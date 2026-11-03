"""Driving use cases: one per agent question (QueryBench S1, InspectRun S2, ProposeRole S3)."""

from __future__ import annotations

import logging

from debrief.domain import FAIL, PASS, Finding, shared_signature
from debrief.errors import DebriefError
from debrief.ports import BenchStore, RunLog

log = logging.getLogger(__name__)


class QueryBench:
    """ "What did ggufbench measure?" — answered only from a BenchStore (R3)."""

    def __init__(self, store: BenchStore) -> None:
        self._store = store

    def run(self) -> list[Finding] | DebriefError:
        answer = self._store.findings()
        if isinstance(answer, DebriefError):
            log.warning("bench query refused: %s", answer.code)
            return answer
        log.info("bench query answered from receipts: %d findings", len(answer))
        return answer


class InspectRun:
    """ "Where did this run break?" — answered only from a RunLog (R4)."""

    def __init__(self, run_log: RunLog) -> None:
        self._run_log = run_log

    def run(self) -> list[Finding] | DebriefError:
        answer = self._run_log.findings()
        if isinstance(answer, DebriefError):
            log.warning("run inspection refused: %s", answer.code)
            return answer
        log.info("run inspection answered from receipts: %d findings", len(answer))
        return answer


class ProposeRole:
    """ "What would you change?" — a BW_ROLE_* diff as text (R5, ADR-0003).

    The only use case allowed to read findings from both ports (ADR-0002);
    it renders text and writes nothing (ADR-0001).
    """

    def __init__(self, bench: QueryBench, run: InspectRun) -> None:
        self._bench = bench
        self._run = run

    def run(self) -> str | DebriefError:
        bench_answer = self._bench.run()
        if isinstance(bench_answer, DebriefError):
            return bench_answer
        run_answer = self._run.run()
        if isinstance(run_answer, DebriefError):
            return run_answer
        return _propose(bench_answer, run_answer)


def _propose(bench_rows: list[Finding], run_rows: list[Finding]) -> str | DebriefError:
    failures = [row for row in run_rows if row.outcome == FAIL]
    if not failures:
        return "no proposal: every logged step passed"
    lines: list[str] = []
    proposed_roles: set[str] = set()
    for failure in failures:
        role = failure.role
        if role is None:
            lines.append(
                f"note: step on {failure.task} recorded no role, nothing to propose"
                f" ({failure.evidence})"
            )
            continue
        canonical = _canonical_role(role)
        if canonical in proposed_roles:
            continue
        proposal = _role_proposal(canonical, failure, bench_rows)
        if isinstance(proposal, DebriefError):
            return proposal
        lines.extend(proposal)
        proposed_roles.add(canonical)
    return "\n".join(lines)


def _canonical_role(role: str) -> str:
    """One env name per role: step lines record the env-var name as often as the
    bare role, and a token that already carries the canonical prefix would
    otherwise render a `BW_ROLE_BW_ROLE_*` diff nobody can paste into the
    buildwright env."""
    return role.upper().removeprefix("BW_ROLE_")


def _role_proposal(
    role: str, failure: Finding, bench_rows: list[Finding]
) -> list[str] | DebriefError:
    role_env = f"BW_ROLE_{role.upper()}"
    cohort = [row for row in bench_rows if row.task == failure.task]
    if not cohort:
        return [
            f"note: ggufbench never measured {failure.task}, keeping {role_env}={failure.model}"
        ]
    signature = shared_signature(cohort)
    if isinstance(signature, DebriefError):
        return signature
    candidates = [
        row
        for row in cohort
        if row.model != failure.model and row.outcome == PASS and row.measure is not None
    ]
    if not candidates:
        return [
            f"note: no passing model for {failure.task} in the bench cohort,"
            f" keeping {role_env}={failure.model}"
        ]
    winner = sorted(candidates, key=lambda row: (-(row.measure or 0.0), row.model))[0]
    return [
        f"proposal: {role_env} holds {failure.model}, which failed task {failure.task}",
        f"- {role_env}={failure.model}",
        f"+ {role_env}={winner.model}",
        f"why run: {failure.model} failed {failure.task} ({failure.reason}) — {failure.evidence}",
        f"why bench: {winner.model} passed {failure.task} at score {winner.measure:.2f}"
        f" ({winner.reason}) — {winner.evidence}",
        f"signature: {signature.key}",
        "not applied: debrief never writes; paste the + line into the buildwright role env"
        " (ADR-0001). Proposals target roles, never models.yaml (ADR-0003).",
    ]
