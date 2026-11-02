# ADR-0004: refuse incomparable rows — never average across task signatures

- **Date:** 2026-11-02
- **Status:** accepted (project-level; decided by Jordi at project creation)
- **Feature:** project-level

## Context

A ggufbench row is only comparable with rows measured under the same task
signature (graded counts per dimension), baseline and engine build — ggufbench
itself derives the signature from the data because version labels have lied
before. Two rows with different signatures answer different questions. An
agent asking debrief for "the best model" does not know this; a naive average
would fabricate a winner.

## Decision

When a query's candidate rows do not share a task signature (or baseline/engine
condition), debrief refuses to rank or average them: it returns the rows grouped
by signature with the reason, and lets the caller choose a cohort. Refusal is a
structured finding, not an error.

## Alternatives considered

- **Average and flag with a warning** — rejected: the number travels; the
  warning does not.
- **Pick the largest homogeneous cohort silently** — rejected: hides the
  exclusion, the exact habit ggufbench exists to end.

## Consequences

- Answers may be longer (groups + reason) but are always honest.
- The comparability rule is enforced once, in the domain, for both ports.
- Ranking queries need an explicit cohort (signature/baseline) in v1 tools.
