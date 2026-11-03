# Tasks: debrief_role_propose

- [x] T1: Repair both adapters' invalid `except FileNotFoundError, NotADirectoryError:` clauses (`adapters/ggufbench_store.py::_is_regular_file`, `adapters/buildwright_log.py::findings`) so both modules import, and verify the boundary validations the proposal text depends on: identifier fields are single-line whitespace-free tokens, free-text fields are single lines with no control chars (incl. U+0085/U+2028/U+2029), scores are finite floats — refusing `source_unparseable`; end-to-end tests prove a poisoned bench cohort (newline- and Unicode-separator-forged `- `/`+ ` lines incl. a `models.yaml` forge) answers a structured error and never renders proposal text (refs R1, R6)
      depends_on: (none)
      refs: R1, R6

- [x] T2: Complete/verify `ProposeRole` in `use_cases.py`: compose QueryBench + InspectRun (the only use case crossing ports), propagate either port's structured error as the whole answer, and render the BW_ROLE_* diff as text — only failing steps propose, canonical role (uppercase + strip existing `BW_ROLE_` prefix, never `BW_ROLE_BW_ROLE_*`, one proposal per role), `- `/`+ `/why run/why bench/signature/not-applied lines, keep-the-role notes (unmeasured task, no passing candidate, role-less step), and the literal all-passed text; tests: happy-path diff from real fixtures, role-token table (bare/uppercase/prefixed/lowercase-prefixed), notes table, all-passed text, port-error propagation table (refs R5, R1)
      depends_on: T1
      refs: R5, R1

- [x] T3: Comparability refusal and role targeting: cohort signature goes through the domain's `shared_signature`; an incomparable cohort (rows spanning signatures, or none carrying one) answers the `incomparable_rows` structured error naming every signature key — never a winner, average, or silently narrowed cohort — at use-case and tool level; tests assert every `- `/`+ ` diff line targets `BW_ROLE_*` and no `models.yaml` change is proposed anywhere in the answer (refs R7, R6)
      depends_on: T2
      refs: R7, R6

- [x] T4: `routing.propose` tool wiring, read-only proof, and slice gates: `_resolve_within` guards for both arguments (`DEBRIEF_BENCH_ROOT` default `artifacts/ggufbench`, `DEBRIEF_RUN_ROOT` default `artifacts/buildwright`) answering `ProposalResponse`, with the NUL/outside-root refuse table; fixtures byte-identical (contents + mtime) after serving and no write-mode opens on the slice's read path; run `harness/init.sh`, `uv run pytest tests`, ruff, `mypy --strict`, audit-security, gauntlet green; record the demo note (command + output) in the slice's approval record (refs R1, R2)
      depends_on: T3
      refs: R1, R2
