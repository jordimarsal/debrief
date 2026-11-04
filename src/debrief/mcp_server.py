"""MCP stdio adapter: three tools that answer from receipts and never write (R1, R2).

Tool names carry the port (bench.*, run.*, routing.propose) so an agent cannot
confuse what was measured with what happened in one run (ADR-0002).
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from debrief.adapters.buildwright_log import BuildwrightLog
from debrief.adapters.ggufbench_store import GgufbenchStore
from debrief.domain import Finding
from debrief.errors import PATH_OUTSIDE_ROOT, DebriefError
from debrief.use_cases import InspectRun, ProposeRole, QueryBench

log = logging.getLogger(__name__)

BENCH_ROOT_ENV = "DEBRIEF_BENCH_ROOT"
RUN_ROOT_ENV = "DEBRIEF_RUN_ROOT"
DEFAULT_BENCH_ROOT = "artifacts/ggufbench"
DEFAULT_RUN_ROOT = "artifacts/buildwright"

server = MCPServer(
    "debrief",
    instructions=(
        "debrief answers agent questions from receipts: bench.query (ggufbench artifacts), "
        "run.inspect (one buildwright run log), routing.propose (a BW_ROLE_* diff as text). "
        "It never writes; every answer is findings or a structured error."
    ),
)


@dataclass(frozen=True)
class FindingsResponse:
    """A bench.* / run.* answer: findings, or a structured error and no findings (R1)."""

    findings: list[Finding] = field(default_factory=list)
    error: DebriefError | None = None

    @classmethod
    def of(cls, answer: list[Finding] | DebriefError) -> FindingsResponse:
        if isinstance(answer, DebriefError):
            return cls(error=answer)
        return cls(findings=list(answer))


@dataclass(frozen=True)
class ProposalResponse:
    """The routing.propose answer: a BW_ROLE_* diff as text, or a structured error (R1, R5)."""

    proposal: str = ""
    error: DebriefError | None = None

    @classmethod
    def of(cls, answer: str | DebriefError) -> ProposalResponse:
        if isinstance(answer, DebriefError):
            return cls(error=answer)
        return cls(proposal=answer)


@server.tool(
    name="bench.query",
    title="What did ggufbench measure?",
    description=(
        "Findings from ggufbench artifacts. `path` is a run directory (or the artifact root "
        "itself) relative to DEBRIEF_BENCH_ROOT. Read-only."
    ),
)
def bench_query(path: str) -> FindingsResponse:
    resolved = _resolve_within(BENCH_ROOT_ENV, DEFAULT_BENCH_ROOT, path)
    if isinstance(resolved, DebriefError):
        return FindingsResponse(error=resolved)
    return FindingsResponse.of(QueryBench(GgufbenchStore(resolved)).run())


@server.tool(
    name="run.inspect",
    title="Where did this run break?",
    description=(
        "Findings from one buildwright run log. `path` is the log file relative to "
        "DEBRIEF_RUN_ROOT. Read-only."
    ),
)
def run_inspect(path: str) -> FindingsResponse:
    resolved = _resolve_within(RUN_ROOT_ENV, DEFAULT_RUN_ROOT, path)
    if isinstance(resolved, DebriefError):
        return FindingsResponse(error=resolved)
    return FindingsResponse.of(InspectRun(BuildwrightLog(resolved)).run())


@server.tool(
    name="routing.propose",
    title="What would you change?",
    description=(
        "A BW_ROLE_* proposal as text, citing bench.query and run.inspect evidence. "
        "`bench_path` is a ggufbench artifact directory under DEBRIEF_BENCH_ROOT, `run_path` "
        "a buildwright log under DEBRIEF_RUN_ROOT. Returns text; never writes."
    ),
)
def routing_propose(bench_path: str, run_path: str) -> ProposalResponse:
    bench_dir = _resolve_within(BENCH_ROOT_ENV, DEFAULT_BENCH_ROOT, bench_path)
    if isinstance(bench_dir, DebriefError):
        return ProposalResponse.of(bench_dir)
    run_file = _resolve_within(RUN_ROOT_ENV, DEFAULT_RUN_ROOT, run_path)
    if isinstance(run_file, DebriefError):
        return ProposalResponse.of(run_file)
    propose = ProposeRole(
        QueryBench(GgufbenchStore(bench_dir)), InspectRun(BuildwrightLog(run_file))
    )
    return ProposalResponse.of(propose.run())


def _resolve_within(root_env: str, default_root: str, requested: str) -> Path | DebriefError:
    """Resolve `requested` against the allowed root; refuse anything that escapes it (A03)."""
    root = Path(os.environ.get(root_env, default_root)).resolve()
    try:
        candidate = (root / requested).resolve() if requested else root
    except (ValueError, OSError) as err:
        # ValueError: embedded NUL bytes survive Path construction and only
        # explode when os calls lstat under resolve(); refuse, never crash.
        return DebriefError(
            code=PATH_OUTSIDE_ROOT,
            message="requested path could not be resolved within the allowed evidence root",
            detail=f"{requested!r}: {err}",
        )
    if not candidate.is_relative_to(root):
        return DebriefError(
            code=PATH_OUTSIDE_ROOT,
            message="requested path is outside the allowed evidence root",
            detail=f"{requested!r} resolves outside {root}",
        )
    return candidate


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("DEBRIEF_LOG_LEVEL", "INFO"),
        stream=sys.stderr,
        format="%(levelname)s %(name)s %(message)s",
    )
    log.info("debrief MCP server starting on stdio (read-only)")
    try:
        server.run()
    except KeyboardInterrupt:
        # Ctrl+C on a stdio server is a normal shutdown, not a crash: exit
        # quietly with the conventional SIGINT code instead of a traceback.
        log.info("debrief MCP server stopping (SIGINT)")
        raise SystemExit(130) from None
