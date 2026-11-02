# CHECKPOINTS — Final state evaluation

> In multi-agent systems, the destination is evaluated, not the journey.
> These are the objective checkpoints a judge (human or AI) can use
> to decide if the project is healthy.

## C1 — Harness is complete

- [ ] The 4 base files exist: `CLAUDE.md` or `AGENTS.md` (entry point at project root), `harness/init.sh`, `harness/feature_list.json`, `harness/progress/current.md`.
- [ ] The 3 docs exist: `docs/architecture.md`, `docs/conventions.md`, `docs/verification.md`.
- [ ] `harness/init.sh` finishes with exit code 0.

## C2 — State is coherent

- [ ] At most one feature `in_progress` in `harness/feature_list.json`.
- [ ] Every `done` feature has passing tests.
- [ ] `harness/progress/current.md` is empty or describes the active session (no stale data).

## C3 — Code respects architecture

- [ ] `src/` only contains modules foreseen in `docs/architecture.md`.
- [ ] No debug prints, no context-free TODOs.

## C4 — Verification is real

- [ ] `tests/` has at least one test per `src/` module.
- [ ] All tests pass (`harness/init.sh` green).

## C5 — Session closed properly

- [ ] No suspicious untracked files.
- [ ] `harness/progress/history.md` has an entry for the last session.
- [ ] The last worked feature reflects its correct state.

## C6 — Spec Driven Development

- [ ] Every feature in `spec_ready`, `in_progress`, or `done` has its `harness/specs/<name>/` folder with 3 files: `requirements.md`, `design.md`, `tasks.md`.
- [ ] `requirements.md` uses strict EARS notation.
- [ ] Every `done` feature has all tasks marked `[x]` in `tasks.md`.
- [ ] Each `R<n>` from `requirements.md` is covered by at least one concrete test in `tests/`.

---

**How to use this file:** a reviewer agent (`.claude/agents/reviewer.md` in Claude mode, `.opencode/agent/reviewer.md` in opencode mode) walks through each checkbox, marks `[x]` or `[ ]`, and rejects session closure if boxes remain unchecked in C1-C6.

<!-- harness:module:audit-checkpoint:start -->
## C7 — Audit (conditional)

- [ ] The latest progress entry contains the audit report (`audit_level` standard/strict) or the manual security-checklist confirmation (`basic`).
- [ ] Findings above the configured audit level's threshold are resolved or explicitly waived in the progress entry.
<!-- harness:module:audit-checkpoint:end -->

<!-- harness:module:gauntlet-checkpoint:start -->
## C8 — Gauntlet (conditional, gauntlet module)

- [ ] `bash harness/tools/gauntlet.sh --feature <name>` exits 0 (G1 mechanical gate green, no vacuous PASS).
- [ ] `harness/progress/gauntlet_<name>.md` records PASS on all four passes (G1–G4); every finding is fixed or defended with rationale.
- [ ] Per-pass evidence exists on disk (`harness/logs/<feature>/gauntlet-*.log` in hybrid; reviewer verdict in full).
<!-- harness:module:gauntlet-checkpoint:end -->
