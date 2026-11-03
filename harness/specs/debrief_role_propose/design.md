# Design: debrief_role_propose

## Context

S3 slice of the debrief parent, gated inside it. `routing.propose` is the only
place the two ports may cross (ADR-0002): it composes the S1/S2 use cases
(QueryBench + InspectRun) and renders a `BW_ROLE_*` diff as text (ADR-0001:
debrief never writes, so the answer is printable, not applied; ADR-0003: the
role-assignment layer, never the models.yaml registry). Comparability is the
domain's one rule (ADR-0004): a bench row only ranks against rows sharing its
task signature. Reconciliation note: ADR-0004's prose says the refusal is "a
structured finding, not an error"; the parent requirement R7 and the shared
`DebriefError` currency make it a *returned* structured error (`code:
incomparable_rows`, message + detail naming every signature key) — returned,
never raised, exactly like every other debrief refusal.

Note: both adapters currently carry a Python-2-style
`except FileNotFoundError, NotADirectoryError:` clause — invalid syntax, the
modules are unimportable and every gate is red until the clauses are repaired.
Repairing both is part of this slice (same situation the S2 slice inherited).

## Approach

Call chain: `routing.propose(bench_path, run_path)` MCP tool → `_resolve_within`
twice (`DEBRIEF_BENCH_ROOT`, default `artifacts/ggufbench`; `DEBRIEF_RUN_ROOT`,
default `artifacts/buildwright`) → `ProposeRole(QueryBench(GgufbenchStore(dir)),
InspectRun(BuildwrightLog(file)))` → `ProposalResponse{proposal, error}`.
Errors are returned, never raised, so the transport always renders a typed
response (R1); either port's structured error is the **whole** answer — never
proposal text with an error buried in it.

### Proposal rendering decisions (a stranger could not reinvent these)

- Only failing run steps generate proposals. A run whose logged steps all pass
  answers the literal line `no proposal: every logged step passed` — success
  text, not an error.
- Role canonicalization: uppercase the step's role token and strip an existing
  `BW_ROLE_` prefix, so `role=BW_ROLE_WORKER` (as written in the log's
  `roles:` header) and `role=worker` render the same one clean
  `BW_ROLE_WORKER=` diff; `BW_ROLE_BW_ROLE_*` can never appear; one proposal
  per canonical role.
- Cohort = bench rows for the same task as the failed step; comparability goes
  through the domain's `shared_signature` (the one ADR-0004 rule). Candidates
  are passing rows with a different model and a finite measure; winner =
  highest measure, model name as tiebreak.
- Every proposal block carries: a `proposal:` summary line, the `- `/`+ ` env
  diff lines, `why run:` (failure reason + evidence), `why bench:` (winner
  score + evidence), the `signature:` key, and a fixed `not applied:` line
  citing ADR-0001/ADR-0003 — a pasteable diff, never applied.
- Keep-the-role cases are notes, not refusals: bench never measured the task,
  no passing candidate in the cohort, or the failed step recorded no role —
  each renders `note: ... keeping BW_ROLE_<ROLE>=<current model>`.
- An incomparable cohort (rows spanning signatures, or none carrying one) makes
  the `incomparable_rows` error the whole answer: no winner, no average, and
  the detail names every signature key so the caller can pick a cohort (R7).
- Text-forgery defense (R6 under attack): the adapters validate every
  artifact/log string field at the boundary — identifier-like fields are
  single-line whitespace-free tokens, free-text fields are single lines with no
  control characters (the rule is `str.splitlines()`, so U+0085/U+2028/U+2029
  are caught too) — and scores must be finite floats. A poisoned artifact
  therefore refuses as `source_unparseable` and the caller sees a structured
  error, never proposal text, so no forged `- `/`+ ` diff or `models.yaml` line
  can ride into the output.
- Read-only proof (R2): the adapters open files for reading only and the
  proposal is rendered text, nothing persisted; tests assert fixtures are
  byte-identical (contents + mtime) after serving and that the slice's read
  path contains no write-mode opens.

## Files to create or modify

| Path | Change |
|---|---|
| `src/debrief/use_cases.py` | `ProposeRole` composing QueryBench + InspectRun, `_propose` rendering, `_canonical_role` (exists; complete/verify per Approach) |
| `src/debrief/domain.py` | `shared_signature` comparability rule (exists; unchanged) |
| `src/debrief/mcp_server.py` | `routing.propose` tool + `ProposalResponse` + both path guards (exists; verify wiring) |
| `src/debrief/adapters/ggufbench_store.py` | repair the invalid except clause; single-line/finite-field validation stays here (exists; repair) |
| `src/debrief/adapters/buildwright_log.py` | repair the invalid except clause (exists; repair) |
| `src/debrief/errors.py` | `INCOMPARABLE_ROWS` code (exists; unchanged) |
| `tests/test_propose.py` | slice behavior tables on real fixtures |
| `tests/fixtures/ggufbench/`, `tests/fixtures/buildwright/` | real fixtures incl. corrupt variants (exist; extend only if a table needs one) |

