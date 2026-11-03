# Implementation log — debrief_run_inspect

feature: debrief_run_inspect

## Traceability

| Req | Tests | Implementation file(s) | Status |
|-----|-------|------------------------|--------|
| R1 | tests/test_run.py::test_inspect_run_refuses_with_structured_error, tests/test_run.py::test_inspect_run_refuses_steps_with_outcome_tokens_outside_the_enum, tests/test_run.py::test_headers_only_run_log_refuses_as_unparseable, tests/test_run.py::test_result_header_contradicting_the_logged_steps_refuses_the_log, tests/test_run.py::test_existing_run_log_behind_unreadable_parent_is_unparseable_not_missing, tests/test_run.py::test_run_inspect_tool_refuses_with_structured_error | src/debrief/errors.py, src/debrief/adapters/buildwright_log.py, src/debrief/use_cases.py, src/debrief/mcp_server.py | done |
| R2 | tests/test_run.py::test_serving_run_inspect_leaves_the_run_fixtures_byte_identical, tests/test_run.py::test_run_inspect_read_path_has_no_write_mode_open_or_mutation, tests/test_bench.py::test_no_debrief_module_contains_a_write_path | src/debrief/adapters/buildwright_log.py, src/debrief/use_cases.py, src/debrief/mcp_server.py | done |
| R4 | tests/test_run.py::test_inspect_run_maps_each_logged_step_to_a_finding, tests/test_run.py::test_inspect_run_reports_a_passing_run_as_pass_findings, tests/test_run.py::test_run_steps_carry_no_bench_knowledge, tests/test_run.py::test_result_header_agreeing_with_the_logged_steps_still_parses, tests/test_run.py::test_failed_steps_without_zero_padding_still_matches_the_logged_step, tests/test_run.py::test_run_inspect_tool_answers_within_the_allowed_root | src/debrief/ports.py, src/debrief/adapters/buildwright_log.py, src/debrief/mcp_server.py | done |

`python3 harness/tools/check-traceability.py --feature debrief_run_inspect`: 3/3
requirements covered, VERDICT PASS (saved verbatim in
`harness/specs/debrief_run_inspect/traceability.txt` at the T4 closure).

## Dispatch batch-1: T1, T2, T3 (2026-11-03)

Starting state: the parent `debrief` feature (status done) already landed the S2
skeleton — `src/debrief/adapters/buildwright_log.py`, `InspectRun`, the
`run.inspect` tool, `tests/test_run.py`, and the `tests/fixtures/buildwright/`
logs — with 104 tests green. This batch therefore **repaired, completed and
verified** the slice surface rather than creating files from scratch.

### T1 — BuildwrightLog adapter (repair + complete) — `src/debrief/adapters/buildwright_log.py`

Audited the adapter against every T1 clause; all behaviors verified present and
proven by tests (including live probes of missing/non-regular/undecodable paths):

- stat()-based existence probe; missing → `run_source_missing`, non-regular
  (directory) → `run_source_missing`, PermissionError on probe →
  `source_unparseable`, undecodable bytes → `source_unparseable`.
- step-line → Finding mapping: role set, `signature`/`measure` left `None`
  (one episode, not a measurement).
- outcome enum `{pass, fail}` checked at the boundary; headers-only log refuses
  as `source_unparseable`; optional `result:` header cross-checked against the
  logged failing ordinals (zero-padding tolerated), every contradiction mode
  refusing with `source_unparseable`.
