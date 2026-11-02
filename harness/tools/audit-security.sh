#!/usr/bin/env bash
# audit-security.sh — SAST + dependency scan for the security-audit module.
#
# Runs the stack-appropriate tools that are available and degrades to
# checklist-only when they are not (§6.3). The installer never runs this script;
# a non-zero exit means HIGH findings and the reviewer must reject approval.
#
# Usage: bash harness/tools/audit-security.sh [--stack=<stack>]
# Exit codes: 0 = no HIGH findings (or checklist-only), 1 = HIGH findings, 2 = usage error

set -uo pipefail

JSON=0
STACK=""
for arg in "$@"; do
  case "$arg" in
    --json) JSON=1 ;;
    --stack=*) STACK="${arg#--stack=}" ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [ -z "$STACK" ]; then
  if [ -f "tsconfig.json" ]; then STACK="typescript"
  elif [ -f "package.json" ]; then STACK="node"
  elif [ -f "build.gradle" ] && { [ -f "AndroidManifest.xml" ] || [ -f "app/src/main/AndroidManifest.xml" ]; }; then STACK="android"
  elif [ -f "build.gradle" ] || [ -f "pom.xml" ]; then STACK="java"
  elif [ -f "requirements.txt" ] || [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then STACK="python"
  elif [ -f "Cargo.toml" ]; then STACK="rust"
  else STACK="generic"
  fi
fi

REPORT="$(mktemp)"
trap 'rm -f "$REPORT"' EXIT
HIGH=0
SKIPPED=()

if [ "$JSON" -eq 0 ]; then
  echo "# Security Audit Report (stack: $STACK)"
  echo ""
fi

FINDINGS_JSON="[]"
MODE="automated"

json_escape() {  # json_escape <string> — quote for embedding in JSON
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' '
}

extract_bandit_json() {  # <report-file-with-bandit-json> → findings array fragment
  python3 - "$1" <<'PYEOF' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("[]")
    raise SystemExit(0)
out = []
for r in d.get("results", []):
    out.append({
        "severity": r.get("issue_severity", "UNKNOWN"),
        "tool": "bandit",
        "rule": r.get("test_id", ""),
        "file": r.get("filename", ""),
        "message": (r.get("issue_text") or "")[:200],
    })
print(json.dumps(out))
PYEOF
}

extract_pip_audit_json() {  # <report-file-with-pip-audit-json>
  python3 - "$1" <<'PYEOF' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("[]")
    raise SystemExit(0)
out = []
for dep in d.get("dependencies", []):
    for v in dep.get("vulns", []):
        out.append({
            "severity": "UNKNOWN",
            "tool": "pip-audit",
            "rule": ",".join(v.get("fix_versions", []) or []) or (v.get("id") or ""),
            "file": f"{dep.get('name','')}=={dep.get('version','')}",
            "message": (v.get("description") or "")[:200],
        })
print(json.dumps(out))
PYEOF
}

extract_npm_audit_json() {  # <report-file-with-npm-audit-json>
  if [ ! -f "$1" ]; then echo "[]"; return; fi
  node -e '
const fs = require("fs");
let d;
try { d = JSON.parse(fs.readFileSync(process.argv[1], "utf8")); } catch (e) { console.log("[]"); process.exit(0); }
const out = [];
const vulns = (d.vulnerabilities && typeof d.vulnerabilities === "object") ? Object.values(d.vulnerabilities) : [];
for (const v of vulns) {
  out.push({severity: (v.severity || "unknown").toUpperCase(), tool: "npm-audit", rule: (v.via || []).map(x => typeof x === "string" ? x : (x.source || "")).join(","), file: v.name || "", message: ((v.title || "") + "").slice(0, 200)});
}
console.log(JSON.stringify(out));
' "$1" 2>/dev/null || echo "[]"
}

case "$STACK" in
  python)
    if command -v bandit >/dev/null 2>&1; then
      if [ "$JSON" -eq 1 ]; then
        bandit -r . -x ./.venv,./venv,./node_modules,./.buildwright -q -f json > "$REPORT" 2>/dev/null || true
        FINDINGS_JSON="$(extract_bandit_json "$REPORT")"
        [ -n "$FINDINGS_JSON" ] || FINDINGS_JSON="[]"
        if grep -q '"issue_severity": "HIGH"' "$REPORT"; then
          HIGH=1
        fi
      else
        echo "## SAST: bandit"
        # ./.buildwright: worktrees of the buildwright runtime (each carries
        # its own .venv) — vendored deps are not this project's attack surface
        bandit -r . -x ./.venv,./venv,./node_modules,./.buildwright -q > "$REPORT" 2>/dev/null || true
        grep -E "Issue:|Severity:|Location:" "$REPORT" || echo "No issues reported"
        if grep -q "Severity: High" "$REPORT"; then
          echo "HIGH severity finding(s) from bandit — see above"
          HIGH=1
        fi
      fi
    else
      [ "$JSON" -eq 1 ] && SKIPPED+=("bandit: not installed")
      [ "$JSON" -eq 1 ] || echo "## SAST: bandit — SKIPPED (not installed; uvx bandit, or pip install bandit)"
    fi
    if command -v pip-audit >/dev/null 2>&1; then
      if [ "$JSON" -eq 1 ]; then
        if ! pip-audit --progress-spinner off --format json > "$REPORT" 2>&1; then
          PA="$(extract_pip_audit_json "$REPORT")"
          FINDINGS_JSON="$(python3 -c "import json,sys; print(json.dumps(json.loads(sys.argv[1]) + json.loads(sys.argv[2])))" "$FINDINGS_JSON" "$PA" 2>/dev/null || echo "$FINDINGS_JSON")"
          HIGH=1
        fi
      else
        echo "## Dependency scan: pip-audit"
        if ! pip-audit --progress-spinner off > "$REPORT" 2>&1; then
          cat "$REPORT"
          HIGH=1
        else
          echo "No known vulnerabilities in resolved dependencies"
        fi
      fi
    else
      [ "$JSON" -eq 1 ] && SKIPPED+=("pip-audit: not installed")
      [ "$JSON" -eq 1 ] || echo "## Dependency scan: pip-audit — SKIPPED (not installed; uvx pip-audit, or pip install pip-audit)"
    fi
    ;;
  typescript|node)
    if command -v npm >/dev/null 2>&1 && [ -f "package.json" ]; then
      if [ "$JSON" -eq 1 ]; then
        if ! npm audit --audit-level=high --json > "$REPORT" 2>&1; then
          FINDINGS_JSON="$(extract_npm_audit_json "$REPORT")"
          HIGH=1
        fi
      else
        echo "## Dependency scan: npm audit"
        if ! npm audit --audit-level=high > "$REPORT" 2>&1; then
          tail -n 30 "$REPORT"
          HIGH=1
        else
          echo "No high-severity dependency vulnerabilities"
        fi
      fi
    else
      [ "$JSON" -eq 1 ] && SKIPPED+=("npm audit: npm or package.json missing")
      [ "$JSON" -eq 1 ] || echo "## Dependency scan: npm audit — SKIPPED (npm or package.json missing)"
    fi
    if ls .eslintrc* eslint.config.* >/dev/null 2>&1; then
      [ "$JSON" -eq 1 ] || echo "## SAST: eslint — run 'npx eslint .' and review security rules"
    else
      [ "$JSON" -eq 1 ] && SKIPPED+=("eslint: not configured")
      [ "$JSON" -eq 1 ] || echo "## SAST: eslint — SKIPPED (not configured)"
    fi
    ;;
  rust)
    if command -v cargo-audit >/dev/null 2>&1; then
      [ "$JSON" -eq 0 ] && echo "## Dependency scan: cargo audit"
      if ! cargo audit > "$REPORT" 2>&1; then
        [ "$JSON" -eq 0 ] && tail -n 30 "$REPORT"
        HIGH=1
      else
        [ "$JSON" -eq 0 ] && echo "No vulnerable crates"
      fi
    else
      [ "$JSON" -eq 1 ] && SKIPPED+=("cargo-audit: not installed")
      [ "$JSON" -eq 1 ] || echo "## Dependency scan: cargo audit — SKIPPED (not installed; cargo install cargo-audit)"
    fi
    if cargo clippy --version >/dev/null 2>&1; then
      [ "$JSON" -eq 1 ] || echo "## SAST: clippy — run 'cargo clippy -- -W clippy::all' and fix warnings"
    else
      [ "$JSON" -eq 1 ] && SKIPPED+=("clippy: not installed")
      [ "$JSON" -eq 1 ] || echo "## SAST: clippy — SKIPPED"
    fi
    ;;
  java|android)
    MODE="checklist-only"
    if grep -q "dependency-check" build.gradle pom.xml 2>/dev/null; then
      [ "$JSON" -eq 1 ] || echo "## Dependency scan: OWASP dependency-check is configured — run its Gradle/Maven task"
    else
      [ "$JSON" -eq 1 ] && SKIPPED+=("dependency-check: not configured")
      [ "$JSON" -eq 1 ] || echo "## Dependency scan: OWASP dependency-check — not configured; checklist-only"
    fi
    ;;
  *)
    MODE="checklist-only"
    [ "$JSON" -eq 1 ] || echo "## Checklist-only audit (no automated tools for stack: $STACK)"
    ;;
