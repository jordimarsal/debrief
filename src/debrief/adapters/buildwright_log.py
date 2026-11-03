"""buildwright run log adapter: read-only mapping of one run log to Findings (R4).

Format: ``key: value`` header lines (``run:``, ``engine_build:``, ``task:``,
``roles:``, ``result:``) followed by one ``step:`` line per logged step. The
adapter is the only place that knows this format (ADR-0002); a run log never
yields a task signature — it is one episode, not a measurement.
"""

from __future__ import annotations

import logging
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from debrief.domain import FAIL, OUTCOMES, PASS, Finding
from debrief.errors import RUN_SOURCE_MISSING, SOURCE_UNPARSEABLE, DebriefError

log = logging.getLogger(__name__)

_STEP_RE = re.compile(
    r"^step:\s*(?P<ordinal>\d+)\s+"
    r"role=(?P<role>\S+)\s+"
    r"model=(?P<model>\S+)\s+"
    r"outcome=(?P<outcome>\S+)\s+"
    r'reason="(?P<reason>[^"]*)"\s+'
    r"evidence=(?P<evidence>\S+)$"
)

_RESULT_RE = re.compile(r"^(?P<outcome>\S+)(?:\s+failed_steps=(?P<failed_steps>\S*))?$")


class _Unparseable(Exception):
    """A run log did not match the buildwright log format."""


@dataclass(frozen=True)
class _Step:
    """One logged step before it becomes a Finding; the ordinal exists only
    here because the ``result:`` header names failed steps by it, and a
    Finding never carries run-internal bookkeeping (ADR-0002)."""

    ordinal: str
    role: str
    model: str
    outcome: str
    reason: str
    evidence: str


class BuildwrightLog:
    """RunLog over one buildwright run log; opens the file for reading only (R2, R4)."""

    def __init__(self, log_file: Path) -> None:
        self._log_file = log_file

    def findings(self) -> list[Finding] | DebriefError:
        # stat()-based probe, mirroring the bench adapter: pathlib's is_file()
        # answers False for a log whose parent directory is unreadable, which
        # would mislabel an existing-but-unreadable log as missing. An evidence
        # tool never silently drops a source it was asked to read.
        try:
            st = self._log_file.stat()
        except FileNotFoundError, NotADirectoryError:
            return DebriefError(
                code=RUN_SOURCE_MISSING,
                message="no buildwright run log at the requested path",
                detail=str(self._log_file),
            )
        except PermissionError as err:
            return DebriefError(
                code=SOURCE_UNPARSEABLE,
                message=f"{self._log_file} exists but cannot be probed",
                detail=str(err),
            )
        if not stat.S_ISREG(st.st_mode):
            return DebriefError(
                code=RUN_SOURCE_MISSING,
                message="no buildwright run log at the requested path",
                detail=str(self._log_file),
            )
        try:
            lines = self._log_file.read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError) as err:
            # ValueError covers undecodable bytes (UnicodeDecodeError), not just I/O errors.
            return DebriefError(
                code=SOURCE_UNPARSEABLE,
                message=f"{self._log_file} could not be read",
                detail=str(err),
            )
        try:
            findings = _map_log(lines)
        except _Unparseable as err:
            return DebriefError(
                code=SOURCE_UNPARSEABLE,
                message=f"{self._log_file} is not a buildwright run log",
                detail=str(err),
            )
        log.info("read %d step(s) from %s", len(findings), self._log_file.name)
        return findings


def _map_log(lines: list[str]) -> list[Finding]:
    task = _header(lines, "task")
    steps = [_parse_step(line) for line in lines if line.startswith("step:")]
    if not steps:
        # A headers-only log (truncated or step-stripped) would otherwise answer
        # [] as a structured success and flip routing.propose to the all-passed
        # claim even when the log's own result: header declares a failure — the
        # same fabrication class the outcome-enum check guards. An evidence tool
        # never silently accepts an episode with no logged steps.
        raise _Unparseable("run log has a task header but no step: lines")
    _check_result_header(_optional_header(lines, "result"), steps)
    return [_finding(step, task) for step in steps]


def _header(lines: list[str], key: str) -> str:
    prefix = f"{key}:"
    for line in lines:
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            if value:
                return value
    raise _Unparseable(f"no {key}: header line")


def _optional_header(lines: list[str], key: str) -> str | None:
    prefix = f"{key}:"
    for line in lines:
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            return value or None
    return None


def _parse_step(line: str) -> _Step:
    match = _STEP_RE.match(line)
    if match is None:
        raise _Unparseable(f"malformed step line: {line!r}")
    outcome = match.group("outcome")
    if outcome not in OUTCOMES:
        # An unvalidated token would flip _propose to "every logged step passed"
        # for a failed run, so the enum is checked at this boundary (conventions:
        # validate at the boundary, trust types inside).
        raise _Unparseable(f"outcome is not one of {sorted(OUTCOMES)}: {outcome!r}")
    return _Step(
        ordinal=match.group("ordinal"),
        role=match.group("role"),
        model=match.group("model"),
        outcome=outcome,
        reason=match.group("reason"),
        evidence=match.group("evidence"),
    )


def _finding(step: _Step, task: str) -> Finding:
    return Finding(
        model=step.model,
        task=task,
        outcome=step.outcome,
        reason=step.reason,
        evidence=step.evidence,
        role=step.role,
    )


def _check_result_header(result_line: str | None, steps: list[_Step]) -> None:
    """A log's ``result:`` header is evidence too: when present it must not
    contradict the steps it summarizes. Left unchecked, ``result: pass`` over a
    logged failure (or a failed_steps list naming steps that passed) would let
    run.inspect answer a success the log itself calls a lie, and
    routing.propose the all-passed claim for a failed episode. The header stays
    optional — producers older than the failed_steps convention omit it — and
    the check runs only once every step line has parsed."""
    if result_line is None:
        return
    match = _RESULT_RE.fullmatch(result_line)
    if match is None:
        raise _Unparseable(f"malformed result: header: {result_line!r}")
    outcome = match.group("outcome")
    if outcome not in OUTCOMES:
        raise _Unparseable(f"result header outcome is not one of {sorted(OUTCOMES)}: {outcome!r}")
    failed = [step for step in steps if step.outcome == FAIL]
    if outcome == PASS:
        if failed:
            raise _Unparseable(
                f"result header declares pass but logged step {failed[0].ordinal} failed"
            )
        return
    declared = _declared_failed_steps(match.group("failed_steps"))
    if not failed:
        raise _Unparseable("result header declares a failure no logged step records")
    logged = {step.ordinal.lstrip("0") or "0" for step in failed}
    if declared != logged:
        raise _Unparseable(
            f"result header failed_steps={match.group('failed_steps')!r} does not match"
            f" the logged failing step(s) {sorted(logged)}"
        )


def _declared_failed_steps(token: str | None) -> set[str]:
    if token is None:
        raise _Unparseable("result header declares a failure without a failed_steps list")
    declared = {part.strip().lstrip("0") or "0" for part in token.split(",") if part.strip()}
    if not declared:
        raise _Unparseable(f"result header failed_steps is empty: {token!r}")
    return declared
