# ADR-0002: two ports, one finding — bench and run answer independently

- **Date:** 2026-11-02
- **Status:** accepted (project-level; decided by Jordi at project creation)
- **Feature:** project-level

## Context

ggufbench artifacts and buildwright run logs answer different questions. The
catalog is a historical measurement under recorded conditions (task signature,
baseline, engine build): two rows compare only inside the same signature. A run
log is one episode: gates, failures, tool calls. Neither converts into the
other, their formats evolve at different speeds, and their freshness differs.

## Decision

debrief exposes two independent ports — `bench` (reads ggufbench artifacts) and
`run` (reads one buildwright run log) — that share one domain type, `Finding`,
and never import each other. `ProposeRole` (S3) is the only use case allowed to
read findings from both. Tool names carry the port (`bench.*`, `run.*`) so an
agent cannot confuse "what was measured" with "what happened in this run".

## Alternatives considered

- **One unified evidence store** — rejected: converting run logs into catalog
  rows (or vice versa) fabricates comparability that the data does not have.
- **Two separate MCP servers** — rejected for v1: one install, one idea
  ("answer from receipts"), and the cross-citation in `ProposeRole` is the
  actual product; two servers would split it across two configs.
- **bench inside ggufbench / run inside buildwright** — rejected: they are the
  producers; debrief is the reader, and embedding it would couple the reader's
  release cycle to each producer's.

## Consequences

- Each port's adapter can break and ship independently; the other keeps
  answering.
- The comparability rule (refuse, don't average) is enforced once, in the
  domain, for both ports.
- Cross-citation ("this run fails the way the catalog already recorded") is
  deliberately deferred to S3 — not in the walking skeleton.
