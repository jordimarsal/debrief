"""Ports the domain drives: two independent evidence sources (ADR-0002)."""

from __future__ import annotations

from typing import Protocol

from debrief.domain import Finding
from debrief.errors import DebriefError


class BenchStore(Protocol):
    """What ggufbench measured (R3): the only bench source debrief reads."""

    def findings(self) -> list[Finding] | DebriefError: ...


class RunLog(Protocol):
    """One buildwright run (R4): the only run source debrief reads."""

    def findings(self) -> list[Finding] | DebriefError: ...
