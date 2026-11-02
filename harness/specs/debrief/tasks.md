# Tasks: debrief

- [ ] T1: S1 walking skeleton. Create src/debrief/errors.py (DebriefError), domain.py (Finding + comparability), ports.py (BenchStore, RunLog), use_cases.py (QueryBench), adapters/ggufbench_store.py, mcp_server.py (bench.query tool + main), add mcp to pyproject.toml, add 3 slice entries to feature_list.json. Add tests/test_bench.py using a real ggufbench fixture.
      depends_on: (none)
      refs: R1, R2, R3

- [ ] T2: S2 run inspect. Create adapters/buildwright_log.py and InspectRun in use_cases.py. Add run.inspect MCP tool. Add tests/test_run.py using a real run log fixture.
      depends_on: T1
      refs: R1, R2, R4

- [ ] T3: S3 role propose. Implement ProposeRole (composes QueryBench + InspectRun) and routing.propose MCP tool returning BW_ROLE_* diff as text. Refuse incomparable rows. Add tests/test_propose.py.
      depends_on: T2
      refs: R1, R2, R5, R6, R7

- [ ] T4: Gates and closure. Run harness/init.sh, uv run pytest tests, ruff, mypy --strict, audit-security, gauntlet. Verify uv sync / uv tool install smoke. Run check-traceability.py. Record demo notes. Move parent to done.
      depends_on: T3
      refs: R8, R9, R10, R11
