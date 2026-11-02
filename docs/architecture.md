# Architecture — debrief (Hexagonal — Ports & Adapters)

debrief answers agent questions from receipts: what ggufbench measured (**bench**)
and where a buildwright run broke (**run**) — then proposes role changes as text
(**propose**). Hexagonal because there are two evidence sources that must stay
independently swappable, and a domain — findings and their comparability rules —
that must not know either source's file formats.

## Principles

- **The domain owns the ports.** Interfaces the domain needs (artifact stores,
  run logs) are defined inside the domain, in domain language — never derived
  from a framework, the MCP SDK, ggufbench or buildwright.
- **Adapters are replaceable details.** The MCP transport, the CLI, the ggufbench
  artifact reader and the buildwright log reader are all adapters; swapping one
  must not touch a single line of domain or use-case code.
- **Use cases orchestrate.** QueryBench, InspectRun and ProposeRole are the only
  entry points for driving the domain.
- **Dependency rule.** Source code dependencies point inward only:
  adapter → port → domain. The domain imports nothing outward — in particular
  nothing from `mcp`, `ggufbench` or `buildwright`.

## The domain

- **`Finding`** is the shared currency: model, task, outcome, reason, evidence
  pointer. Every tool response is findings or a structured error.
- Comparability lives here: rows with different task signatures are refused,
  not merged (ADR-0004).
- The domain has no write path. ProposeRole returns text; nothing persists
  (ADR-0001, ADR-0003).

## Ports

| Port | Kind | Role | Adapter |
| --- | --- | --- | --- |
| `QueryBench` | use case (driving) | "what did ggufbench measure?" | MCP tool `bench.*`, CLI |
| `InspectRun` | use case (driving) | "where did this run break?" | MCP tool `run.*`, CLI |
| `ProposeRole` | use case (driving) | "what would you change?" (text diff) | MCP tool `routing.propose`, CLI |
| `BenchStore` | driven (port) | read ggufbench artifacts | ggufbench-artifacts adapter |
| `RunLog` | driven (port) | read one buildwright run log | buildwright-log adapter |

## Data flow

MCP tool call (driving adapter) → use case → driven port → adapter reads
artifacts/logs → `Finding`s → structured tool response. `ProposeRole` composes
`QueryBench` and `InspectRun` findings into a `BW_ROLE_*` diff **as text** —
S3 only; S1 and S2 never cross (ADR-0002).

## Slice map (parent `debrief` — approved at its Spec Gate)

| Slice | Name | Demoable outcome |
| --- | --- | --- |
| S1 | `bench_query` | an agent asks what ggufbench measured and gets findings from real artifacts |
| S2 | `run_inspect` | an agent asks where a buildwright run broke and gets structured findings |
| S3 | `role_propose` | an agent gets a `BW_ROLE_*` proposal citing both ports — printed, never written |

Each slice is a feature (`part_of: debrief`) with its own lite spec and both
human gates (`docs/slicing-protocol.md`).

## Out of scope (v1)

Langfuse traces, HTTP transport, applying proposals, `models.yaml` mutation,
kanban mirrors, anything network-facing.