- **Except clause:** the design note calls
  `except FileNotFoundError, NotADirectoryError:` "invalid syntax, module
  currently unimportable". On this repo's pinned toolchain that premise is
  false: `requires-python >= 3.14` / `.python-version` 3.14.7, where PEP 758
  makes the unparenthesized clause valid and tuple-catching — proven by
  `uv run python -c "import debrief.adapters.buildwright_log"` → `imported`,
  a tuple-catch probe → `caught as tuple: PEP 758 active`, and the 106-test
  suite importing and exercising the adapter. I did parenthesize the clause and
  re-ran the gates: `ruff format --check .` (a mandated gate, docs/conventions.md)
  **rejected the parenthesized form** and demanded the unparenthesized shape
  back (ruff target py314; diff captured in `harness/logs/debrief_run_inspect/batch-1.log`).
  The parent's reviewer-approved gauntlet round 8
  (`harness/logs/debrief/gauntlet-g23.log`, Defended finding #1) already resolved
  this exact conflict: "valid on the py314 target and `ruff format` normalizes
  towards the unparenthesized shape — The formatter is the canon", and
  `ggufbench_store.py` carries the identical clause. Parenthesizing one adapter
  would break a green gate *and* file homogeneity, so the clause stays in the
  formatter-canonical PEP 758 form; the repair the spec actually wants
  (module importable, clause valid, both exceptions caught) holds and is
  evidenced above. `harness/specs/debrief_run_inspect/design.md`'s Context note
  is factually stale on this point (flagged for the reviewer; no spec rewrite
  attempted beyond whitespace, below).

### T2 — adapter tests — `tests/test_run.py`

- Strengthened `test_inspect_run_maps_each_logged_step_to_a_finding` to assert
  all three findings of the broken-run fixture (role/outcome/evidence triples in
  order, all three models, shared task, non-empty reasons) — previously only the
  middle finding was checked in detail.
- Added `id="non_regular_path"` row (the `r-2026-11-02T09-14Z` fixture directory)
  to the refusal table, proving T1's non-regular → `run_source_missing` branch.
- Existing coverage verified complete against the task list: passing-run → pass
  findings; run findings carry no bench fields; refusal table (missing,
  truncated, no task header, undecodable bytes, outcome tokens `FAIL`/`timeout`
  outside the enum); tmp_path tables for headers-only refusal and all seven
  `result:`-header contradiction modes plus agreement and zero-padding.
  Suite: 104 → 105 tests.

### T3 — run.inspect wiring — `src/debrief/mcp_server.py`, `tests/test_run.py`

- Wiring verified: `run.inspect` resolves the requested path through
  `_resolve_within(RUN_ROOT_ENV, DEFAULT_RUN_ROOT, path)` (outside-root and
  embedded-NUL → `path_outside_root`), then answers `FindingsResponse` via
  `InspectRun(BuildwrightLog(resolved)).run()` — errors returned, never raised.
- Added `test_run_inspect_root_contract_is_stable` pinning the agent-facing
  contract: `RUN_ROOT_ENV == "DEBRIEF_RUN_ROOT"`,
  `DEFAULT_RUN_ROOT == "artifacts/buildwright"`.
- Existing tool tests verified: in-root path answers the broken-run fixture's
  findings (roles planner/worker/reviewer, worker `fail`); refusal table covers
  missing, `../pyproject.toml` (outside root), NUL-suffixed and NUL-only paths.
  Suite: 105 → 106 tests.

### Gate repair (needed for the batch's green gates)

- `harness/specs/debrief_run_inspect/design.md` (harness-written spec): its
  "Public signatures" python code block failed `ruff format --check .`
  (missing blank lines between top-level defs; 3-space comment offset).
  Applied the formatter's exact diff (whitespace only inside the fence — no
  requirement/design content changed) so the mandated format gate is green,
  matching the parent spec files' format-clean state.

### Gates (run after each task; final battery in `harness/logs/debrief_run_inspect/batch-1.log`)

- `uv run ruff check .` → exit 0 ("All checks passed!")
- `uv run ruff format --check .` → exit 0 ("48 files already formatted")
- `uv run mypy --strict` → exit 0 ("Success: no issues found in 14 source files")
- `uv run pytest tests` → exit 0, **106 passed** (summary line read, per
  docs/verification.md)
- `bash harness/init.sh` → exit 0, final line `[OK]` (feature_list valid,
  4 features; "All tests pass")

Tasks T1–T3 ticked in `harness/specs/debrief_run_inspect/tasks.md` with this log
in place. T4 (read-only guarantee + slice closure) intentionally untouched.

## Dispatch batch-2: T4 (2026-11-03)

