"""MCP stdio adapter: three tools that answer from receipts and never write (R1, R2).

Tool names carry the port (bench.*, run.*, routing.propose) so an agent cannot
confuse what was measured with what happened in one run (ADR-0002).
"""

from __future__ import annotations

import importlib.metadata
import logging
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

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

_HELP = f"""\
debrief-mcp {importlib.metadata.version("debrief-mcp")} — answer agent questions from receipts
MCP stdio server, read-only: every answer is findings or a structured error; never writes.

usage: debrief [-h | --help] [--version]

tools (MCP stdio, JSON-RPC over stdin/stdout; logs go to stderr):

  bench.query      What did ggufbench measure? Findings from ggufbench artifacts.
                   arg: path — run directory (or the artifact root itself) relative
                   to the bench root.
  run.inspect      Where did a buildwright run break? Findings from one run log.
                   arg: path — the log file relative to the run root.
  routing.propose  A BW_ROLE_* proposal as text citing both ports' evidence.
                   args: bench_path (ggufbench artifacts dir), run_path (run log).
                   Text only; never applied (ADR-0001), targets roles, never
                   models.yaml (ADR-0003); incomparable rows are refused, never
                   averaged (ADR-0004).

environment:

  DEBRIEF_BENCH_ROOT  allowed root for ggufbench artifacts
                      (default: {DEFAULT_BENCH_ROOT})
  DEBRIEF_RUN_ROOT    allowed root for buildwright run logs
                      (default: {DEFAULT_RUN_ROOT})
  DEBRIEF_LOG_LEVEL   stderr logging level (default: INFO)

options:

  -h, --help     show this help and exit
  --version      show the installed debrief version and exit

exit codes:

  0    normal (help/version, or the client closed the session)
  2    unknown argument
  130  interrupted (SIGINT)
"""

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


# Every debrief tool is read-only (R1): findings or a proposal as text, no
# writes, no network — hosts use these hints to warn before invoking.
_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


@server.tool(
    name="bench.query",
    title="What did ggufbench measure?",
    description=(
        "Findings from ggufbench artifacts. `path` is a run directory (or the artifact root "
        "itself) relative to DEBRIEF_BENCH_ROOT. Read-only."
    ),
    annotations=_READ_ONLY,
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
    annotations=_READ_ONLY,
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
    annotations=_READ_ONLY,
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


def _on_sigint(signum: int, frame: object) -> None:
    # Ctrl+C on a stdio server is a normal shutdown, not a crash. Exit
    # immediately with the conventional SIGINT code: os._exit skips the
    # interpreter shutdown, where a still-running SDK thread would otherwise
    # turn a second Ctrl+C into an "Exception ignored" traceback.
    log.info("debrief MCP server stopping (SIGINT)")
    sys.stderr.flush()
    os._exit(130)


def main() -> None:
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(_HELP, end="")
        return
    if "--version" in args:
        print(f"debrief-mcp {importlib.metadata.version('debrief-mcp')}")
        return
    if args:
        # The server takes no positional input: anything else is a typo that
        # should fail fast instead of silently starting a stdio session that
        # would then hang waiting for JSON-RPC on the terminal.
        print(
            f"debrief: unrecognized argument(s): {' '.join(args)}\ntry 'debrief --help'",
            file=sys.stderr,
        )
        raise SystemExit(2)

    logging.basicConfig(
        level=os.environ.get("DEBRIEF_LOG_LEVEL", "INFO"),
        stream=sys.stderr,
        format="%(levelname)s %(name)s %(message)s",
    )
    log.info("debrief MCP server starting on stdio (read-only)")
    signal.signal(signal.SIGINT, _on_sigint)
    server.run()
