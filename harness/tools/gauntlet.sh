#!/usr/bin/env bash
# gauntlet.sh — Mechanical gate for the gauntlet module (pass G1).
#
# Verifies the checkable half of a feature before any judgment pass runs:
# the spec trio exists, every task is [x], and requirement traceability has
# no gaps. Semantic judgment (does the test really verify the requirement?)
# stays with the reviewer — this script only proves the mapping exists.
#
# Usage: bash harness/tools/gauntlet.sh --feature NAME [--root DIR] [--json]
# Exit codes: 0 = PASS (mechanical gates green), 1 = REJECT (gaps found),
#             2 = usage error (mirrors check-traceability.py hard guards:
#             a verdict without per-feature evidence lines is a vacuous PASS)
#
# Protocol v1 JSON (--json): {"tool": "gauntlet", "protocol": 1, ...} first.

set -uo pipefail

FEATURE=""
ROOT="."
JSON=0

while [ $# -gt 0 ]; do
  case "$1" in
    --feature=*) FEATURE="${1#*=}" ;;
    --feature) shift; FEATURE="${1:-}" ;;
    --root=*) ROOT="${1#*=}" ;;
    --root) shift; ROOT="${1:-}" ;;
    --json) JSON=1 ;;
    -h|--help)
      echo "Usage: gauntlet.sh --feature NAME [--root DIR] [--json]"
      exit 0 ;;
    *) echo "gauntlet.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

# Guard 1: a named feature is mandatory — bare invocations used to pass 0/0.
if [ -z "$FEATURE" ]; then
  echo "gauntlet.sh: --feature NAME is required (refusing a vacuous PASS)" >&2
  exit 2
fi
if [ ! -d "$ROOT" ]; then
  echo "gauntlet.sh: root is not a directory: $ROOT" >&2
  exit 2
fi

SPEC_DIR="$ROOT/harness/specs/$FEATURE"
REQ="$SPEC_DIR/requirements.md"
TASKS="$SPEC_DIR/tasks.md"
DESIGN="$SPEC_DIR/design.md"

GAPS=()
CHECKS=()  # entries as "name:ok" / "name:fail"

# Guard 2: the spec trio must exist before anything else counts.
for f in "$REQ" "$DESIGN" "$TASKS"; do
  if [ -f "$f" ]; then
    CHECKS+=("spec-$(basename "$f" .md):ok")
  else
    CHECKS+=("spec-$(basename "$f" .md):fail")
    GAPS+=("missing spec file: $f")
  fi
done
if [ ! -f "$REQ" ]; then
  GAPS+=("no requirements.md — nothing to trace, gauntlet stops here")
fi

# Check: no unchecked tasks remain.
DONE=0
TOTAL=0
if [ -f "$TASKS" ]; then
  TOTAL="$(grep -cE '^- \[[ xX]\] T[0-9]+' "$TASKS" || true)"
  DONE="$(grep -cE '^- \[[xX]\] T[0-9]+' "$TASKS" || true)"
  if [ "$TOTAL" -eq 0 ]; then
    CHECKS+=("tasks:fail")
    GAPS+=("tasks.md declares no T<n> tasks")
  elif [ "$DONE" -lt "$TOTAL" ]; then
    CHECKS+=("tasks:fail")
    GAPS+=("$((TOTAL - DONE)) of $TOTAL tasks still [ ] in $TASKS")
  else
    CHECKS+=("tasks:ok")
  fi
fi

# Check: traceability has no gaps (delegates to check-traceability.py).
TRACE_STATUS="skipped"
if [ -x "$ROOT/harness/tools/check-traceability.py" ] && command -v python3 >/dev/null 2>&1; then
  TRACE_OUT="$(python3 "$ROOT/harness/tools/check-traceability.py" --feature "$FEATURE" --root "$ROOT" 2>&1)"
  TRACE_RC=$?
  if [ "$TRACE_RC" -eq 0 ]; then
    # A verdict without a per-feature evidence line is a vacuous PASS.
    if printf '%s\n' "$TRACE_OUT" | grep -qE "^## $FEATURE: [0-9]+/[0-9]+"; then
      CHECKS+=("traceability:ok")
      TRACE_STATUS="ok"
    else
      CHECKS+=("traceability:fail")
      TRACE_STATUS="vacuous"
      GAPS+=("traceability verdict lacks a '## $FEATURE: n/n' evidence line")
    fi
  elif [ "$TRACE_RC" -eq 2 ]; then
    CHECKS+=("traceability:fail")
    TRACE_STATUS="usage-error"
    GAPS+=("traceability guard: $TRACE_OUT")
  else
    CHECKS+=("traceability:fail")
    TRACE_STATUS="gaps"
    GAPS+=("traceability gaps: $(printf '%s' "$TRACE_OUT" | tr '\n' ' ')")
  fi
else
  CHECKS+=("traceability:fail")
  GAPS+=("harness/tools/check-traceability.py missing or python3 unavailable")
fi

if [ "${#GAPS[@]}" -eq 0 ]; then VERDICT="PASS"; RC=0; else VERDICT="REJECT"; RC=1; fi

json_escape() {  # json_escape <string> — quote for embedding in JSON
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\t\r' '   '
}

if [ "$JSON" -eq 1 ]; then
  checks_json=""
  for c in ${CHECKS[@]+"${CHECKS[@]}"}; do
    n="${c%%:*}"; s="${c##*:}"
    checks_json="${checks_json:+$checks_json,}{\"name\": \"$n\", \"status\": \"$s\"}"
  done
  gaps_json=""
  for g in ${GAPS[@]+"${GAPS[@]}"}; do
    gaps_json="${gaps_json:+$gaps_json,}\"$(json_escape "$g")\""
  done
  printf '{"tool": "gauntlet", "protocol": 1, "feature": "%s", "verdict": "%s", "checks": [%s], "gaps": [%s]}\n' \
    "$(json_escape "$FEATURE")" "$VERDICT" "$checks_json" "$gaps_json"
else
  echo "# Gauntlet G1 — feature $FEATURE: $VERDICT"
  echo ""
  for c in ${CHECKS[@]+"${CHECKS[@]}"}; do echo "- $c"; done
  if [ "${#GAPS[@]}" -gt 0 ]; then
    echo ""
    echo "## Gaps"
    for g in ${GAPS[@]+"${GAPS[@]}"}; do echo "- $g"; done
  fi
  echo ""
  echo "Traceability detail: $TRACE_STATUS"
fi

exit "$RC"
