# Implementation log — debrief_role_propose

feature: debrief_role_propose

## Traceability

| Req | Tests | Implementation file(s) | Status |
|-----|-------|------------------------|--------|
| R1 | tests/test_propose.py::test_propose_role_propagates_structured_errors_from_both_ports, tests/test_propose.py::test_routing_propose_answers_a_poisoned_bench_cohort_with_a_structured_error, tests/test_propose.py::test_routing_propose_tool_refuses_nul_bytes_in_path_arguments, tests/test_bench.py::test_regular_file_where_a_run_dir_should_be_refuses_as_missing_not_crashing, tests/test_run.py::test_log_path_through_a_regular_file_parent_refuses_as_missing_not_crashing | src/debrief/errors.py, src/debrief/use_cases.py, src/debrief/adapters/ggufbench_store.py, src/debrief/adapters/buildwright_log.py, src/debrief/mcp_server.py | done |
| R2 | tests/test_propose.py::test_serving_routing_propose_leaves_the_slice_fixtures_byte_identical, tests/test_propose.py::test_routing_propose_read_path_has_no_write_mode_open_or_mutation, tests/test_propose.py::test_the_slice_write_gate_flags_every_write_shape, tests/test_propose.py::test_the_slice_write_gate_passes_every_read_shape, tests/test_run.py::test_serving_run_inspect_leaves_the_run_fixtures_byte_identical, tests/test_run.py::test_run_inspect_read_path_has_no_write_mode_open_or_mutation, tests/test_bench.py::test_no_debrief_module_contains_a_write_path | src/debrief/adapters/*, src/debrief/use_cases.py, src/debrief/mcp_server.py | done |
| R5 | tests/test_propose.py::test_propose_role_diffs_the_failed_role_to_the_bench_winner, tests/test_propose.py::test_role_tokens_carrying_the_env_prefix_still_render_a_pasteable_diff, tests/test_propose.py::test_propose_role_reports_when_no_step_failed, tests/test_propose.py::test_propose_renders_a_keep_the_role_note_and_no_diff_for_every_keep_case | src/debrief/use_cases.py | done |
| R6 | tests/test_propose.py::test_proposal_diff_lines_target_bw_roles_only, tests/test_propose.py::test_poisoned_bench_fields_never_reach_the_proposal_output, tests/test_propose.py::test_routing_propose_answers_a_poisoned_bench_cohort_with_a_structured_error | src/debrief/adapters/ggufbench_store.py, src/debrief/use_cases.py | done |
| R7 | tests/test_propose.py::test_propose_role_refuses_rows_spanning_two_baselines, tests/test_propose.py::test_propose_refuses_a_cohort_where_no_row_carries_a_signature, tests/test_propose.py::test_propose_refuses_a_spanning_cohort_instead_of_ranking_the_other_signature, tests/test_propose.py::test_routing_propose_tool_refuses_a_spanning_cohort_with_no_proposal_text, tests/test_propose.py::test_routing_propose_tool_refuses_incomparable_rows | src/debrief/domain.py, src/debrief/use_cases.py, src/debrief/mcp_server.py | done |

## Dispatch batch-1: T1, T2, T3 (2026-11-03)

Starting state: the parent `debrief` feature (status done) already landed the S3
surface — `ProposeRole` in `src/debrief/use_cases.py`, the `routing.propose` tool
in `src/debrief/mcp_server.py`, both adapters, and `tests/test_propose.py` with
the `tests/fixtures/` trees — at 108 tests green. This batch therefore repaired,
completed and verified the slice surface rather than creating files from scratch.

### T1 — except-clause repair + boundary validations (refs R1, R6)

**Except clauses.** The design note calls
`except FileNotFoundError, NotADirectoryError:` "invalid syntax, the modules are
unimportable". On this repo's pinned toolchain that premise is false:
`requires-python >= 3.14` / `.python-version` 3.14.7, where PEP 758 makes the
unparenthesized clause valid and tuple-catching. Evidence collected this batch:

- `uv run python -c "import debrief.adapters.ggufbench_store,
  debrief.adapters.buildwright_log"` → imports clean (exit 0);
- live probes of both clauses' second arm: a run-dir candidate whose parent
  component is a regular file raises `NotADirectoryError` on `stat()`, and
  `GgufbenchStore.findings()` answers `bench_source_missing` /
  `BuildwrightLog.findings()` answers `run_source_missing` — no raw exception
  escapes (R1);
- the S2 slice's reviewer-approved precedent
  (`harness/progress/impl_debrief_run_inspect.md`, Dispatch batch-1) resolved the
  same conflict: parenthesizing breaks `ruff format --check .` on the py314
  target and the parent's gauntlet round 8 ruled "the formatter is the canon";
  `ggufbench_store.py` carries the identical clause. Both clauses stay in the
  formatter-canonical PEP 758 form; the repair the spec actually wants (both
  modules importable, both exception types caught) holds and is now pinned by
  tests.

Tests added:

- `tests/test_bench.py::test_regular_file_where_a_run_dir_should_be_refuses_as_missing_not_crashing`
  — the `NotADirectoryError` arm of `_is_regular_file` through the public store
  path (structured `bench_source_missing`, not a crash); the `FileNotFoundError`
  arm was already pinned by `test_query_bench_refuses_with_structured_error[id=no_results_under_root]`.
- `tests/test_run.py::test_log_path_through_a_regular_file_parent_refuses_as_missing_not_crashing`
  — the `NotADirectoryError` arm of `findings()` (`run_source_missing`); the
  `FileNotFoundError` arm was already pinned by
  `test_inspect_run_refuses_with_structured_error[id=missing_log]`.

**Boundary validations the proposal text depends on** — audited in
`src/debrief/adapters/ggufbench_store.py` and found complete:
`_required_token` (single-line whitespace-free tokens for model/task/baseline/
engine_build/graded dimensions; the `\S+` fullmatch provably rejects
U+0085/U+2028/U+2029), `_required_line` (free text single-line via
`value.splitlines() == [value]`, so all three Unicode separators are caught, plus
the `< 0x20`/`0x7F` control-char refusal), and `_map_row`'s finite-float gate
(`math.isfinite` + `OverflowError` → `source_unparseable`). The run adapter's
step grammar yields single-line fields by construction (`read_text().splitlines()`
up front; `\S+` tokens reject the Unicode separators; a separator inside a quoted
`reason` splits the line so it no longer matches `_STEP_RE`).

Tests added:

- `tests/test_bench.py`: `reason`/`artifact` forge rows through U+0085 (the one
  separator the forge table did not name yet) in
  `test_bench_refuses_string_fields_that_could_forge_proposal_lines`; the
  U+2029 row was renamed `unicode_paragraph_separator` for accuracy.
- `tests/test_propose.py::test_routing_propose_answers_a_poisoned_bench_cohort_with_a_structured_error`
  (table: newline forge, U+2029 `models.yaml` forge) — end-to-end through the
  `routing.propose` tool boundary: the poisoned cohort answers
  `source_unparseable` and `proposal == ""`, so no forged `- `/`+ `/models.yaml
  line is ever rendered (R6). Complements the existing use-case-level table
  `test_poisoned_bench_fields_never_reach_the_proposal_output`.

### Gates after T1

- `uv run pytest tests` → exit 0, **114 passed** (summary line read)
- `uv run ruff check .` → exit 0; `uv run ruff format --check .` → exit 0
  (54 files already formatted); `uv run mypy --strict` → exit 0
- `bash harness/init.sh` → exit 0, final line `[OK]`

T1 ticked in `harness/specs/debrief_role_propose/tasks.md`.

### T2 — ProposeRole composition, error propagation, diff rendering (refs R5, R1)

Audited `ProposeRole` / `_propose` / `_canonical_role` in
`src/debrief/use_cases.py` against every T2 clause — all present, no code change
needed:

- composition is the only port-crossing use case: `ProposeRole(QueryBench, InspectRun)`
  calls only the S1/S2 use cases' `run()` (never the adapters, ADR-0002);
- either port's structured error is returned as the whole answer
  (bench answer checked first, run answer second);
- only `outcome == FAIL` run steps propose; an all-passing run answers the
  literal `no proposal: every logged step passed`;
- `_canonical_role` uppercases and strips a leading `BW_ROLE_` before
  deduplicating, so `worker` / `WORKER` / `BW_ROLE_WORKER` / `bw_role_worker`
  all render one clean `BW_ROLE_WORKER=` diff and `BW_ROLE_BW_ROLE_*` cannot
  appear; one proposal per canonical role (`proposed_roles` set);
- each block carries `proposal:` / `- `/`+ `/`why run:`/`why bench:`
  (winner score + evidence) / `signature:` / the fixed `not applied:` line
  citing ADR-0001/ADR-0003; keep-the-role notes for unmeasured task, no passing
  candidate, role-less step.

Tests added (`tests/test_propose.py`):

- notes table
  `test_propose_renders_a_keep_the_role_note_and_no_diff_for_every_keep_case`
  (ids `unmeasured_task`, `no_passing_candidate`, `roleless_step`): asserts the
  exact note text, that no `- `/`+ ` diff line and no `models.yaml` mention
  appears in a keep-the-role answer. Driven through the real `ProposeRole` use
  case over a `_StaticRows` port double because the role-less state is
  unreachable from fixtures — the buildwright step grammar always records
  `role=`, so no log can carry it (documented in the test double's docstring;
  the unmeasured/no-passing cases additionally stay pinned by the existing
  real-fixture tests).
- `no_passing_candidate` uses the sharper same-model case: a *passing* bench row
  for the failing model itself must not become its own winner (`row.model !=
  failure.model` filter), which no fixture expressed.
- port-error propagation table extended with
  `bench_refuses_a_nonfinite_score` (`source_unparseable` from the bench port)
  and `run_refuses_a_truncated_step` (`source_unparseable` from the run port);
  the body now also asserts the error is the whole answer
  (`not isinstance(answer, str)`, message + detail non-empty).

Existing coverage verified complete against the task list: happy-path diff from
the real fixtures (`test_propose_role_diffs_the_failed_role_to_the_bench_winner`),
role-token table (bare/uppercase/prefixed/lowercase-prefixed, `BW_ROLE_BW_ROLE_`
absent), all-passed literal text, tool-level demo diff.

### Gates after T2

- `uv run pytest tests` → exit 0, **119 passed**
- `uv run ruff check .` → exit 0; `uv run ruff format --check .` → exit 0;
  `uv run mypy --strict` → exit 0
- `bash harness/init.sh` → exit 0, final line `[OK]`

T2 ticked in `harness/specs/debrief_role_propose/tasks.md`.

### T3 — comparability refusal + role targeting (refs R7, R6)

Audited the comparability path against every T3 clause — no code change needed:

- the cohort's signature goes through the domain's `shared_signature`
  (`src/debrief/domain.py`), the one ADR-0004 rule; `_role_proposal` calls it on
  the task-filtered bench cohort before any candidate is ranked;
- a cohort spanning signatures, or carrying none, makes the
  `incomparable_rows` structured error the whole answer (returned by
  `_propose`, propagated by `ProposeRole.run()` and `ProposalResponse.of`) —
  never a winner, an average, or a silently narrowed cohort.

Tests added/extended (`tests/test_propose.py`):

- `test_proposal_diff_lines_target_bw_roles_only` extended (R6): besides every
  `- `/`+ ` line starting with `BW_ROLE_`, the answer's only `models.yaml`
  mentions are inside the fixed `not applied:` prose — no line proposes a
  registry change.
- `test_propose_refuses_a_spanning_cohort_instead_of_ranking_the_other_signature`
  (use case, real artifact tree via `_spanning_bench_tree`): the failure's own
  signature holds only the failing model and the top scorer (0.99, `LLAMA`)
  sits in the other baseline — so ranking it would break the rule and silently
  narrowing would drop the only other measured model. Asserts the refusal names
  every signature key and carries no winner: `LLAMA` and `0.99` appear nowhere
  in the answer.
- `test_routing_propose_tool_refuses_a_spanning_cohort_with_no_proposal_text`
  (tool level): same tree through `routing.propose` → `proposal == ""`,
  `error.code == incomparable_rows`, both signature keys named.
- `test_propose_refuses_a_cohort_where_no_row_carries_a_signature` (use case):
  the second `incomparable_rows` arm. Not reachable from real artifacts — the
  bench adapter maps every row with a `TaskSignature` — so it is driven through
  `ProposeRole` over `_StaticRows` with contract-legal signature-less Findings;
  the refusal names the rows.
- Existing tool-level spanning refusal (`test_routing_propose_tool_refuses_incomparable_rows`)
  verified against the real two-baseline fixture root.

Side observation recorded for the reviewer: at tool level a *successful* bench
query followed by a missing run log answers `run_source_missing` (the run port
is inspected before any cohort check, so its refusal is the whole answer) —
correct per R1, and the reason the new tool-level spanning test pins
`RUN_ROOT_ENV` explicitly.

### Gates after T3 (final battery on the batch state)

- `uv run pytest tests` → exit 0, **122 passed**
- `uv run ruff check .` → exit 0; `uv run ruff format --check .` → exit 0;
  `uv run mypy --strict` → exit 0
- `bash harness/init.sh` → exit 0, final line `[OK]`

T3 ticked in `harness/specs/debrief_role_propose/tasks.md`. T4 (tool-wiring
proof, read-only guarantee, slice gates + demo note) intentionally untouched.

## Batch-1 net diff

| File | Change |
|---|---|
| `tests/test_bench.py` | +1 clause test, +2 U+0085 forge rows, 1 row renamed |
| `tests/test_run.py` | +1 clause test |
| `tests/test_propose.py` | +imports/helpers (`_StaticRows`, `_bench_row`, `_run_finding`, `propose_prebuilt`), +notes table (3), +2 propagation rows + whole-answer asserts, +tool-level poison table (2), +spanning refusal (use case + tool), +no-signature refusal, targeting test extended |
| `src/debrief/use_cases.py`, `adapters/*.py`, `domain.py`, `mcp_server.py` | no change needed — parent-slice implementation verified complete against T1–T3 |

Suite: 108 → 122 tests. No fixture files added or modified.

## Dispatch batch-2: T4 (2026-11-03)

### T4 — tool wiring proof, read-only guarantee, slice gates (refs R1, R2) — `tests/test_propose.py`

**Tool wiring proof.** The `routing.propose` wiring itself was verified complete in
`src/debrief/mcp_server.py` (no source change needed): both arguments resolve
through `_resolve_within` — `BENCH_ROOT_ENV`/`DEFAULT_BENCH_ROOT` first, then
`RUN_ROOT_ENV`/`DEFAULT_RUN_ROOT` — each refusal answering `ProposalResponse.of`
(`proposal: ""`, typed error, never raised), the composed
`ProposeRole(QueryBench(GgufbenchStore(bench_dir)), InspectRun(BuildwrightLog(run_file)))`
answering through the same dataclass. Tests added:

- `test_routing_propose_root_contract_is_stable`: pins the agent-facing path
  contract (`DEBRIEF_BENCH_ROOT` / `artifacts/ggufbench`, `DEBRIEF_RUN_ROOT` /
  `artifacts/buildwright`), mirroring the S2 slice's contract test.
- `test_routing_propose_tool_refuses_paths_outside_the_roots` (the refuse
  table): traversal `../pyproject.toml` in either argument, plus the two
  cross-port rows — a bench path naming a run log and a run path naming a
  bench artifact both refuse `path_outside_root` before either port is read
  (ADR-0002 at the path layer). Asserts `proposal == ""`, the code, and the
  detail naming the requested path. Completes the NUL table already pinned by
  `test_routing_propose_tool_refuses_nul_bytes_in_path_arguments`
  (NUL suffix in either argument), together covering NUL + outside-root for
  both arguments.

**Read-only guarantee (R2).**

- `test_serving_routing_propose_leaves_the_slice_fixtures_byte_identical`:
  fingerprints every file under the slice's three fixture roots
  (`tests/fixtures/ggufbench`, `ggufbench_broken`, `buildwright` — 26 files;
  ≥20 asserted so the proof cannot go vacuous) — size, `st_mtime_ns`, sha256 —
  then serves `routing.propose` across the answer space (happy proposal,
  spanning-cohort refusal, all-passed text, bench-missing, run-missing) plus a
  use-case-level poisoned-score serve, and asserts the fingerprint is
  unchanged (contents **and** mtime). Probe-verified teeth on a `tmp`
  fixture *copy* (no repo fixture mutated): a re-fingerprint without mutation
  is stable, an mtime-only `os.utime(+1ms)` flips it, restoring the mtime
  equalizes again, and a content change flips it.
- `test_routing_propose_read_path_has_no_write_mode_open_or_mutation`: AST
  gate over the slice's read path — `adapters/ggufbench_store.py`,
  `adapters/buildwright_log.py`, `use_cases.py`, `mcp_server.py` (the bench
  adapter is new coverage; S2's gate covered the run adapter, use case and
  transport only) — flagging write-mode `open()` (literal or non-literal),
  mutating calls (`write_text`, `write_bytes`, `unlink`, `mkdir`, `rename`,
  `replace`, `remove`, `rmdir`, `rmtree`, `touch`, `truncate`, `chmod`) and
  `shutil` imports. Self-proving teeth live in the suite this time:
  `test_the_slice_write_gate_flags_every_write_shape` (10 rows) and
  `test_the_slice_write_gate_passes_every_read_shape` (5 rows). The teeth
  table caught a real gap while being written: the mode of the bound method
  form (`path.open('w')`) sits in slot 0, not slot 1, so a builtin-shaped
  helper would silently pass it — the S3 gate detects the callee form
  (Attribute → slot 0 when bound-single-arg) before checking the mode.
  Side observation for the reviewer: S2's
  `tests/test_run.py::test_run_inspect_read_path_has_no_write_mode_open_or_mutation`
  keeps the builtin-only shape; its read path has no `Path.open(...)` call, so
  the gap is latent there and left untouched (not this batch's file).

**Slice gates (final battery on the closure state, verbatim in
`harness/logs/debrief_role_propose/batch-1.log`; every gate exit 0):**

- `uv run ruff check .` → "All checks passed!"
- `uv run ruff format --check .` → "55 files already formatted"
- `uv run mypy --strict` → "Success: no issues found in 14 source files"
- `uv run pytest tests` → **144 passed** (summary line read, per
  docs/verification.md; 122 → 144)
- `bash harness/tools/audit-security.sh` → "VERDICT: no HIGH severity findings
  reported by automated tools." (bandit B101 Low/High assert-noise in tests
  only; pip-audit skipped, not installed)
- `bash harness/tools/gauntlet.sh --feature debrief_role_propose` → G1 **PASS**
  (spec trio ok, tasks 4/4 ok, traceability ok)
- `bash harness/init.sh` → exit 0, final line `[OK]` (feature_list valid,
  4 features; "All tests pass", 144 passed)
- `python3 harness/tools/check-traceability.py --feature debrief_role_propose`
  → 5/5, VERDICT PASS, saved verbatim to
  `harness/specs/debrief_role_propose/traceability.txt`.

**Demo note (command + output) recorded in the slice's approval record
`harness/specs/debrief_role_propose/APPROVAL`** (refs R1, R2):

- Command: `DEBRIEF_BENCH_ROOT=$PWD/tests/fixtures/ggufbench
  DEBRIEF_RUN_ROOT=$PWD/tests/fixtures/buildwright uv run debrief` (MCP stdio),
  driven end-to-end by an MCP client (`mcp.ClientSession` → `initialize` →
  `tools/list` → `routing.propose`). Session 1 — eight calls: the happy path
  answering the full pasteable diff (`- `/`+ ` BW_ROLE_WORKER lines, why
  run/why bench, the signature key, the fixed `not applied:` line citing
  ADR-0001/ADR-0003); the `.` root scan answering `incomparable_rows` naming
  both baselines with `proposal: ""`; bench traversal and a NUL-suffixed run
  path answering `path_outside_root`; missing bench/run answering
  `bench_source_missing`/`run_source_missing`; the all-passed run answering the
  literal `no proposal: every logged step passed`. Session 2
  (`DEBRIEF_BENCH_ROOT=tests/fixtures/ggufbench_broken`) — the non-finite
  score cohort answering `source_unparseable`, the poisoned row's model in no
  answer. After both sessions closed the fixture fingerprint was re-checked:
  26 files, `byte-identical (size+mtime_ns+sha256): True` — R2 holds while
  serving.
- Full transcript with command + output (20 assertions, all PASS):
  `harness/logs/debrief_role_propose/demo.log`; the demo note is recorded in
  `harness/specs/debrief_role_propose/APPROVAL` — the slice's approval record,
  left for the human to countersign at the Completion Gate.
- Capture mechanics (both transient drivers deleted before this log was
  written; verified absent): `.capture_demo.py` wrote `demo.log` and
  unlinked itself; the battery was captured by an inline `python -c` driver
  that never existed as a repo file, so the gates scanned the pure closure
  tree (55 files).

T4 ticked in `harness/specs/debrief_role_propose/tasks.md`. Remaining for the
slice's Completion Gate (human, not implementer): countersign APPROVAL, slice
status flip in `harness/feature_list.json`, gauntlet G2–G4 per C8.

## Batch-2 net diff

| File | Change |
|---|---|
| `tests/test_propose.py` | +imports (`ast`, `hashlib`, root-contract constants), +root-contract test, +outside-root refuse table (4 rows incl. 2 cross-port), +fixture byte-identity test, +read-path AST gate with method-form mode detection, +gate teeth tables (10 flag rows, 5 read rows) |
| `harness/specs/debrief_role_propose/APPROVAL` | created: pending countersign header + the T4 demo note (command + output, refs R1, R2, R5–R7) |
| `harness/specs/debrief_role_propose/traceability.txt` | created: check-traceability 5/5 PASS verbatim |
| `harness/logs/debrief_role_propose/demo.log` | created: MCP stdio demo transcript, 20 assertions PASS |
| `harness/logs/debrief_role_propose/batch-1.log` | created: eight-gate battery, verbatim, all exit 0 |
| `harness/progress/impl_debrief_role_propose.md` | R2 traceability row resolved (real test ids, status done); this section |
| `harness/specs/debrief_role_propose/tasks.md` | T4 ticked |
| `src/debrief/*` | no change needed — wiring verified complete against T4 |

Suite: 122 → 144 tests. No fixture files added or modified.
