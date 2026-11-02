#!/usr/bin/env python3
"""Validate a harness feature_list.json against Protocol v1 rules.

The JSON Schema (templates/feature_list.schema.json) is the documented
contract; this script enforces the same rules with the stdlib only — no
jsonschema dependency on installed projects.

Usage: validate-feature-list.py [--json] <feature-list.json>
Exit codes: 0 valid, 1 invalid, 2 usage error.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable

STATUSES = ("pending", "spec_ready", "in_progress", "blocked", "done")
AUDIT_LEVELS = ("basic", "standard", "strict")
NAME_RE = re.compile(r"^[a-z0-9_]+$")


def parse_args(argv: list[str]) -> "tuple[bool, str] | int":
    """Parse CLI flags; return (as_json, path) or exit code 2."""
    as_json = False
    path: str | None = None
    for a in argv:
        if a == "--json":
            as_json = True
        elif a.startswith("-"):
            print(f"unknown argument: {a}", file=sys.stderr)
            return 2
        else:
            if path is not None:
                print(
                    "usage: validate-feature-list.py [--json] <feature-list.json>",
                    file=sys.stderr,
                )
                return 2
            path = a
    if path is None:
        print("usage: validate-feature-list.py [--json] <feature-list.json>", file=sys.stderr)
        return 2
    return as_json, path


def _validate_project_section(data: dict, err: "Callable[[str, str, str], None]") -> None:
    project = data.get("project")
    if not isinstance(project, dict):
        err("project", "missing", "project section is required")
        return
    name = project.get("name")
    if not isinstance(name, str) or not name:
        err("project.name", "missing", "project.name must be a non-empty string")
    if not isinstance(project.get("parallel"), bool):
        err("project.parallel", "invalid_type", "project.parallel must be a boolean")
    modules = project.get("modules")
    if not isinstance(modules, list) or not all(isinstance(m, str) for m in modules):
        err("project.modules", "invalid_type", "project.modules must be an array of strings")
    level = project.get("audit_level")
    if level not in AUDIT_LEVELS:
        err("project.audit_level", "invalid_enum", f"audit_level must be one of {AUDIT_LEVELS}")


def _validate_feature(feat: object, at: str, seen_ids: set[int], err: "Callable[[str, str, str], None]") -> str | None:
    """Validate one feature entry; return its status when the entry is an object."""
    if not isinstance(feat, dict):
        err(at, "invalid_type", "feature must be an object")
        return None
    fid = feat.get("id")
    if not isinstance(fid, int) or isinstance(fid, bool):
        err(f"{at}.id", "invalid_type", "id must be an integer")
    elif fid in seen_ids:
        err(f"{at}.id", "duplicate", f"duplicate feature id {fid}")
    else:
        seen_ids.add(fid)
    fname = feat.get("name")
    if not isinstance(fname, str) or not NAME_RE.match(fname):
        err(f"{at}.name", "invalid_name", "name must be snake_case ([a-z0-9_]+)")
    for key in ("title", "description"):
        if not isinstance(feat.get(key), str):
            err(f"{at}.{key}", "invalid_type", f"{key} must be a string")
    acceptance = feat.get("acceptance")
    if not isinstance(acceptance, list) or not all(isinstance(a, str) for a in acceptance):
        err(f"{at}.acceptance", "invalid_type", "acceptance must be an array of strings")
    status = feat.get("status")
    if status not in STATUSES:
        err(f"{at}.status", "invalid_enum", f"status must be one of {STATUSES}")
    return status if isinstance(status, str) else None


def _require_done_approval(fname: object, fid: object, at: str, err: "Callable[[str, str, str], None]") -> None:
    if not isinstance(fname, str):
        return
    approval = os.path.join("harness", "specs", fname, "APPROVAL")
    if not os.path.isfile(approval):
        err(
            f"{at}.status",
            "missing_approval",
            f"feature {fid} is done without a human approval record {approval}",
        )


def _validate_features(data: dict, err: "Callable[[str, str, str], None]") -> None:
    features = data.get("features")
    if not isinstance(features, list):
        err("features", "missing", "features array is required")
        return
    seen_ids: set[int] = set()
    names: set[str] = set()
    part_of_refs: list[tuple[str, str]] = []
    in_progress = 0
    for i, feat in enumerate(features):
        at = f"features[{i}]"
        status = _validate_feature(feat, at, seen_ids, err)
        if isinstance(feat, dict):
            fname = feat.get("name")
            if isinstance(fname, str) and NAME_RE.match(fname):
                names.add(fname)
            ref = feat.get("part_of")
            if ref is not None:
                if not isinstance(ref, str) or not ref:
                    err(f"{at}.part_of", "invalid_type", "part_of must be a non-empty string")
                else:
                    part_of_refs.append((at, ref))
        if status == "in_progress":
            in_progress += 1
        if status == "done" and isinstance(feat, dict):
            _require_done_approval(feat.get("name"), feat.get("id"), at, err)
    for at, ref in part_of_refs:
        if ref not in names:
            err(
                f"{at}.part_of",
                "unknown_part_of",
                f"part_of '{ref}' does not match any feature name",
            )
    if in_progress > 1:
        err(
            "features",
            "invariant_I1",
            f"at most one feature may be in_progress (found {in_progress})",
        )


def _validate_document(data: object, err: "Callable[[str, str, str], None]") -> None:
    if not isinstance(data, dict):
        err("", "invalid_type", "document must be an object")
        return
    _validate_project_section(data, err)
    _validate_features(data, err)


def _print_report(errors: list[dict[str, str]], as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "tool": "validate-feature-list",
                    "protocol": 1,
                    "valid": not errors,
                    "errors": errors,
                }
            )
        )
        return
    if errors:
        for e in errors:
            where = e["path"] or "(document)"
            print(f"[FAIL] {where}: {e['message']}")
        print(f"{len(errors)} error(s)")
    else:
        print("feature_list.json is valid (protocol v1)")


def main(argv: list[str]) -> int:
    parsed = parse_args(argv)
    if isinstance(parsed, int):
        return parsed
    as_json, path = parsed
    errors: list[dict[str, str]] = []

    def err(path_in_doc: str, code: str, message: str) -> None:
        errors.append({"path": path_in_doc, "code": code, "message": message})

    try:
        with open(path, encoding="utf-8") as f:
            data: object = json.load(f)
    except FileNotFoundError:
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        err("", "invalid_json", f"not valid JSON: {e}")
        data = None

    _validate_document(data, err)
    _print_report(errors, as_json)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
