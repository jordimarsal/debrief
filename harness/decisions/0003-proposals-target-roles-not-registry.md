# ADR-0003: proposals target roles (BW_ROLE_*), never the registry (models.yaml)

- **Date:** 2026-11-02
- **Status:** accepted (project-level; decided by Jordi at project creation)
- **Feature:** project-level

## Context

buildwright separates two configuration layers: `models.yaml` is the registry
of what exists (adding a model ≈ five lines), while `BW_ROLE_*` (env or project
file, which always wins) assigns a model to a role — planner, worker, reviewer.
A debrief proposal answers "given this evidence, which model should hold which
role". That answer lives in the assignment layer, not the registry.

## Decision

`routing.propose` returns a `BW_ROLE_<ROLE>` diff as text (ADR-0001: never
applied by debrief). It does not propose edits to `models.yaml` unless the
evidence is about a model that is missing from the registry — in which case the
proposal says "registry gap: add X" as a note, not as an edit.

## Alternatives considered

- **Propose `models.yaml` diffs too** — rejected: it mixes "what exists" with
  "who does what", and the registry rarely changes from run evidence.
- **Write `BW_ROLE_*` directly (flag-gated)** — rejected: violates ADR-0001 and
  hands an agent a silent re-routing path.

## Consequences

- Proposals are small, reviewable env diffs a human can paste.
- debrief stays honest about scope: it advises the assignment layer only.
- If a proposal needs a model that is not registered, the finding names the
  registry gap explicitly instead of inventing an entry.
