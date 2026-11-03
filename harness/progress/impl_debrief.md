# Implementation progress — debrief

feature: debrief

## Traceability

| Req | Tests | Implementation file(s) | Status |
|-----|-------|------------------------|--------|
| R1 | tests/test_bench.py::test_query_bench_refuses_with_structured_error, tests/test_run.py::test_inspect_run_refuses_with_structured_error, tests/test_propose.py::test_propose_role_propagates_structured_errors_from_both_ports, tests/test_bench.py::test_bench_refuses_string_fields_that_could_forge_proposal_lines, tests/test_propose.py::test_poisoned_bench_fields_never_reach_the_proposal_output, tests/test_run.py::test_existing_run_log_behind_unreadable_parent_is_unparseable_not_missing | src/debrief/errors.py, src/debrief/mcp_server.py, src/debrief/adapters/ggufbench_store.py, src/debrief/adapters/buildwright_log.py | done |
| R2 | tests/test_bench.py::test_no_debrief_module_contains_a_write_path | src/debrief/ (whole package) | done |
| R3 | tests/test_bench.py::test_bench_row_carries_measure_signature_and_evidence_from_the_artifact | src/debrief/adapters/ggufbench_store.py | done |
| R4 | tests/test_run.py::test_inspect_run_maps_each_logged_step_to_a_finding | src/debrief/adapters/buildwright_log.py | done |
| R5 | tests/test_propose.py::test_propose_role_diffs_the_failed_role_to_the_bench_winner | src/debrief/use_cases.py | done |
| R6 | tests/test_propose.py::test_proposal_diff_lines_target_bw_roles_only, tests/test_propose.py::test_poisoned_bench_fields_never_reach_the_proposal_output | src/debrief/use_cases.py, src/debrief/adapters/ggufbench_store.py | done |
| R7 | tests/test_bench.py::test_shared_signature_refuses_rows_measured_against_different_baselines, tests/test_propose.py::test_propose_role_refuses_rows_spanning_two_baselines | src/debrief/domain.py | done |
| R8 | tests/test_quality_gates.py::test_quality_gate_tooling_is_configured_over_src_and_tests | gates per slice: latest battery harness/logs/debrief/batch-9.log (init.sh, pytest 104 passed, ruff, ruff format, mypy --strict, audit-security all exit=0, on the final closure state after the round-7 fix) | done |
| R9 | tests/test_propose.py::test_propose_role_diffs_the_failed_role_to_the_bench_winner | S3 demo in harness/specs/debrief/APPROVAL; gauntlet_debrief.md round-8 PASS (rounds 1–5 + 7 REJECT fixed: hostile inputs, score boundary, symlink-escape boundary + role-prefix normalization, string-field forgery + run-log EACCES + Unicode line-separator residual, zero-step run-log refusal + result:/failed_steps header cross-check) | done |
| R10 | tests/test_package.py::test_cli_entrypoint_is_callable | uv sync + uv tool install + JSON-RPC smoke: harness/logs/debrief/install-smoke.log (re-run after the round-7 fix, incl. the headers-only-log run.inspect probe over the installed binary) | done |
| R11 | tests/test_propose.py::test_routing_propose_tool_renders_the_recorded_demo_diff | per-slice demo notes (command + output) in harness/specs/debrief/APPROVAL; full transcript harness/logs/debrief/demo.log (re-recorded incl. round-1/2/3/5/7 hostile probes, 33 assertions PASS) | done |

`check-traceability.py --feature debrief`: 11/11 requirements covered, VERDICT PASS
(saved verbatim in `harness/specs/debrief/traceability.txt` at the T4 closure,
re-run after the round-7 fix).
All 11 rows are `done`; the R8–R11 evidence was recorded by the T4 closure batch
and refreshed by the T4 fix rounds (latest: round-7 fix / round-8 gauntlet PASS).

## Batch T1 (S1 walking skeleton)

- Found the S1 source (errors/domain/ports/use_cases/ggufbench_store/mcp_server) already
  present in the worktree from the scaffold session, but ungated: ruff 19 errors, mypy 1
  error, no tests, no slice entries, no progress record.
- Fixed pre-existing gate failures so the batch could start green:
  - `src/debrief/use_cases.py`: mypy --strict `union-attr` — `_propose` now binds
    `role = failure.role` once and passes `role` into `_role_proposal(role, ...)` (narrowing
    does not cross the call boundary).
  - Wrapped the 7 E501 long lines in `use_cases.py`, `ggufbench_store.py`, `mcp_server.py`;
    `ruff format` applied to src/tests.
  - `harness/tools/`: mechanical lint debt (10× UP037 quoted annotations, 2× E501 in
    validate-feature-list.py); repaired the broken `except A, B:` tuple the UP037 autofix
    produced in check-traceability.py (compileall green, tool runs again).
  - `harness/specs/debrief/design.md`: ruff 0.17 formats python code blocks in markdown;
    ran `ruff format` on the Signatures block only (whitespace).
- `src/debrief/adapters/ggufbench_store.py`: the MCP tool contract promises "`path` is a run
  directory (or the artifact root itself)" but the adapter only scanned child dirs for
  `<run-id>/results.json`; it now reads `results.json` when the requested root *is* a run
  directory (covered by tests).
- Created `tests/test_bench.py` (11 tests, real ggufbench fixtures, no mocks): artifact-root
  answers, row mapping (measure/signature/evidence), structured-error table
  (bench_source_missing, source_unparseable), ADR-0004 comparability accept/refuse,
  MCP `bench.query` boundary via `DEBRIEF_BENCH_ROOT` incl. path-traversal refusal, and the
  R2 static no-write-path guard over `src/debrief`.
- `harness/feature_list.json`: added slices `debrief_bench_query` (S1),
  `debrief_run_inspect` (S2), `debrief_role_propose` (S3), each `part_of: debrief`,
  status `pending`; validate-feature-list.py: valid.
