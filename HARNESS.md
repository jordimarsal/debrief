# Harness — debrief

Installed with [harness](https://github.com/jordimarsal/harness) (`opencode`, `v0.10.3-1-g271c75b`).

- **Stack detected:** python
- **Architecture:** hexagonal
- **Workflow:** hybrid — one in-session agent; same human gates; evidence logs in harness/logs/ (see the workflow section of AGENTS.md)
- **Roles:** Leader · Spec Author · Implementer · Reviewer (`.opencode/agent/`)
- **Gates:** `harness/CHECKPOINTS.md` · `docs/verification.md`
- **Process:** `docs/specs.md` — Spec-Driven Development with a human approval gate
- **Commits:** Conventional Commits — enforced by `.git/hooks/commit-msg` (source: `harness/tools/commit-msg`)

## Next

1. Edit `docs/architecture.md` and `docs/conventions.md` for this project.
2. Add features to `harness/feature_list.json`.
3. Project-specific additions to AGENTS.md (mandatory steps, map rows) go
   inside the `harness:project` block at the end of the file — preserved
   verbatim on --update.
3. Start the leader: `opencode`
4. Update later: re-run install.sh with `--update` (keeps specs, progress and settings).

First prompt:

> Read AGENTS.md and start the leader workflow. Pick the first pending feature.
