# Gauntlet Protocol (Sequential Adversarial Review)

> Installed by the harness `gauntlet` module. The gauntlet runs once per
> feature, after the last implementer batch and before the Completion Gate.
> It does not replace the human gates — both stay mandatory. Scale the depth
> to feature size; do not run full passes on a one-file change.

## Passes

| Pass | Question | Mechanical gate |
|---|---|---|
| G1 — Correctness | Every `R<n>` covered by a real test, every `T<n>` done | `bash harness/tools/gauntlet.sh --feature <name>` exit 0 |
| G2 — Adversarial | Malicious input, 10k concurrent, null/empty/negative, races, brittle tests | Agent judgment, recorded per finding |
| G3 — Maintainability | Architecture, conventions, SOLID where it reduces complexity, no blanket `except`, I/O at edges | Agent judgment + `harness/init.sh` green |
| G4 — Evidence | Logs on disk, report complete, nothing claimed without a path | Report file exists with 4 PASS lines |

G2 reuses the adversarial checklist from `docs/iteration-protocol.md` when
`iterative-refinement` is installed; otherwise the table above is the whole
checklist. Each finding is either fixed or explicitly defended with rationale
in the report. A defended finding still counts as a pass, but the rationale
must name the trade-off.

## Depth scaling

| Feature size | Depth |
|---|---|
| Trivial (1 file) | G1 + G4 only; note G2/G3 as `skipped (trivial)` with one-line reason |
| Medium (2-3 files) | G1–G4 in a single review sitting, one finding round max |
| Complex / very complex | Full G1–G4 with a fix round between verdict and re-run |

## Full workflow (dispatch flow)

1. The leader dispatches the reviewer with the feature name and nothing else.
2. The reviewer runs the passes in order, G1 first. A G1 REJECT stops the
   gauntlet — no judgment passes run on a feature whose mechanics are red.
3. Fixes go back to the implementer as one batch; the gauntlet re-runs from G1.
4. The report lands at `harness/progress/gauntlet_<name>.md` (format below).

## Hybrid workflow (one in-session agent)

Same passes, played sequentially by you — never two passes in one sitting
without writing the intermediate verdict to disk first:

1. **G1 mode.** Run `gauntlet.sh --feature <name>` yourself; save the output
   to `harness/logs/<feature>/gauntlet-g1.log`. Non-zero means stop and fix.
2. **G2+G3 mode.** Walk the checklists against the diff with fresh eyes:
   re-read each changed file top to bottom instead of trusting your batch
   memory. Log findings to `harness/logs/<feature>/gauntlet-g23.log`.
3. **G4 mode.** Run `harness/init.sh`, confirm green, write the report file.
4. **Escalate** to a real reviewer dispatch when the feature has more than
   ~12 tasks, touches critical files, or G2/G3 is subjective (no mechanical
   gate covers the doubt). Fresh context beats speed there.

Trade-off, stated plainly: hybrid gauntlet trades independent-context
criticism for velocity. The per-pass logs are what keep that trade honest —
a pass without a log is not a pass.

## Report format (`harness/progress/gauntlet_<name>.md`)

```markdown
# Gauntlet — feature <name>

- G1 correctness: PASS (gauntlet.sh exit 0, <n>/<n> tasks done, traceability <m>/<m>)
- G2 adversarial: PASS (k findings, all fixed or defended below)
- G3 maintainability: PASS (init.sh green, conventions checked)
- G4 evidence: PASS (logs: <paths>)

## Findings (if any)
1. [G2] <description> — fixed in <file> | defended: <rationale>
```

**Verdict:** `PASS` iff all four lines say PASS. Anything else rejects the
Completion Gate request.