- Gates: `harness/init.sh` → [OK]; `uv run pytest tests` → 12 passed; `ruff check .` → All
  checks passed!; `ruff format --check .` → clean; `uv run mypy --strict` → no issues (11
  files); `audit-security.sh` → no HIGH findings (LOW: bandit B105 on `PASS = "pass"`
  constant, B101 asserts-in-tests); gauntlet G1 → REJECT as expected mid-batch (T2–T4
  unchecked, traceability rows R4–R7 pending until T2/T3).

## Batch T2 (S2 run inspect)

- `src/debrief/adapters/buildwright_log.py`, `InspectRun`, and the `run.inspect` MCP tool
  were present from the scaffold session; this batch gated them with real-fixture tests.
- Created `tests/test_run.py` (9 tests, real buildwright log fixtures, no mocks): step→
  Finding mapping incl. role/evidence/reason, run steps carry no bench knowledge
  (no signature, no measure — ADR-0002), a passing run maps to pass findings, the
  structured-error table (run_source_missing, source_unparseable for a truncated step line
  and a log without a `task:` header), and the `run.inspect` MCP boundary via
  `DEBRIEF_RUN_ROOT` incl. path-traversal refusal.
- Created `tests/test_quality_gates.py`: asserts pyproject keeps mypy --strict over
  src+tests, the ruff rule set, the `debrief` script, and the pytest/ruff/mypy dev deps —
  the mechanical precondition behind R8's per-slice gate runs.
- pyproject.toml: `extend-exclude = ["harness/tools"]` — those harness-owned scripts are
  executed by the system python3 (3.11), which cannot parse the py314-only `except A, B:`
  style ruff format normalizes towards; excluding them keeps the formatter from breaking
  the harness tooling (repaired the one instance this had already produced in
  check-traceability.py during T1).
- Gates: init.sh → [OK]; pytest → 22 passed; ruff check ./format → clean; mypy --strict →
  no issues (13 files); audit-security → no HIGH findings; gauntlet G1 → REJECT, expected
  until T3/T4 (propose tests missing, T4 closure pending).

## Batch T3 (S3 role propose)

- `ProposeRole` (composing `QueryBench` + `InspectRun`) and the `routing.propose` MCP tool
  were present from the scaffold session (plus the T1 narrowing fix in `_propose`);
  this batch gated them with tests.
- Created `tests/test_propose.py` (10 tests): the BW_ROLE_* diff for the failed worker role
  citing both ports (winner `llama-3.1-8b-instruct` at score 0.86, signature line,
  `not applied` never-writes note), R6 guard that every `- `/`+ ` diff line targets a
  `BW_ROLE_*` env, R7 refusal when bench rows span two baselines (`incomparable_rows`,
  never averaged), the all-steps-pass note, the two keep-the-role note branches
  (task never measured by ggufbench; no other passing model — composed from real bench
  fixtures plus synthetic run logs under `tmp_path`), structured-error propagation from
  each port, and the `routing.propose` MCP boundary incl. its incomparable-rows refusal.
- Recorded demo (S3 path, command + output; the formal demo note lands in the S3 approval
  record at the Completion Gate, T4):
  `ProposeRole(QueryBench(GgufbenchStore(tests/fixtures/ggufbench/run-2026-11-01)),
  InspectRun(BuildwrightLog(.../run-2026-11-02T09-14Z.log))).run()` →
  `proposal: BW_ROLE_WORKER holds qwen2.5-7b-instruct-q4_k_m, which failed task sql-join`
  / `- BW_ROLE_WORKER=qwen2.5-7b-instruct-q4_k_m`
  / `+ BW_ROLE_WORKER=llama-3.1-8b-instruct-q4_k_m` / why run / why bench / signature /
  `not applied: debrief never writes …`.
- Traceability table above: R1–R7 done; `check-traceability.py --feature debrief` → 11/11
  covered, VERDICT PASS.
- Gates: init.sh → [OK]; pytest → 32 passed; ruff check ./format → clean; mypy --strict →
  no issues (14 files); audit-security → no HIGH findings; gauntlet G1 → only remaining
  gap is T4 itself still unchecked (closure batch: full gate battery, uv sync /
  uv tool install smoke, demo notes, parent → done).

## Batch T4 (gates and closure)

- Gate battery re-run end-to-end and captured verbatim in
  `harness/logs/debrief/batch-4.log`: `bash harness/init.sh` (final line `[OK]`),
  `uv run pytest tests` (32 passed), `uv run ruff check .` (All checks passed!),
  `uv run ruff format --check .` (43 files already formatted),
  `uv run mypy --strict` (no issues in 14 files), `bash harness/tools/audit-security.sh`
  (no HIGH findings; LOW-only bandit noise in tests + the `PASS` domain constant).
- Install smoke (R10) captured in `harness/logs/debrief/install-smoke.log`: `uv sync` →
  exit 0; `uv tool install .` (into a temp `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`, cleaned up
  afterwards) built `debrief==0.1.0` and installed the `debrief` executable; raw
  JSON-RPC piped to that binary answered `initialize`, `tools/list` (all three tool
  names) and `tools/call bench.query` → 4 findings, `error: null`. First attempt lost
  the `tools/call` response: the server exits on stdin EOF before the in-flight answer
  is flushed, so the smoke now keeps stdin open and reads line-by-line (Popen) until
  the answer arrives.
- Slice demos (R11) recorded by driving the real server over MCP stdio
  (`ClientSession` → `uv run debrief`, fixture roots via env): `bench.query
  run-2026-11-01` (4 findings incl. the qwen2.5 fail with signature+measure),
  `run.inspect run-2026-11-02T09-14Z.log` (planner/worker/reviewer, worker fail,
  `signature: null`, `measure: null`), `routing.propose` → the BW_ROLE_WORKER diff with
  both `why run`/`why bench` citations and the never-writes note, plus the
  `incomparable_rows` refusal when bench_path is the two-baseline artifact root.
  Transcript: `harness/logs/debrief/demo.log` (assertions PASS); demo notes with
  command + output copied into `harness/specs/debrief/APPROVAL`.