esac

[ -n "$FINDINGS_JSON" ] || FINDINGS_JSON="[]"

if [ "$JSON" -eq 1 ]; then
  VERDICT="PASS"
  [ "$HIGH" -eq 1 ] && VERDICT="REJECT"
  SKIPPED_JSON="[]"
  if [ "${#SKIPPED[@]}" -gt 0 ]; then
    SKIPPED_JSON="["
    first=1
    for s in "${SKIPPED[@]}"; do
      if [ $first -eq 1 ]; then first=0; else SKIPPED_JSON="$SKIPPED_JSON,"; fi
      SKIPPED_JSON="$SKIPPED_JSON\"$(json_escape "$s")\""
    done
    SKIPPED_JSON="$SKIPPED_JSON]"
  fi
  printf '{"tool":"audit-security","protocol":1,"stack":"%s","mode":"%s","verdict":"%s","findings":%s,"skipped":%s}\n' \
    "$(json_escape "$STACK")" "$MODE" "$VERDICT" "$FINDINGS_JSON" "$SKIPPED_JSON"
else
  echo ""
  echo "## Checklist"
  echo "Confirm every item of the Security Audit Checklist in docs/verification.md"
  echo "(section 'Security Audit Checklist'). Record the outcome in the review file."
  echo ""
  if [ "$HIGH" -eq 1 ]; then
    echo "VERDICT: HIGH severity findings — approval must be rejected (audit_level standard/strict)."
    exit 1
  fi
  echo "VERDICT: no HIGH severity findings reported by automated tools."
  exit 0
fi
[ "$HIGH" -eq 1 ] && exit 1
exit 0
