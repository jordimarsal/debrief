# ggufbench artifact fixtures

Real ggufbench artifact tree, in ggufbench's on-disk layout: one
`<run-id>/results.json` per graded run, plus the transcripts each row points to
as evidence.

A results document records the conditions ggufbench derived from the data —
`engine_build`, `baseline` — and one row per (model, task): outcome, reason,
`score`, and `graded`, the counts per dimension that form the task signature
(ADR-0004). `run-2026-11-01` and `run-2026-11-02` share `engine_build` and
graded counts but were measured against different baselines, so their
`sql-join` rows are *not* comparable — that pair is what the refusal tests
exercise.

`../ggufbench_broken/` holds the malformed variants (invalid JSON, wrong
schema) kept outside the clean tree so whole-root queries stay honest.
