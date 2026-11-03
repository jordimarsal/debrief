# Tasks: debrief_bench_query

- [x] T1: Create src/debrief/errors.py (DebriefError + BENCH_SOURCE_MISSING, SOURCE_UNPARSEABLE, PATH_OUTSIDE_ROOT) and src/debrief/domain.py (Finding, TaskSignature, OUTCOMES, shared_signature); tests for signature keys and incomparable-row refusal/acceptance.
      depends_on: (none)
      refs: R1, R3

- [x] T2: Create src/debrief/ports.py (BenchStore protocol) and src/debrief/adapters/ggufbench_store.py mapping real results.json artifacts to Findings and returning structured errors for missing/unparseable sources (bad JSON, nesting bomb, wrong schema, outcome enum, non-finite/overflowing scores, line-forging fields, symlink escape, unreadable dirs); add real fixtures under tests/fixtures/ggufbench and ggufbench_broken with parametrized refusal tests.
      depends_on: T1
      refs: R1, R3

- [x] T3: Add QueryBench to src/debrief/use_cases.py and the bench.query tool to src/debrief/mcp_server.py: DEBRIEF_BENCH_ROOT-scoped path resolution (PATH_OUTSIDE_ROOT incl. NUL bytes), FindingsResponse, stdio main() (mcp dependency + debrief script in pyproject.toml); tests for tool-level answers inside the root and refusals for traversal/NUL/symlink escapes below the requested path.
      depends_on: T2
      refs: R1, R2, R3

- [x] T4: Prove read-only serving and close the slice: static write-marker scan over src/debrief plus a runtime test that a bench.query call leaves the artifact tree byte-identical; run uv run pytest tests, ruff, mypy --strict; fill the requirements.md traceability table and save harness/tools/check-traceability.py output in the feature directory.
      depends_on: T3
      refs: R1, R2, R3
