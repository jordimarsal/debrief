# Requirements: debrief_bench_query

Slice S1 of parent `debrief` (walking skeleton): the `bench.query` MCP tool answers
"what did ggufbench measure?" from real ggufbench artifacts. Requirement IDs match the
parent's slice-ownership map (S1 owns parent R1, R2, R3).

## R1
When the agent invokes the `bench.query` tool, the system shall return either findings
or a structured error carrying a stable code.

## R2
While serving a `bench.query` call, the system shall not write to the filesystem.

## R3
When `bench.query` returns findings, the system shall have derived every finding solely
from ggufbench artifact files read through the BenchStore port.

## Traceability

| Requirement | Test(s) | Implementation file(s) | Status |
|-------------|---------|------------------------|--------|
| R1 | test_bench_query_tool_answers_within_the_allowed_root, test_query_bench_refuses_with_structured_error, test_bench_query_tool_refuses_paths_outside_the_root, test_bench_query_tool_refuses_a_symlink_escaping_below_the_requested_path | src/debrief/errors.py, src/debrief/use_cases.py, src/debrief/mcp_server.py | done |
| R2 | test_no_debrief_module_contains_a_write_path, test_bench_query_leaves_the_artifact_tree_byte_identical, test_bench_query_symlink_escape_refusal_writes_nothing_either | src/debrief/mcp_server.py, src/debrief/adapters/ggufbench_store.py | done |
| R3 | test_query_bench_answers_from_real_artifact_root, test_bench_row_carries_measure_signature_and_evidence_from_the_artifact, test_symlinked_results_file_outside_the_root_refuses_the_scan, test_symlinked_results_file_inside_the_root_is_still_read | src/debrief/ports.py, src/debrief/adapters/ggufbench_store.py, src/debrief/domain.py | done |
