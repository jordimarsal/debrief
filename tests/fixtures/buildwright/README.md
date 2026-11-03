# buildwright run log fixtures

One file per run, in buildwright's log format: `key: value` header lines
(`run:`, `engine_build:`, `task:`, `roles:`, `result:`), then one `step:` line
per logged step, then the `result:` line. Free text is allowed around these —
debrief reads receipts, not the whole log.

`run-truncated.log` (a step line cut off mid-reason), `run-no-task.log` (no
`task:` header), `run-bad-outcome-FAIL.log` / `run-bad-outcome-token.log`
(`outcome=` tokens outside the pass/fail enum) and `run-invalid-utf8.log`
(undecodable bytes) are the malformed variants.