- `python3 harness/tools/check-traceability.py --feature debrief` → `## debrief: 11/11
  requirements covered`, `VERDICT: PASS`, saved verbatim to
  `harness/specs/debrief/traceability.txt`; traceability rows R8–R11 flipped to `done`
  with the gate/smoke/demo evidence named.
- Closure state: T4 marked `[x]` in `harness/specs/debrief/tasks.md`;
  `harness/feature_list.json` parent `debrief` → `done` (slice entries stay `pending`:
  they were implemented as parent tasks T1–T3 and validated `done` entries would
  require spec trios + APPROVAL files no dispatch authorized; their acceptance is
  discharged by the parent's APPROVAL demo notes — recorded in APPROVAL and above);
  `python3 harness/tools/validate-feature-list.py harness/feature_list.json` →
  `feature_list.json is valid (protocol v1)`.
- Gauntlet (C8): G1 `bash harness/tools/gauntlet.sh --feature debrief` → exit 0 PASS
  (`harness/logs/debrief/gauntlet-g1.log`); G2+G3 fresh-eyes pass over every changed
  file — 6 findings, 4 verified safe by existing tests, 2 defended (uppercase outcome
  enum → keep-note instead of proposal; zero-step log wording), none open
  (`harness/logs/debrief/gauntlet-g23.log`); G4 report
  `harness/progress/gauntlet_debrief.md` with four PASS lines.
- Evidence mechanics: the capture ran through a transient `.capture_t4.py` that wrote
  the logs and deleted itself; its first run showed ruff red only because the script
  itself was in the scan path — ruff/format re-verified green after removal and the
  battery was re-captured clean.

## Batch T4 fix round (gauntlet round-1 findings)

- Gauntlet G2/G3 round 1 REJECTED with 4 findings (recorded at the top of
  `harness/progress/gauntlet_debrief.md`); this batch fixed all four and the gauntlet
  re-ran from G1.
- [G2-1] `src/debrief/mcp_server.py` `_resolve_within`: the `(root / requested).resolve()`
  call is now wrapped in `except (ValueError, OSError)` -> `path_outside_root`; NUL bytes
  in any tool path argument answer a structured error instead of crashing into a protocol
  ToolError. Tests: `test_bench_query_tool_refuses_paths_outside_the_root` parametrized
  over traversal + three NUL shapes; NUL rows added to the `run.inspect` and
  `routing.propose` refusal tables.
- [G2-2] `src/debrief/adapters/ggufbench_store.py`: the directory enumeration moved into
  `_results_files()`, wrapped in `findings()` by the same narrow
  `OSError -> source_unparseable` mapping as the read path. Because pathlib on CPython
  3.14 swallows EACCES inside `is_file()` (which is what silently dropped unreadable run
  dirs into a misleading `bench_source_missing`), the scan now stats candidates via
  `_is_regular_file()` (propagates EACCES/ELOOP, treats only ENOENT/ENOTDIR as "no
  results here" — a plain `README.md` under the artifact root must not fail the scan).
  Tests: `test_unreadable_artifact_root_refuses_instead_of_raising` (chmod 000 root, was
  a PermissionError escape) and `test_unreadable_run_directory_is_reported_not_skipped`,
  both `skipif(os.geteuid() == 0)` with modes restored in `finally`.
- [G2-3] Outcome enum validated at both adapter boundaries (`OUTCOMES = frozenset({PASS,
  FAIL})` in `src/debrief/domain.py`; adapters raise `_Unparseable` -> source_unparseable
  for any other token). This kills the false-claim direction: a run whose only step says
  `outcome=FAIL` plus a passing bench cohort now refuses instead of answering "no
  proposal: every logged step passed". Fixtures: `ggufbench_broken/bad-outcome-uppercase`
  + `bad-outcome-token` results.json; `buildwright/run-bad-outcome-FAIL.log` +
  `run-bad-outcome-token.log` (+ README updates). Tests:
  `test_unknown_outcome_step_never_yields_the_all_passed_claim[FAIL|Pass|timeout]`,
  `test_inspect_run_refuses_steps_with_outcome_tokens_outside_the_enum[*]`,
  `test_bench_refuses_rows_with_outcome_tokens_outside_the_enum[*]` + two refusal-table
  rows.
- [G2-4] `_read_run` catches `(OSError, ValueError, RecursionError)`; ValueError also
  covers UnicodeDecodeError (hostile bytes), and the buildwright read path maps it too.
  Tests: `test_hostile_artifact_bytes_refuse_as_unparseable
  [nesting_bomb_array|nesting_bomb_object|undecodable_bytes]`, `run-invalid-utf8.log`
  row in the run refusal table. Fixture `run-invalid-utf8.log` is real binary bytes
  (written once via a `uv run python -c` one-liner).
- Doc reconciliation (round-1 G3 note): `harness/specs/debrief/design.md` Approach no
  longer mentions a thin CLI — the `debrief` entry point is the stdio server, demos
  drive it from an MCP client. Round-1 G3 note (2) kept as optional (buildwright read
  failures stay `source_unparseable`, consistent with the bench read path).
- All four fixes probe-verified twice: directly (transient heredoc probe, "ALL PROBES
  FIXED") and over MCP stdio (hostile section of `harness/logs/debrief/demo.log`:
  NUL paths -> path_outside_root, nesting bomb -> source_unparseable, uppercase-outcome
  propose -> source_unparseable and the "every logged step passed" string absent).
- Gates re-run end-to-end, captured in `harness/logs/debrief/batch-5.log` (all exit=0):
  init.sh [OK] + 54 passed (was 32), ruff check, ruff format --check (45 files),
  mypy --strict (14 files), audit-security (no HIGH; bandit LOW noise elided in the
  log with a pointer, full LOW list of this round in the run_command archive).
  Test count 32 -> 54 (22 regression tests over the four findings).
- Install smoke re-run after the code changes (`harness/logs/debrief/install-smoke.log`):
  `uv sync` exit 0; `uv tool install .` rebuilt `debrief==0.1.0` into a temp tool dir;
  raw JSON-RPC over the installed binary: initialize / tools/list / tools/call
  bench.query -> 4 findings, `error: null`.
- Demo transcript re-recorded with the fixed server (`harness/logs/debrief/demo.log`,
  "demo assertions PASS"): S1/S2/S3 demos unchanged in content; new hostile-probe
  section appended.
- Gauntlet re-run from G1: G1 PASS (`gauntlet-g1.log`); G2+G3 fresh-eyes pass with the
  fix verification + new-angle scan + 2 carry-over defenses (`gauntlet-g23.log`);
  report `harness/progress/gauntlet_debrief.md` now has four round-2 PASS lines.
- `check-traceability.py --feature debrief` re-run -> 11/11, VERDICT PASS, saved to
  `harness/specs/debrief/traceability.txt`; traceability rows R8–R11 now point at the
  re-run evidence. APPROVAL Completion Gate section refreshed to the same evidence.
- Capture mechanics: two transient scripts (`.capture_t4fix.py` for demo+smoke,
  `.capture_battery.py` for batch-5.log) wrote the logs and deleted themselves before
  any ruff/bandit scan; `ls`-verified absent afterwards. Battery first attempted via
  individual `run_command` invocations (all six green, outputs above in session), then
  re-captured verbatim into batch-5.log by the transient runner.
- Closure state unchanged: T4 `[x]` in tasks.md; parent `debrief` stays `done` in
  `harness/feature_list.json` (validator re-run via init.sh: valid).

## Batch T4 fix round 2 (gauntlet round-2 findings, per human fix order)

- Gauntlet round 2 REJECTED with 2 sibling findings at the ggufbench score boundary;
  this batch fixed both exactly as ordered — boundary fixes only in
  `src/debrief/adapters/ggufbench_store.py::_map_row`:
- [G2-1 non-finite scores] `_map_row` now converts once (`measure = float(score)`) and
  refuses any non-finite result with `math.isfinite(measure)` → `_Unparseable` →
  `source_unparseable` (json.loads accepts the NaN/Infinity/-Infinity tokens, which
  otherwise hijack the `_role_proposal` winner ranking — `+ BW_ROLE_WORKER=evil-model`
  with "why bench: … score inf/nan"). Regression rows: NaN / Infinity / -Infinity
  fixtures (`tests/fixtures/ggufbench_broken/nonfinite-score-{nan,infinity,
  neg-infinity}/results.json`, single `evil-model` pass row each) +
  `test_bench_refuses_scores_outside_the_finite_float_domain[nan|infinity|
  negative_infinity|huge_int]` asserting code + detail token, plus end-to-end rows
  `tests/test_propose.py::test_poisoned_bench_scores_never_reach_the_proposal_ranking[*]`
  pinning that a poisoned cohort answers a DebriefError, never a fabricated diff.
- [G2-2 huge-int score] the same conversion now runs under `except OverflowError` →
  `_Unparseable("score overflows a float: <digits>")` → `source_unparseable` (JSON
  integers are arbitrary-precision; a 401-digit score escaped QueryBench/ProposeRole/
  the MCP tool as a raw protocol error). Regression row: fixture
  `huge-int-score/results.json` (1 followed by 400 zeros) + the `huge_int_score` row
  above (both tables).
- Fresh-eyes sibling probe: `1e999` (json → inf) refuses through the same isfinite
  gate — no extra fixture needed; run-side findings carry `measure: null` (ADR-0002),
  so the boundary is the only entry path for a poisoned measure.
- `tests/fixtures/ggufbench_broken/README.md` notes the score-boundary fixtures.
- Gates re-run end-to-end after the fix, captured verbatim by a transient self-deleting
  runner into `harness/logs/debrief/batch-6.log` — six gates, every `[exit=0]`:
  init.sh `[OK]` + 62 passed (was 54; +8 score-boundary test cases), ruff check,
  ruff format --check (45 files), mypy --strict (14 files), audit-security (no HIGH;
  LOW-only bandit noise elided with a pointer, as in batch-5.log).
- Install smoke re-run after the code change (`harness/logs/debrief/install-smoke.log`):
  `uv sync` exit 0; `uv tool install .` rebuilt `debrief==0.1.0` into a temp tool dir;
  raw JSON-RPC over the installed binary: initialize / tools/list / tools/call
  bench.query → 4 findings, `error: null`.
- Demo transcript re-recorded with the fixed server (`harness/logs/debrief/demo.log`,
  "demo assertions PASS"): S1/S2/S3 demos + R7 refusal unchanged in content; hostile
  section extended with the four score probes over MCP stdio — nan/inf/-inf →
  "score is not a finite number", huge-int → "score overflows a float", propose over a
  poisoned cohort → `source_unparseable` with "evil-model" absent from the whole
  transcript. Capture mechanics learned the hard way: a `tools/call` issued the instant
  after `initialize` can land before the stdio server processes
  `notifications/initialized` (mcp 2.3 parks its read loop during the inline
  initialize) and answers -32602 "Invalid request parameters" — the runner settles
  0.3s and retries; stale probe/capture scripts self-delete before any ruff/bandit
  scan, and `ls` verified none remain.
- Gauntlet re-run from G1: G1 PASS (`harness/logs/debrief/gauntlet-g1.log`); G2+G3
  fresh-eyes round 3 PASS (fix verification + new-angle scan + the 1e999 probe);
  G4 evidence — `harness/progress/gauntlet_debrief.md` now ends with the round-3
  four-PASS section; rounds 1–2 preserved verbatim.
- `python3 harness/tools/check-traceability.py --feature debrief` → 11/11, VERDICT
  PASS, saved to `harness/specs/debrief/traceability.txt`; traceability rows R8–R11
  point at the round-3 evidence. APPROVAL Completion Gate section refreshed.
- Closure state: T4 `[x]` in tasks.md; parent `debrief` → `status: "done"` in
  `harness/feature_list.json` (it had reverted to `in_progress` in the worktree);
  validate-feature-list green via init.sh.

## Batch T4 fix round 3 (review round-1 CHANGES_REQUESTED: slice entries restored)

- The three slice entries were missing from `harness/feature_list.json` although T1's
  deliverable ("add 3 slice entries"), design.md's file table, Batch T1/T4 records and
  the round-2 G3 note all describe them as present as `pending` — the reviewer traced
  them to the worktree revert the T4 closure batch itself noticed. Restored per the
  reviewer's preferred option (no spec mutation):
  - `debrief_bench_query` (id 2), `debrief_run_inspect` (id 3), `debrief_role_propose`
    (id 4), each `part_of: "debrief"`, `status: "pending"`, titles/outcomes from
    design.md's slice map and acceptance rows from requirements.md's slice ownership
    (S1 R1–R3, S2 R1–R2+R4, S3 R1–R2+R5–R7, plus the ADR constraints).
  - Parent `debrief` stays `done`; slices stay `pending` (their acceptance is
    discharged by the parent's APPROVAL demo notes, as APPROVAL already documents).
- Gates re-run end-to-end after the restore (all exit=0, observed this session):
  `python3 harness/tools/validate-feature-list.py harness/feature_list.json`
  → `feature_list.json is valid (protocol v1)` (4 features); `bash harness/init.sh`
  → `[OK]` (feature_list valid (4 features), 62 passed); `uv run pytest tests`
  → 62 passed; `uv run ruff check .` → All checks passed!; `uv run ruff format
  --check .` → 45 files already formatted; `uv run mypy --strict` → no issues in 14
  source files; `bash harness/tools/audit-security.sh` → no HIGH findings (LOW-only
  bandit noise: B101 asserts in tests, B105 `PASS` domain constant); `uv sync` →
  exit 0.
- Installability smoke re-run after the restore (no source change; re-confirmed):
  `uv tool install .` into a temp `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` (cleaned up)
  built `debrief==0.1.0` and installed the `debrief` executable; raw JSON-RPC over
  the installed binary answered initialize (id 1), tools/list (id 2: bench.query,
  run.inspect, routing.propose) and tools/call bench.query (id 3: 4 findings,
  error null).
- `python3 harness/tools/check-traceability.py --feature debrief` → `## debrief: 11/11
  requirements covered`, `VERDICT: PASS` (`harness/specs/debrief/traceability.txt`
  unchanged in content, verdict re-confirmed).
- Gauntlet re-run from G1: `bash harness/tools/gauntlet.sh --feature debrief` → PASS
  (spec trio ok, tasks 4/4 `[x]`, traceability ok). G2+G3: the on-disk per-pass log
  `harness/logs/debrief/gauntlet-g23.log` still held only the round-2 pass (54 tests,
  "no new findings"), so it was annotated (recommended, non-blocking item): a
  per-pass index plus a "Round-3 (final) pass" section now records the fresh-eyes
  pass over the round-2 fix batch (62 tests): both score-boundary fixes verified at
  `_map_row`, regression-locked by the 8 boundary rows; fresh-angle scan found no new
  finding — the `1e999` sibling was re-probed through the public path this round
  (`source_unparseable`, "score is not a finite number: inf"), and the bool-score
  guard, the artifact-bounded OverflowError detail (operator-scope roots, as defended
  in round 2) and the unchanged no-write-path/layer rules are all noted — matching the
  round-3 verdict in `harness/progress/gauntlet_debrief.md`.
- `harness/progress/current.md`: the Log now records the round-2 REJECT → round-3
  fix → **round-3 PASS** chain and this review fix round (it previously stopped at
  "round-2 PASS").
- Closure state unchanged: T4 `[x]` in tasks.md; parent `debrief` `done` in
  `harness/feature_list.json`; APPROVAL and traceability.txt untouched (the restore
  re-establishes exactly the state their text describes — slices `pending`, parent
  `done`).

## Batch T4 fix round 4 (gauntlet round-3 findings, per human fix order)

- Gauntlet round 3 REJECTED with 3 findings (recorded in the round history of
  `harness/progress/gauntlet_debrief.md`); this batch fixed both actionable ones
  exactly as ordered and defended the third (per protocol), then the gauntlet re-ran
  from G1.
- [G2-1 MUST-FIX nested symlink indirection] `src/debrief/adapters/ggufbench_store.py`:
  `_results_files()` now resolves the store root once, and every candidate —
  `root / RESULTS_FILE` and each `iterdir()` entry — goes through the new
  `_contained_results(root, candidate)`, which resolves the candidate and requires
  `resolved.is_relative_to(root)` before anything is read; an escaping candidate
  refuses the whole scan via `_Unparseable` -> `source_unparseable`
  ("a run's results.json escapes the ggufbench artifact root"), matching the
  evidence-tool direction already established for unreadable/corrupt run dirs
  (never a silent skip, never a silent read past the boundary). `_read_run` only ever
  receives resolved-and-contained paths. A resolve-time OSError maps to the same
  refusal (`from err` chained).
  Regression rows: `tests/test_bench.py::test_symlinked_results_file_outside_the_root_refuses_the_scan[artifact_root_scan|run_dir_requested]`
  (hostile table: the external file holds a winning `LEAKED-model` row and the test
  asserts it never appears in the answer),
  `test_bench_query_tool_refuses_a_symlink_escaping_below_the_requested_path` (the
  gauntlet's exact public-path probe: `bench_query("r1")`),
  `test_symlinked_results_file_inside_the_root_is_still_read` (positive control: the
  boundary refuses escapes, not symlinks), and
  `tests/test_propose.py::test_symlink_escaping_the_bench_root_never_reaches_the_proposal[artifact_root_scan|run_dir_requested]`
  (the leak cannot reach the proposal ranking through `routing.propose`).
- [G2-2 SHOULD-FIX prefixed role token] `src/debrief/use_cases.py`: new
  `_canonical_role()` — `role.upper().removeprefix("BW_ROLE_")` — applied in
  `_propose` before dedup and rendering, so `role=BW_ROLE_WORKER` (and its lowercase
  form) now yield the canonical `+ BW_ROLE_WORKER=…` diff instead of
  `BW_ROLE_BW_ROLE_WORKER`; dedup also happens on the canonical name, so a log
  mixing `worker` and `BW_ROLE_WORKER` collapses to one proposal.
  Regression table: `test_role_tokens_carrying_the_env_prefix_still_render_a_pasteable_diff`
  [bare_lowercase|bare_uppercase|prefixed_as_written_in_the_roles_header|prefixed_lowercase],
  each asserting the normalized `+ BW_ROLE_WORKER=llama-3.1-8b-instruct-q4_k_m` line
  and the absence of `BW_ROLE_BW_ROLE_`.
- [G2-3 DEFENDED] no action required, as recorded in the round-3 verdict; its
  residuals were re-checked this round and all prior-round fixes re-verified through
  the public MCP path.
- Both fixes probe-verified through the public MCP path (transient self-deleting
  probe, "PROBE PASS"): `bench.query {"path": "r1"}` over the escaping tree →
  `source_unparseable`, findings `[]`, no `LEAKED-model` anywhere;
  `routing.propose` over the same artifact → the structured error, proposal `""`;
  prefixed-role propose → normalized diff only.
- Fresh-eyes G2+G3 pass (`harness/logs/debrief/gauntlet-g23.log`): fixed findings
  re-verified publicly + regression-locked; 5 new residual probes all PASS —
  symlink loop (structured error, no crash), escaping run-*directory* symlink
  (the fix covers any depth, not only one level down), results.json symlink to a
  directory inside the root (skipped, no crash), contained two-hop symlink chain
  (still read), degenerate role token `BW_ROLE_` (text-only, never double-prefixed,
  "not applied" intact); 3 findings defended with named trade-offs (TOCTOU window
  identical to the accepted `_resolve_within` design and outside the declared
  single-user threat model — closing it needs `openat2(RESOLVE_BENEATH)`, out of
  scope for the ordered one-spot fix; degenerate `BW_ROLE_` token is text-only
  output; the resolve-OSError escape wording is effectively unreachable because
  non-strict `Path.resolve` swallows component OSErrors).
- Gates re-run end-to-end after the fix and captured verbatim by a transient
  self-relocating runner (moved itself to /tmp before any scan, so ruff/bandit
  never see it) into `harness/logs/debrief/batch-7.log` — six gates, every
  `[exit=0]`: init.sh `[OK]` + 72 passed (was 62; +10 round-3 regression rows),
  ruff check, ruff format --check (45 files), mypy --strict (14 files),
  audit-security (no HIGH; the LOW-only bandit noise elided exactly like
  batch-4/5/6, verdict line verbatim). A first capture pass had the runner's
  bandit-elision transform unapplied; it was corrected and the battery re-captured
  clean.
- Install smoke re-run after the code change (`harness/logs/debrief/install-smoke.log`):
  `uv sync` exit 0; `uv tool install .` rebuilt `debrief==0.1.0` into a temp tool
  dir; raw JSON-RPC over the installed binary: initialize / tools/list /
  tools/call bench.query → 4 findings, `error: null`.
- Demo transcript re-recorded with the fixed server (`harness/logs/debrief/demo.log`,
  "demo assertions PASS"): S1/S2/S3 + R7 refusal unchanged in content; rounds-1/2
  hostile section unchanged; new "gauntlet round-3 findings" section appends the
  symlink-escape bench/propose refusals and the normalized prefixed-role diff.
- `python3 harness/tools/check-traceability.py --feature debrief` re-run → 11/11,
  VERDICT PASS, saved verbatim to `harness/specs/debrief/traceability.txt`;
  traceability rows R8–R11 updated to the round-4 evidence; APPROVAL Completion Gate
  section refreshed (round-3 findings named, 72 tests, batch-7/smoke/demo/gauntlet
  logs, round-4 PASS).
- Gauntlet re-run from G1: G1 PASS (`harness/logs/debrief/gauntlet-g1.log`); G2+G3
  PASS (log above); report `harness/progress/gauntlet_debrief.md` rewritten with the
  round history (1–3 REJECT, 4 PASS), four PASS lines and the findings ledger.
  `harness/progress/current.md` log extended with the round-3 REJECT → round-4 fix →
  round-4 PASS chain.
- Closure state: T4 stays `[x]` in tasks.md; parent `debrief` stays `done` in
  `harness/feature_list.json` (slices stay `pending`, accepted via the parent's
  APPROVAL demo notes); `validate-feature-list.py` green via init.sh inside the
  battery. Transient capture/probe scripts self-deleted (verified absent).
- Evidence-state repair (found during closure): the working tree had lost the
  reviewer-accepted `harness/feature_list.json` state — the file was back at HEAD's
  one-feature entry with the parent `blocked` (the harness flip-watcher commits
  `chore(debrief): status blocked/in_progress` against the parent, and the previous
  session's uncommitted restore was not in the checkout this attempt started from).
  Restored the accepted state exactly as recorded in the round-1 review fix and
  `harness/progress/review_debrief.md`: parent `debrief` → `done` (its APPROVAL
  exists, satisfying the validator's done rule) plus slice entries ids 2–4
  (`debrief_bench_query`, `debrief_run_inspect`, `debrief_role_propose`, each
  `part_of: "debrief"`, `status: "pending"`, titles from design.md's slice map,
  acceptance rows from requirements.md's slice ownership — S1 R1–R3, S2 R1–R2+R4,
  S3 R1–R2+R5–R7). `validate-feature-list.py` → `valid (protocol v1)` (4 features);
  check-traceability and gauntlet G1 re-run green on the restored file. Because the
  battery log had captured init.sh's "valid (1 features)" (the same staleness the
  reviewer flagged as non-blocking observation 1 for batch-6.log), the six-gate
  battery was re-captured on the final state into `harness/logs/debrief/batch-7.log`
  — all `[exit=0]`, 72 passed, feature_list valid (4 features). Install smoke and
  demo transcripts needed no re-capture: they exercise only `src/debrief` and the
  fixtures, unchanged since their post-round-3-fix runs.

## Batch T4 fix round 5 (gauntlet round-5 findings, per human fix order)

- Gauntlet round 5 REJECTED with 2 findings; this batch fixed both exactly as ordered,
  then closed the fresh-eyes residual the round's own re-read surfaced.
- [G2-1 MUST-FIX, artifact string-field forgery] `src/debrief/adapters/
  ggufbench_store.py` now validates every artifact string field at the boundary:
  identifier-like fields (`model`, `task`, `baseline`, `engine_build`, graded
  dimension names) must be single-line whitespace-free tokens (`_required_token`,
  `_required_counts`), free-text fields (`reason`, `artifact`) single-line
  control-char-free (`_required_line`); anything else refuses as
  `source_unparseable` ("not a single-line whitespace-free token" / "contains
  control characters"), exactly like every other malformed row. Regression rows:
  `tests/test_bench.py::test_bench_refuses_string_fields_that_could_forge_proposal_lines`
  parametrized over model/task/reason/artifact/engine_build/baseline poisoning
  (incl. the two gauntlet probe vectors and control-char shapes) +
  `test_bench_refuses_multiline_graded_dimension`; end-to-end
  `tests/test_propose.py::test_poisoned_bench_fields_never_reach_the_proposal_output`
  parametrized over the forged role line, the forged `models.yaml` registry line, a
  `reason` vector, an `artifact` vector and a Unicode-separator vector — each
  asserting the structured refusal, i.e. no forged `- `/`+ ` diff line reaches the
  caller's output.
- [G2-2 MINOR, run-log EACCES] `src/debrief/adapters/buildwright_log.py::findings`
  now mirrors the bench stat()-based probe: `stat()` first —
  `FileNotFoundError`/`NotADirectoryError` -> `run_source_missing`;
  `PermissionError` (existing log behind an unreadable parent, or an unreadable
  file) -> `source_unparseable` ("exists but cannot be probed"); a non-regular
  stat stays `run_source_missing`. This kills the pathlib-swallowed-EACCES
  mislabeling ("an evidence tool never silently drops"). Regression:
  `tests/test_run.py::test_existing_run_log_behind_unreadable_parent_is_unparseable_not_missing`
  (chmod 000 parent, skipif-root, mode restored in `finally`).
- [fresh-eyes residual, fixed in this batch] the free-text rule initially refused
  only `ord(ch) < 0x20 or == 0x7F`, but Unicode line separators (U+0085 NEL,
  U+2028, U+2029) sit above that range and still split the value everywhere
  Python splits text — empirically confirmed: `reason="trusted-value<U+2029>
  + BW_ROLE_WORKER=evil-model"` passed the ord() check and `str.splitlines()`
  yields the forged diff line. `_required_line` now additionally requires
  `value.splitlines() == [value]` -> `source_unparseable` ("is not a single
  line"); `_required_token` additionally refuses control characters that are
  `\S` (e.g. NUL) via the shared `_refuse_control_chars` helper. Regression rows:
  `reason_forges_via_unicode_line_separator`, `artifact_unicode_line_separator`,
  `model_control_char_is_not_a_token` (bench table) and the
  `reason_forges_via_unicode_line_separator` end-to-end propose row.
- Fresh-eyes residual probes (transient script, run and deleted; results recorded
  in the round-6 section of `harness/logs/debrief/gauntlet-g23.log`): U+2029 in a
  token -> token refusal; NUL in a token -> control-char refusal; U+0085 in
  `reason` -> "is not a single line"; whitespace-only `reason` -> accepted as
  findings (cannot break out of its `why …: (…) — …` line); whitespace-only
  `model` -> token refusal; graded dimension `a:b` -> rendering-only key
  ambiguity (comparability compares `TaskSignature` dataclasses, never the key);
  negative finite score -> accepted (ggufbench's pass verdict is authoritative);
  `run.inspect` on a directory -> `run_source_missing` (no run log at that path,
  the established non-regular direction); bench_path at a plain `results.json`
  file -> `bench_source_missing` (contract promises a directory); positive
  control unchanged.
- Suite 72 -> 91 (19 regression rows over the two ordered findings + the
  residual). Gates re-run end-to-end on the final code state and captured
  verbatim by a transient self-deleting runner into
  `harness/logs/debrief/batch-8.log` — six gates, every `[exit=0]`: init.sh
  `[OK]` (feature_list valid, 4 features), pytest 91 passed, ruff check, ruff
  format --check (45 files), mypy --strict (14 files), audit-security (no HIGH;
  148 LOW-only bandit findings elided in the log with a pointer: B101
  asserts-in-tests, B105 `PASS = "pass"` domain constant).
- Install smoke re-run after the code change
  (`harness/logs/debrief/install-smoke.log`): `uv sync` exit 0; `uv tool install
  .` rebuilt `debrief==0.1.0` into a temp tool dir (cleaned up); raw JSON-RPC
  over the installed binary: initialize / tools/list / tools/call bench.query ->
  4 findings, `error: null`.
- Demo transcript re-recorded with the fixed server
  (`harness/logs/debrief/demo.log`, "demo assertions PASS"): S1/S2/S3 demos and
  the R7 refusal unchanged in content; rounds 1–3 hostile probes re-verified;
  new round-5 section: poisoned `model` (role-line and `models.yaml` vectors) ->
  `source_unparseable` with `proposal: ""` and no `- `/`+ ` line in any answer;
  poisoned `reason` -> "contains control characters"; `poisoned-separator`
  (U+2029) -> "is not a single line" with no diff line; unreadable-parent run
  log -> `source_unparseable` ("exists but cannot be probed"), never
  `run_source_missing`.
- `check-traceability.py --feature debrief` re-run -> 11/11, VERDICT PASS, saved
  to `harness/specs/debrief/traceability.txt`; traceability rows R1/R6/R8–R11
  updated to the round-5/6 evidence. APPROVAL Completion Gate refreshed to the
  round-6 run.
- Gauntlet re-run from G1: G1 PASS (`harness/logs/debrief/gauntlet-g1.log`);
  G2+G3 fresh-eyes pass recorded in the round-6 section of
  `harness/logs/debrief/gauntlet-g23.log` (fixed findings re-verified publicly,
  the Unicode-separator finding caught and fixed, 10 residual probes, 3
  defended); report `harness/progress/gauntlet_debrief.md` now has four round-6
  PASS lines with the round-5 record kept below the separator.
- Closure state: `harness/feature_list.json` restored to the reviewer-accepted
  closure state (parent `debrief` = `done` + slice ids 2–4
  `debrief_bench_query` / `debrief_run_inspect` / `debrief_role_propose`, each
  `part_of: "debrief"`, `status: "pending"` — the checkout had lost them again
  to the status-flip watcher); validator -> valid (4 features, inside init.sh);
  T4 stays `[x]` in `harness/specs/debrief/tasks.md`; parent `done`.

## Batch T4 fix round 6 (gauntlet round-7 findings, per human fix order)

- Gauntlet round 7 (a fresh G2+G3 pass independent of the prior six rounds)
  REJECTED with one MUST-FIX and its sibling: [G2-1] a step-stripped run log
  (valid `task:` header, zero `step:` lines) answered `[]` as a structured
  success from run.inspect and "no proposal: every logged step passed" from
  routing.propose while the log's own `result: fail failed_steps=01` header
  declared a failure; [G2-2] the `result:`/`failed_steps` header was parsed
  nowhere. This batch implemented the ordered fix and the optional family fix.
- [G2-1, ordered MUST-FIX] `src/debrief/adapters/buildwright_log.py::_map_log`
  raises `_Unparseable` -> `source_unparseable` when the log has a `task:`
  header but no `step:` lines, so a headers-only log can never answer `[]` as a
  structured success and ProposeRole can never answer the all-passed claim for
  a step-stripped log. Regression rows: `tests/test_run.py::
  test_headers_only_run_log_refuses_as_unparseable` and `tests/test_propose.py::
  test_propose_does_not_claim_all_passed_for_a_step_stripped_log` (both landed
  with the fix code before this batch; verified live this batch: headers-only
  inspect -> DebriefError(source_unparseable, "run log has a task header but no
  step: lines"); propose over it -> the same structured error).
- [G2-2, optional cross-check implemented] `_map_log` now parses each step into
  a frozen `_Step` record (keeping the step ordinal out of the shared `Finding`,
  ADR-0002) and `_check_result_header` cross-checks the `result:` header against
  the logged step outcomes once every step line has parsed and the zero-step
  refusal has fired: `result: pass` over a logged failure refuses
  ("declares pass but logged step 02 failed"); a `failed_steps` list that does
  not match the logged failing step ordinals refuses ("does not match"), with
  zero-padding-insensitive comparison (`02` == `2` == `0002`) and comma lists
  matching multi-failure logs; a failure claim with no logged failing step
  refuses; a failure without a `failed_steps` list, an empty list, a malformed
  header and a header outcome outside the pass/fail enum all refuse; the header
  stays optional (older producers omit it) and first-wins like every header key.
  Regression rows: `tests/test_run.py::
  test_result_header_contradicting_the_logged_steps_refuses_the_log[*]` (7
  reject cases), `test_result_header_agreeing_with_the_logged_steps_still_parses`,
  `test_failed_steps_without_zero_padding_still_matches_the_logged_step`,
  `tests/test_propose.py::
  test_propose_does_not_claim_all_passed_for_a_log_whose_result_header_lies[*]`
  (pass header over a logged failure; `failed_steps` naming a step that passed).
- Fresh-eyes residual probes: 19, all PASS (consistent/unpadded/zero-padded/
  duplicate/multi-failure headers parse; no result header parses; every
  contradiction refuses; space-separated ordinal lists and trailing prose are
  malformed headers; a second `result:` header is ignored; a pass header with an
  unrelated `failed_steps=99` token is not a contradiction). Defended in the
  round-8 gauntlet section: tolerance on meaningless pass-header metadata,
  first-wins duplicates, and strictness on an uncrosscheckable failure claim.
- Evidence re-recorded: demo transcript (`harness/logs/debrief/demo.log`,
  33 assertions PASS incl. the new "gauntlet round-7 findings" section probed
  over MCP stdio); install smoke over the *installed* binary
  (`harness/logs/debrief/install-smoke.log`) now also calls `run.inspect` on a
  headers-only log and asserts `source_unparseable` ("no step: lines") — the
  smoke's JSON-RPC loop was also fixed to pipeline past the silent
  `notifications/initialized` notification (it used to deadlock waiting for a
  response a notification never sends); traceability re-run
  (`harness/specs/debrief/traceability.txt`, 11/11, VERDICT PASS); gauntlet
  re-run from G1 (G1 PASS in `gauntlet-g1.log`; G2+G3 round-8 section appended
  to `gauntlet-g23.log`; report `harness/progress/gauntlet_debrief.md` now has
  four round-8 PASS lines with the round-7 REJECT record kept below the
  separator).
- Closure state: `harness/feature_list.json` back in the reviewer-accepted
  shape after the status-flip watcher had dropped it again — parent `debrief` =
  `done` plus the three slice entries (ids 2-4 `debrief_bench_query` /
  `debrief_run_inspect` / `debrief_role_propose`, each `part_of: "debrief"`,
  `status: "pending"`, acceptance rows = the slice's requirements from
  requirements.md slice ownership); validator -> `feature_list.json is valid
  (protocol v1)`. `harness/specs/debrief/APPROVAL` refreshed with the round-7/8
  evidence and the batch-9 battery; `harness/logs/debrief/batch-9.log` is the
  six-gate battery captured on this final state (all `[exit=0]`, 104 passed,
  "valid (4 features)"); T4 stays `[x]` in `harness/specs/debrief/tasks.md`;
  parent `done`.
