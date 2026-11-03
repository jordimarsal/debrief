"""Domain: the shared currency of both ports and the comparability rule (ADR-0002, ADR-0004).

Imports nothing outward — no ggufbench, buildwright, mcp or filesystem here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from debrief.errors import INCOMPARABLE_ROWS, DebriefError

PASS = "pass"
FAIL = "fail"
OUTCOMES = frozenset({PASS, FAIL})


@dataclass(frozen=True)
class TaskSignature:
    """Graded counts per dimension plus the baseline and engine build (ADR-0004).

    ggufbench derives it from the data because version labels have lied before;
    two rows compare only inside one signature.
    """

    graded_counts: tuple[tuple[str, int], ...]
    baseline: str
    engine_build: str

    @classmethod
    def of(cls, graded: Mapping[str, int], baseline: str, engine_build: str) -> TaskSignature:
        return cls(tuple(sorted(graded.items())), baseline, engine_build)

    @property
    def key(self) -> str:
        graded = ",".join(f"{dimension}:{count}" for dimension, count in self.graded_counts)
        return f"{graded}@{self.baseline}@{self.engine_build}"


@dataclass(frozen=True)
class Finding:
    """The shared currency: model, task, outcome, reason, evidence pointer (ADR-0002).

    `signature`, `measure` and `role` carry what one port knows and the other
    does not: bench rows carry a signature and a score, run steps carry the
    buildwright role. Neither port fills the other's fields.
    """

    model: str
    task: str
    outcome: str
    reason: str
    evidence: str
    signature: TaskSignature | None = None
    measure: float | None = None
    role: str | None = None


def shared_signature(rows: Sequence[Finding]) -> TaskSignature | DebriefError:
    """The one task signature covering every row, or a refusal (ADR-0004).

    Rows that do not share a signature answer different questions, so the
    caller gets `incomparable_rows` with the groups named — never an average.
    """
    signatures = {row.signature for row in rows if row.signature is not None}
    if len(signatures) > 1:
        listed = ", ".join(sorted(signature.key for signature in signatures))
        return DebriefError(
            code=INCOMPARABLE_ROWS,
            message="rows span more than one task signature; refusing to rank or average",
            detail=f"{len(signatures)} signatures: {listed}",
        )
    if not signatures:
        return DebriefError(
            code=INCOMPARABLE_ROWS,
            message="no row records a task signature, so comparability cannot be established",
            detail=f"{len(rows)} row(s): " + ", ".join(f"{row.model}/{row.task}" for row in rows),
        )
    return signatures.pop()