## Public signatures

```python
class ProposeRole:
    def __init__(self, bench: QueryBench, run: InspectRun) -> None: ...
    def run(self) -> str | DebriefError: ...  # text only


@server.tool(name="routing.propose")
def routing_propose(bench_path: str, run_path: str) -> ProposalResponse: ...


@dataclass(frozen=True)
class ProposalResponse:
    proposal: str = ""
    error: DebriefError | None = None

    @classmethod
    def of(cls, answer: str | DebriefError) -> ProposalResponse: ...


def shared_signature(rows: Sequence[Finding]) -> TaskSignature | DebriefError: ...
```

## Exceptions and error cases

| Condition | Error code | Refs |
|---|---|---|
| `bench_path` or `run_path` escapes its evidence root, or is unresolvable (embedded NUL) | `path_outside_root` | R1 |
| No ggufbench artifacts / no `results.json` under the bench path | `bench_source_missing` | R1 |
| No regular run log at the run path | `run_source_missing` | R1 |
| Unreadable/undecodable bytes, non-JSON artifact, malformed step or row, outcome token outside the enum, `result:` header contradicting the logged steps, non-finite score, multi-line or control-char field | `source_unparseable` | R1, R6 |
| Bench cohort rows span more than one task signature, or none carries one | `incomparable_rows` | R7 |
| Every logged step passed | not an error: the literal `no proposal: every logged step passed` text | R5 |

Every error is returned as `DebriefError(code, message, detail)`, never raised
(R1); an incomparable cohort is never averaged or silently narrowed to a
homogeneous subset (R7).

## Discarded alternatives

- **Average and flag, or silently pick the largest homogeneous cohort**
  (ADR-0004's rejected alternatives) — rejected: the number travels, the
  warning does not; the refusal names all signatures so the caller chooses.
- **Render refusals as proposal prose** (e.g., a note inside the diff) —
  rejected: R7 requires a typed error an agent branches on; prose can be
  mistaken for a diff.
- **Propose `models.yaml` edits alongside role diffs** — rejected: mixes the
  registry with the assignment layer (ADR-0003); a registry gap is named as a
  note, never an edit.
- **Write the proposal flag-gated** — rejected: ADR-0001 and R2; the `+ ` line
  is meant for a human to paste.
- **ProposeRole calling the adapters directly** — rejected: composition must
  reuse the S1/S2 use cases and their error handling (ADR-0002); direct adapter
  calls would fork the read path.

## Test strategy

Real fixtures, no mocks (walking-skeleton discipline). `tests/test_propose.py`:

- happy path (R5): the real broken run + matching bench run answer the full
  diff text — `proposal:` line, `- `/`+ ` lines, `why run:`/`why bench:`,
  `signature:` key, `not applied:` line.
- targeting (R6): every `- `/`+ ` line names `BW_ROLE_*`; no `models.yaml`
  change anywhere in the answer.
- role-token table (R5, R6): `worker`, `WORKER`, `BW_ROLE_WORKER`,
  `bw_role_worker` all render the same canonical diff; `BW_ROLE_BW_ROLE_`
  never appears.
- incomparable rows (R7): a bench root spanning two baselines refuses with
  `incomparable_rows` naming both signature keys, at use-case and tool level.
- refusal propagation (R1, R6): missing bench, missing run, poisoned string
  fields (newline- and Unicode-separator-forged `- `/`+ ` lines incl. a
  `models.yaml` forge), non-finite scores, outcome tokens outside the enum,
  step-stripped and result-header-lying logs — all answer structured errors,
  never proposal text.
- keep-the-role notes (R5): unmeasured task, no passing candidate, role-less
  step; all-passed run answers the exact no-proposal text.
- tool guards (R1): NUL and outside-root refuse for either argument with
  `path_outside_root`.
- read-only (R2): fixtures byte-identical (contents + mtime) after serving;
  no write-mode opens on the slice's path.

Mechanical gates per parent R8 (`harness/init.sh`, `uv run pytest tests`,
ruff, `mypy --strict`, audit-security, gauntlet) green before the Completion
Gate, with the demo note (command + output) recorded in the slice's approval
record (parent R11).
