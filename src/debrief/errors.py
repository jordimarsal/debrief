"""Structured errors: every debrief answer is findings or one of these (R1)."""

from __future__ import annotations

from dataclasses import dataclass

BENCH_SOURCE_MISSING = "bench_source_missing"
RUN_SOURCE_MISSING = "run_source_missing"
SOURCE_UNPARSEABLE = "source_unparseable"
INCOMPARABLE_ROWS = "incomparable_rows"
PATH_OUTSIDE_ROOT = "path_outside_root"


@dataclass(frozen=True)
class DebriefError:
    """A refusal a tool returns instead of findings.

    Returned, never raised, so the transport adapter can always render a typed
    response; `code` is the stable contract an agent branches on.
    """

    code: str
    message: str
    detail: str
