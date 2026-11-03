# Design: debrief_run_inspect

## Context

S2 slice of the debrief parent, gated inside it. The agent names one buildwright
run log; the tool answers that episode's findings. ADR-0001 (debrief never
writes) and ADR-0002 (two ports, one Finding — the adapter is the only place
that knows a source's format) govern the shape. S3's ProposeRole later consumes
this slice's findings, so the answer currency is `Finding`, never raw log lines.

Note: the parent's S2 batch left `src/debrief/adapters/buildwright_log.py` with
a Python-2-style `except FileNotFoundError, NotADirectoryError:` clause —
invalid syntax, module currently unimportable. Repairing that clause is part of
this slice.

## Approach

Call chain: `run.inspect(path)` MCP tool → path guard `_resolve_within`
(`DEBRIEF_RUN_ROOT`, default `artifacts/buildwright`) →
`InspectRun(BuildwrightLog(resolved))` → `FindingsResponse`. The use case is a
passthrough over the RunLog port; all format knowledge and refusal decisions
live in the adapter; errors are returned, never raised, so the transport can
always render a typed response.

### Run log format decisions (a stranger could not reinvent these)

- Header lines `key: value` (`run:`, `engine_build:`, `task:`, `roles:`,
  `result:`) followed by one `step:` line per logged step:
  `step: NN role=R model=M outcome=pass|fail reason="..." evidence=E`.
- One step line maps to exactly one Finding (model, task from the header,
  outcome, reason, evidence, role); `signature` and `measure` stay `None` —
  a run is one episode, not a measurement, so run findings never carry bench
  knowledge (ADR-0002, ADR-0004).
- A headers-only log (task header but no `step:` lines) is `source_unparseable`,
  never `[]` — an empty list would read as "nothing broke" and flip S3's
  proposal to the all-passed claim even when the log's own `result:` header
  declares a failure.
- `outcome` is validated against `{pass, fail}` at this boundary (validate at
  the boundary, trust types inside).
- The optional `result:` header is evidence too: `result: pass` over a logged
  failure, or a `failed_steps` list that does not match the logged failing
  ordinals (zero-padding tolerated), refuses the log as `source_unparseable`.
  Producers without the header still parse.
- Existence is probed with `stat()`, not `is_file()`: a log behind an unreadable
  parent directory is `source_unparseable`, not mislabeled missing.

## Files to create or modify

| Path | Change |
|---|---|
| `src/debrief/adapters/buildwright_log.py` | RunLog adapter: probe, parse, map, refuse (incl. repairing the broken except clause) |
| `src/debrief/use_cases.py` | `InspectRun` over RunLog (exists; verify passthrough only, no format knowledge leaks in) |
| `src/debrief/mcp_server.py` | `run.inspect` tool: path under `DEBRIEF_RUN_ROOT`, answers `FindingsResponse` (exists; verify wiring) |
| `src/debrief/ports.py` | `RunLog` protocol (exists; unchanged) |
| `tests/test_run.py` | slice behavior tables on real fixtures |
| `tests/fixtures/buildwright/` | real log fixtures incl. corrupt variants |

## Public signatures

```python
class BuildwrightLog:  # implements RunLog
    def __init__(self, log_file: Path) -> None: ...
    def findings(self) -> list[Finding] | DebriefError: ...


class InspectRun:
    def __init__(self, run_log: RunLog) -> None: ...
    def run(self) -> list[Finding] | DebriefError: ...


@server.tool(name="run.inspect")
def run_inspect(path: str) -> FindingsResponse: ...


RUN_ROOT_ENV = "DEBRIEF_RUN_ROOT"  # default root: artifacts/buildwright
```

## Exceptions and error cases

| Condition | Error code | Refs |
|---|---|---|
| Requested path escapes the run root, or is unresolvable (embedded NUL) | `path_outside_root` | R1, R4 |
| No regular file at the resolved path | `run_source_missing` | R1, R4 |
| File exists but is unreadable or undecodable | `source_unparseable` | R1 |
| No task header, no step lines, malformed step line, outcome token outside the enum, `result:` header contradicting the logged steps | `source_unparseable` | R4 |

Every error is returned as `DebriefError(code, message, detail)`, never raised
(R1); content that is not a buildwright run log yields a structured error, not
invented findings (R4).

## Discarded alternatives

- **One generic artifact reader for bench and run** — rejected: the two formats
  diverge and ADR-0002 keeps each source's format inside its own adapter; a
  shared parser would couple the ports.
- **Answer `[]` for a headers-only log** — rejected: silently claims a clean run
  for a possibly truncated log, contradicting the log's own `result:` header.
- **Parse the log in the MCP tool or the use case** — rejected: format knowledge
  stays in the adapter so the domain stays transport-free and S3 consumes
  findings without reparsing.
- **Fill `signature`/`measure` on run findings** — rejected: an episode has no
  task signature; forging one would feed the comparability rule a fake basis
  (ADR-0004).

## Test strategy

Real fixtures, no mocks (walking-skeleton discipline). `tests/test_run.py`:

- mapping: the 3-step broken-run fixture answers three findings with roles,
  task, reason, evidence intact; a passing run answers pass findings; run
  findings carry no bench fields (`signature`/`measure` are `None`).
- refusals (parametrized): missing log, truncated step line, no task header,
  undecodable bytes, outcome tokens outside the enum — structured error with
  the expected stable code, non-empty message and detail.
- format edge tables via `tmp_path`: headers-only log; `result:` header in
  agreement and in each contradiction mode; zero-padding tolerance.
- tool path guard (parametrized): in-root path answers findings; outside root,
  NUL-suffixed and missing paths answer the expected error code.
- unreadable-parent probe case (`skipif` root).

R2 is proved two ways: fixtures are byte-identical (contents and mtime) after
serving, and the slice's read path contains no write-mode opens. Mechanical
gates (`harness/init.sh`, `uv run pytest tests`, ruff, `mypy --strict`) green
before the Completion Gate, with the demo note (command + output) recorded in
the slice's approval record.
