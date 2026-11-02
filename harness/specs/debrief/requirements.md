# Requirements: debrief (parent)

Parent feature for 3 vertical slices (S1 bench_query, S2 run_inspect, S3 role_propose).
Each slice refines its subset in its lite trio.

## R1
Tool calls return findings or a structured error.

## R2
No file writes while serving.

## R3
Bench findings come only from ggufbench artifacts.

## R4
Run findings come only from a buildwright run log.

## R5
Role proposal is a BW_ROLE_* diff as text from both ports' findings.

## R6
Proposals target BW_ROLE_* roles, never models.yaml.

## R7
Incomparable rows -> structured error, never averaged.

## R8
Before each slice Completion Gate: init.sh, pytest, ruff, mypy --strict, audit-security, gauntlet green.

## R9
Parent done only after S3 Completion Gate with recorded demo.

## R10
Installs with uv sync / uv tool install; smoke call works.

## R11
Each slice approval record has a demo note (command + output).

## Slice ownership

- S1 debrief_bench_query — R1, R2, R3
- S2 debrief_run_inspect — R1, R2, R4
- S3 debrief_role_propose — R1, R2, R5, R6, R7
- Parent — R8, R9, R10, R11
