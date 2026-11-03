# Design: debrief_bench_query

## Context

S1 slice of `debrief` (part_of: parent feature 1) and its walking skeleton: one real
path end-to-end — ggufbench adapter → BenchStore port → QueryBench use case → MCP
stdio tool `bench.query` — no mocks. ADR-0001 (debrief never writes), ADR-0002 (one
`Finding` currency; format knowledge stays in the adapter), ADR-0004 (task signatures,
not version labels). The `run.*` and `routing.*` tools belong to S2/S3 and are out of
scope here; gates run per slice inside the parent (parent R8).

## Approach

- **Artifact contract** (known only in `adapters/ggufbench_store.py`): layout
  `<DEBRIEF_BENCH_ROOT>/[<run-id>/]results.json`; document
  `{engine_build, baseline, rows: [{model, task, outcome, score, reason, artifact, graded: {dimension: count}}]}`;
  `outcome` ∈ {pass, fail}. Identifier-like fields (model, task, engine_build,
  baseline, graded dimensions) are single-line whitespace-free tokens; free-text fields
  (reason, artifact) are single-line control-char-free — artifact strings reach
  proposal text verbatim in S3, so line forgery is refused at this boundary. Scores
  must be finite floats (bool/int-overflow/NaN/Infinity refused).
- **Refusals are returned, never raised**: `DebriefError` values flow back through the
  port so the transport adapter can always render a typed findings-or-error response (R1).
- **Boundary validation**: `mcp_server._resolve_within` resolves `path` against
  `DEBRIEF_BENCH_ROOT` (default `artifacts/ggufbench`), resolving symlinks and refusing
  escapes and NUL bytes (`PATH_OUTSIDE_ROOT`); the adapter re-checks containment for
  every `results.json` it finds, so a symlinked row file cannot read outside the root (R3).

## Files to create or modify

| Path | Change |
|---|---|
| `src/debrief/errors.py` | `DebriefError` (code, message, detail) + codes BENCH_SOURCE_MISSING, SOURCE_UNPARSEABLE, PATH_OUTSIDE_ROOT |
| `src/debrief/domain.py` | `Finding`, `TaskSignature`, `OUTCOMES`, `shared_signature` (comparability; composed by S3) |
| `src/debrief/ports.py` | `BenchStore` protocol (`RunLog` declared, implemented in S2) |
| `src/debrief/use_cases.py` | `QueryBench` |
| `src/debrief/adapters/ggufbench_store.py` | read-only ggufbench artifact adapter |
| `src/debrief/mcp_server.py` | MCP stdio server, `bench_query` tool, `_resolve_within`, `main()` |
| `pyproject.toml` | add `mcp` dependency; console script `debrief = debrief:main` |
| `tests/test_bench.py`, `tests/fixtures/ggufbench*` | real-fixture tests (see Test strategy) |

## Public signatures

```python
@dataclass(frozen=True)
class DebriefError:
    code: str
    message: str
    detail: str


@dataclass(frozen=True)
class TaskSignature:
    graded_counts: tuple[tuple[str, int], ...]
    baseline: str
    engine_build: str

    @classmethod
    def of(cls, graded: Mapping[str, int], baseline: str, engine_build: str) -> TaskSignature: ...
    @property
    def key(self) -> str: ...


@dataclass(frozen=True)
class Finding:
    model: str
    task: str
    outcome: str  # "pass" | "fail"
    reason: str
    evidence: str
    signature: TaskSignature | None = None
    measure: float | None = None
    role: str | None = None  # filled by the run port (S2), never by bench


class BenchStore(Protocol):
    def findings(self) -> list[Finding] | DebriefError: ...


class QueryBench:
    def __init__(self, store: BenchStore) -> None: ...
    def run(self) -> list[Finding] | DebriefError: ...


@dataclass(frozen=True)
class FindingsResponse:
    findings: list[Finding]
    error: DebriefError | None


def bench_query(path: str) -> FindingsResponse: ...
def main() -> None: ...  # MCP stdio entry point
```

## Exceptions and error cases

| Condition | Returned error | Requirement |
|---|---|---|
| Requested path resolves outside the evidence root, or contains NUL bytes | `PATH_OUTSIDE_ROOT` | R1 |
| Root absent, or no `results.json` under any run directory | `BENCH_SOURCE_MISSING` | R1 |
| `results.json` unreadable, invalid JSON, nesting bomb, wrong schema, outcome outside the enum, non-finite/overflowing score, line-forging field, symlink escaping the root, unreadable directory | `SOURCE_UNPARSEABLE` | R1, R3 |

## Discarded alternatives

- **In-memory/mock BenchStore for S1** — rejected: S1 is the walking skeleton; findings
  must come from real artifacts (R3).
- **Returning raw artifact JSON rows to the agent** — rejected: `Finding` is the shared
  currency of both ports and of routing.propose (ADR-0002); adapters own the format.
- **Raising exceptions across the port** — rejected: a returned `DebriefError` keeps
  every response total (findings or structured error, R1) and typed.
- **Caching parsed artifacts at serve time** — rejected: adds state and a write
  temptation; every call re-reads receipts (R2, ADR-0001).

## Test strategy

Real fixtures under `tests/fixtures/ggufbench` (happy path, one run dir and the root
scan) and `tests/fixtures/ggufbench_broken` (refusal tree), plus `tmp_path` fixtures for
hostile bytes and symlink escapes; parametrized reject tables. Static check: no
`src/debrief` module contains a write marker; runtime check: a `bench.query` call leaves
the artifact tree byte-identical (R2). Tool-level tests drive `bench_query` with
`DEBRIEF_BENCH_ROOT` set. Gates: `uv run pytest tests`, `ruff`, `mypy --strict`;
traceability via `harness/tools/check-traceability.py`; demo through an MCP client at
the Completion Gate (parent R11).
