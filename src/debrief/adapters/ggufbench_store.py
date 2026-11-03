"""ggufbench artifacts adapter: read-only mapping of artifact rows to Findings (R3).

Layout: one ``<run-id>/results.json`` per ggufbench run under the artifact root.
The adapter is the only place that knows this format (ADR-0002).
"""

from __future__ import annotations

import json
import logging
import math
import re
import stat
from pathlib import Path
from typing import Any

from debrief.domain import OUTCOMES, Finding, TaskSignature
from debrief.errors import BENCH_SOURCE_MISSING, SOURCE_UNPARSEABLE, DebriefError

log = logging.getLogger(__name__)

RESULTS_FILE = "results.json"

# Artifact string fields reach the routing.propose text verbatim, so a newline
# in a poisoned row could forge arbitrary proposal diff lines (ADR-0004
# fabrication class). Identifier-like fields must be single-line whitespace-free
# tokens; free-text fields single-line control-char-free — both validated here,
# at the boundary, per conventions.
_TOKEN_RE = re.compile(r"\S+")


class _Unparseable(Exception):
    """An artifact did not match the ggufbench results schema."""


class GgufbenchStore:
    """BenchStore over ggufbench artifacts; opens files for reading only (R2, R3)."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root

    def findings(self) -> list[Finding] | DebriefError:
        try:
            results_files = self._results_files()
        except OSError as err:
            return DebriefError(
                code=SOURCE_UNPARSEABLE,
                message=f"{self._artifact_root} could not be scanned for {RESULTS_FILE}",
                detail=str(err),
            )
        except _Unparseable as err:
            # A symlink below the requested path must not turn the store into a
            # read primitive for files outside the evidence root (conventions:
            # resolve against an explicit allowed root — security-audit A03).
            return DebriefError(
                code=SOURCE_UNPARSEABLE,
                message=f"a run's {RESULTS_FILE} escapes the ggufbench artifact root",
                detail=str(err),
            )
        if results_files is None:
            return DebriefError(
                code=BENCH_SOURCE_MISSING,
                message="no ggufbench artifacts at the requested path",
                detail=str(self._artifact_root),
            )
        if not results_files:
            return DebriefError(
                code=BENCH_SOURCE_MISSING,
                message=f"no {RESULTS_FILE} under any run directory",
                detail=str(self._artifact_root),
            )
        findings: list[Finding] = []
        for results_file in results_files:
            mapped = _read_run(results_file)
            if isinstance(mapped, DebriefError):
                return mapped
            findings.extend(mapped)
        log.info("read %d ggufbench row(s) from %d run(s)", len(findings), len(results_files))
        return findings

    def _results_files(self) -> list[Path] | None:
        """One results.json per run under the root; None when the root itself is absent.

        Scans with stat(), not is_file(): pathlib's is_*() answer False for
        unreadable directories, which would silently drop a run the tool must
        report; stat() raises, and findings() maps that to a structured error.
        Every candidate is resolved and required to stay under the resolved
        root before anything is read, so symlink indirection below the
        requested path cannot escape the evidence root (A03).
        """
        root = self._artifact_root.resolve()
        if not root.is_dir():
            return None
        own = _contained_results(root, root / RESULTS_FILE)
        if own is not None:
            return [own]
        found: list[Path] = []
        for path in root.iterdir():
            contained = _contained_results(root, path / RESULTS_FILE)
            if contained is not None:
                found.append(contained)
        return sorted(found)


def _contained_results(root: Path, candidate: Path) -> Path | None:
    """Resolve `candidate` and return it only when it stays under `root` and is a file.

    A `<run>/results.json` may be a symlink: without this check an artifact
    could name any file on the host and its bytes would enter findings,
    bypassing the root boundary every agent-controlled path respects.
    An escaping candidate refuses the whole scan — an evidence tool never
    silently drops (or silently reads past its boundary) a run directory.
    """
    try:
        resolved = candidate.resolve()
    except OSError as err:
        raise _Unparseable(f"{candidate} could not be resolved") from err
    if not resolved.is_relative_to(root):
        raise _Unparseable(f"{candidate} resolves outside the artifact root")
    return resolved if _is_regular_file(resolved) else None


def _is_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.stat().st_mode)
    except FileNotFoundError, NotADirectoryError:
        return False


def _read_run(results_file: Path) -> list[Finding] | DebriefError:
    try:
        document: Any = json.loads(results_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as err:
        # ValueError covers JSONDecodeError and undecodable bytes; RecursionError
        # covers nesting-bomb JSON, which no legitimate artifact carries.
        return DebriefError(
            code=SOURCE_UNPARSEABLE,
            message=f"{results_file} could not be read as JSON",
            detail=str(err),
        )
    try:
        return _map_document(document)
    except _Unparseable as err:
        return DebriefError(
            code=SOURCE_UNPARSEABLE,
            message=f"{results_file} is not a ggufbench results document",
            detail=str(err),
        )


def _map_document(document: Any) -> list[Finding]:
    if not isinstance(document, dict):
        raise _Unparseable("document is not an object")
    engine_build = _required_token(document, "engine_build")
    baseline = _required_token(document, "baseline")
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise _Unparseable("rows is not an array")
    return [_map_row(row, baseline, engine_build) for row in rows]


def _map_row(row: Any, baseline: str, engine_build: str) -> Finding:
    if not isinstance(row, dict):
        raise _Unparseable("row is not an object")
    graded = _required_counts(row)
    score = row.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise _Unparseable("score is not a number")
    try:
        measure = float(score)
    except OverflowError as err:
        # JSON integers are arbitrary-precision; a score too wide for a float is
        # corrupt evidence, not a crash (R1: every answer is findings or a
        # structured error).
        raise _Unparseable(f"score overflows a float: {score}") from err
    if not math.isfinite(measure):
        # json.loads accepts the NaN/Infinity/-Infinity tokens; a non-finite
        # measure would win the proposal ranking and fabricate a role change
        # (the ADR-0004 fabrication class), so it refuses at this boundary.
        raise _Unparseable(f"score is not a finite number: {measure!r}")
    outcome = _required_str(row, "outcome")
    if outcome not in OUTCOMES:
        raise _Unparseable(f"outcome is not one of {sorted(OUTCOMES)}: {outcome!r}")
    return Finding(
        model=_required_token(row, "model"),
        task=_required_token(row, "task"),
        outcome=outcome,
        reason=_required_line(row, "reason"),
        evidence=_required_line(row, "artifact"),
        signature=TaskSignature.of(graded, baseline, engine_build),
        measure=measure,
    )


def _required_counts(row: dict[str, Any]) -> dict[str, int]:
    graded = row.get("graded")
    if not isinstance(graded, dict):
        raise _Unparseable("graded is not an object of counts")
    counts: dict[str, int] = {}
    for dimension, count in graded.items():
        if not isinstance(dimension, str) or isinstance(count, bool) or not isinstance(count, int):
            raise _Unparseable("graded counts must map dimension names to integers")
        if _TOKEN_RE.fullmatch(dimension) is None:
            # Dimension names join the task signature and the proposal text; a
            # multi-line name would forge proposal lines exactly like a model id.
            raise _Unparseable(f"graded dimension is not a single-line token: {dimension!r}")
        counts[dimension] = count
    return counts


def _required_str(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise _Unparseable(f"{key} is not a non-empty string")
    return value


def _required_token(document: dict[str, Any], key: str) -> str:
    """Identifier-like field: one non-empty, whitespace-free line (no newline forgery)."""
    value = _required_str(document, key)
    if _TOKEN_RE.fullmatch(value) is None:
        raise _Unparseable(f"{key} is not a single-line whitespace-free token: {value!r}")
    _refuse_control_chars(key, value)
    return value


def _required_line(document: dict[str, Any], key: str) -> str:
    """Free-text field: one non-empty line with no control characters (incl. newlines).

    The single-line rule is str.splitlines(), not just ``ord(ch) < 0x20``:
    Unicode line separators (U+0085 NEL, U+2028, U+2029) sit above that range
    but still split the value everywhere Python splits text, so a poisoned
    reason or artifact path could smuggle a forged proposal line past a pure
    control-character check.
    """
    value = _required_str(document, key)
    _refuse_control_chars(key, value)
    if value.splitlines() != [value]:
        raise _Unparseable(f"{key} is not a single line: {value!r}")
    return value


def _refuse_control_chars(key: str, value: str) -> None:
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise _Unparseable(f"{key} contains control characters: {value!r}")
