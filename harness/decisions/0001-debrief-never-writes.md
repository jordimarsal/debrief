# ADR-0001: debrief never writes

- **Date:** 2026-11-02
- **Status:** accepted (project-level; decided by Jordi at project creation)
- **Feature:** project-level

## Context

debrief reads evidence (ggufbench artifacts, buildwright run logs) and answers
agent questions. The MCP precedent in this portfolio — a PNG tool that edited
files in place — showed how easily a "small tool" grows a destructive side
effect that an agent can trigger without meaning to. A tool that both reads
evidence and writes configuration invites an agent to "fix" a failing run by
silently re-routing models.

## Decision

Every debrief tool is read-only or returns a proposal as text. Nothing in
`src/` opens files for writing; no tool mutates `.env`, `BW_ROLE_*`,
`models.yaml` or any other file.

## Alternatives considered

- **Read-mostly with an opt-in `apply` tool** — rejected for v1: the write path
  exists from day one and only the flag changes. If applying proposals is ever
  wanted, it should be a separate, carefully-gated feature (and likely a
  separate process), not a tool here.
- **Sandboxed writes to a copy** — rejected for v1: still a write path, still
  an agent-triggerable mutation, with extra complexity.

## Consequences

- Simpler security posture: `audit-security` path-traversal findings apply to
  reads only; no write validation to maintain.
- The value of a proposal is carried by the human (or a future, explicitly
  scoped feature) applying it.
- Cheap to reverse now; expensive to reverse later once callers depend on
  applying — revisit before ever adding a write path.
