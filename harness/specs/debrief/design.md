# Design: debrief (parent)

MCP server: answers from receipts (bench = ggufbench artifacts, run = buildwright log, propose = role diff). Hexagonal: adapter -> port -> domain. Domain has no outward deps and no write path.

ADRs: 0001 never writes; 0002 two ports, one Finding; 0003 roles not registry; 0004 refuse incomparable rows.

## Slice Map

| Slice | Feature (part_of: debrief) | Outcome |
|---|---|---|
| S1 | debrief_bench_query | agent asks what ggufbench measured -> findings from real artifacts |
| S2 | debrief_run_inspect | agent asks where a run broke -> structured findings |
| S3 | debrief_role_propose | agent gets BW_ROLE_* proposal citing both ports, text only |

S1 is the walking skeleton (real path, no mocks). Parent done after S3 Completion Gate + demo (R9).

## Approach

- Domain: `Finding` (shared currency) + comparability rule. No writes, no ggufbench/buildwright/mcp imports.
- Driving: one use case per question: QueryBench, InspectRun, ProposeRole. MCP stdio tools + thin CLI for demos.
- Driven: BenchStore, RunLog ports; adapters read-only.
- ProposeRole composes both ports and renders BW_ROLE_* diff as text (S3 only).

## Files (package src/debrief/, entry debrief = debrief:main)

| Path | Change | Slice |
|---|---|---|
| errors.py | DebriefError (code, message, detail) | S1 |
| domain.py | Finding, comparability rule | S1 |
| ports.py | BenchStore, RunLog protocols | S1, S2 |
| use_cases.py | QueryBench, InspectRun, ProposeRole | S1-S3 |
| adapters/ggufbench_store.py | read ggufbench artifacts | S1 |
| adapters/buildwright_log.py | read one run log | S2 |
| mcp_server.py | MCP stdio adapter + main() | S1-S3 |
| pyproject.toml | add mcp dependency | S1 |
| feature_list.json | add 3 slice entries | parent |
| tests/ | per-slice tests on real fixtures | S1-S3 |

## Signatures

```python
@dataclass(frozen=True)
class DebriefError:
    code: str; message: str; detail: str

@dataclass(frozen=True)
class Finding:
    model: str; task: str; outcome: str; reason: str; evidence: str

class BenchStore(Protocol):
    def findings(self) -> list[Finding] | DebriefError: ...
class RunLog(Protocol):
    def findings(self) -> list[Finding] | DebriefError: ...

class QueryBench:
    def __init__(self, store: BenchStore): ...
    def run(self) -> list[Finding] | DebriefError: ...
class InspectRun:
    def __init__(self, log: RunLog): ...
    def run(self) -> list[Finding] | DebriefError: ...
class ProposeRole:
    def __init__(self, bench: QueryBench, run: InspectRun): ...
    def run(self) -> str | DebriefError: ...  # text only
```

Error codes: bench_source_missing, run_source_missing, source_unparseable, incomparable_rows.

## Tests

Real fixtures under tests/ (ggufbench artifact tree, run log excerpt); no mocks. Walking skeleton.
Gates per slice (R8). Traceability via check-traceability.py. Demo note at Completion Gate (R11).