### T4 — read-only guarantee and slice gates (refs R2, R1) — `tests/test_run.py`

- `test_serving_run_inspect_leaves_the_run_fixtures_byte_identical`: fingerprints
  every file under `tests/fixtures/buildwright` (9 files: size, `st_mtime_ns`,
  sha256) before serving, then serves `run.inspect` over the real fixtures — the
  3-step broken log (3 findings), the passing log (1 finding) and a refusal
  (`run-truncated.log` -> `source_unparseable`) — and asserts the fingerprint is
  unchanged afterwards. Probe-verified teeth: an mtime-only `touch` and a
  content change each flip the fingerprint (transient `tmp_path` probe against a
  fixture copy, no repo fixture mutated).
- `test_run_inspect_read_path_has_no_write_mode_open_or_mutation`: AST gate over
  the slice's read path (`adapters/buildwright_log.py`, `use_cases.py`,
  `mcp_server.py`): any `open()` with a write-mode argument (`w`/`x`/`a`/`+`,
  literal or non-literal — a non-literal mode counts as an offender because it
  cannot be proven read-only), any mutating call (`write_text`, `write_bytes`,
  `unlink`, `mkdir`, `rename`, `replace`, `remove`, `rmdir`, `rmtree`, `touch`,
  `truncate`, `chmod`) and any `shutil` import is an offender. Probe-verified
  teeth on six synthetic cases (write mode / `wb` / non-literal mode /
  `write_text` / `unlink` / `shutil` import all flagged; `open(p)`, `open(p,'rb')`
  and `read_text` clean). Complements the parent-wide substring guard
  `tests/test_bench.py::test_no_debrief_module_contains_a_write_path`.
- Suite: 106 -> 108 tests.

### Demo note (recorded into the slice's approval record, refs R1, R2, R4)

- Command: `DEBRIEF_RUN_ROOT=$PWD/tests/fixtures/buildwright uv run debrief`
  (MCP stdio), driven end-to-end by an MCP client (`mcp.ClientSession` ->
  `initialize` -> `tools/list` -> `run.inspect`). Six calls: the 3-step broken
  log (planner/worker/reviewer findings, worker `fail`, `signature: null`,
  `measure: null`), the passing log (1 pass finding), plus four structured
  errors — truncated step line (`source_unparseable`), outcome token `FAIL`
  outside the enum (`source_unparseable`), missing log (`run_source_missing`),
  NUL-suffixed path (`path_outside_root`). After the session closed the fixture
  fingerprint was re-checked: byte-identical, `True`. R2 holds while serving.
- Full transcript with command + output:
  `harness/logs/debrief_run_inspect/demo.log` ("demo assertions PASS");
  the demo note (command + output) is recorded in
  `harness/specs/debrief_run_inspect/APPROVAL` — the slice's approval record,
  left for the human to countersign at the Completion Gate.

### Gates (final battery on the closure state)

- `uv run ruff check .` -> exit 0 ("All checks passed!")
- `uv run ruff format --check .` -> exit 0 ("49 files already formatted")
- `uv run mypy --strict` -> exit 0 ("Success: no issues found in 14 source files")
- `uv run pytest tests` -> exit 0, **108 passed** (summary line read, per
  docs/verification.md)
- `bash harness/init.sh` -> exit 0, final line `[OK]` (feature_list valid,
  4 features; "All tests pass")
- Full battery captured verbatim in `harness/logs/debrief_run_inspect/batch-2.log`
  (evidence rule, AGENTS.md §3); capture mechanics: the demo ran through a
  transient `.capture_demo.py` that wrote `demo.log` and deleted itself before
  the lint gates scanned the tree (verified absent afterwards).
- `python3 harness/tools/check-traceability.py --feature debrief_run_inspect`
  -> 3/3, VERDICT PASS, saved verbatim to
  `harness/specs/debrief_run_inspect/traceability.txt`.

T4 ticked in `harness/specs/debrief_run_inspect/tasks.md`. Remaining for the
slice's Completion Gate (human, not implementer): countersign APPROVAL, slice
status flip in `harness/feature_list.json`, gauntlet per C8.
