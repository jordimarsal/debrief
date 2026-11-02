# Conventions

This document defines the coding and project conventions for the project. These rules
exist to enforce extreme homogeneity across the codebase. The goal is that any developer
can open any file and immediately understand its structure, naming, and intent without
having to learn a new style.

**Default policy: no comments.** Code must be self-documenting through clear naming and
structure. Comments are permitted only when they explain *why* a non-obvious decision was
made. Comments that describe *what* the code does are prohibited; if the code cannot be
understood without comments, rewrite the code.

---

## Style Rules

- PEP 8 enforced by `ruff format` + `ruff check`; line length 100.
- Type hints everywhere (`mypy --strict` clean); `from __future__ import annotations` in modules with cross-references.
- Dataclasses (frozen where possible) for value objects; no mutable default arguments, ever.
- Prefer composition and small pure functions; a module is importable without side effects.

---

## Naming Rules

- Modules and packages `snake_case`, classes `UpperCamel`, constants `UPPER_SNAKE`.
- Private-by-underscore (`_internal`) only at package boundaries, not as a decorum habit.
- Test names state the behavior: `test_expired_policy_is_rejected`, not `test_policy3`.

---

## File Structure

- `src/` layout (`src/<pkg>/`, `tests/`), never a flat script pile; pyproject.toml is the single build/dependency source.
- Tooling goes through **uv** by default: `uv add` / `uv remove` for dependencies, `uv sync` to materialize the locked venv, `uv run` to execute inside it; commit `uv.lock`.
- Package by feature (`policies/`, `billing/`); `__init__.py` stays empty unless exporting a deliberate API.
- CLI entry points via `if __name__ == "__main__"` only in thin launchers; logic lives in importable modules.

---

## Test Rules

- pytest with fixtures (no unittest classes); Arrange-Act-Assert with blank-line separation.
- Parametrize over cases: `@pytest.mark.parametrize` for reject/accept tables.
- Async code through `pytest-asyncio`; network/containers via `testcontainers-python`, never live endpoints.
- Type-check the tests too: they run under `mypy --strict` like production code.

---

## Error Handling

- Raise specific exception types defined in the package (`PolicyNotFound`), never bare `Exception`.
- No silent `except:` / `except Exception: pass` — catch the narrowest type and log or wrap with context (`raise X from err`).
- `try/except/else/finally` over deep nesting; validate at the boundary, trust types inside.

---

## Design Principles

Minimum bar for every stack and language — the language sections above may add
rules, never subtract these:

- **Semantic types over loose dictionaries.** Model domain concepts as enums,
  DTOs, value objects, records or dataclasses instead of passing raw
  dictionaries/maps around — the type name carries the meaning.
- **One concept per class, one responsibility per method** (Single
  Responsibility Principle).
- **No nested try/catch.** Extract a named function that handles one failure
  mode instead.
- **Prefer composition over inheritance.**
- **Prefer immutability:** final fields, immutable objects, unmodifiable
  collections — initialize once, never mutate shared state in place.
- **Tell, don't ask.** Behavior lives on the object that owns the data; value
  objects are rich (they validate and act), not anemic data bags.

---

## Commit Rules

Every commit in this repository follows
[Conventional Commits](https://www.conventionalcommits.org/):

- Format: `<type>(<optional scope>)!: <summary>` — e.g. `feat(auth): add refresh-token rotation`.
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `release`, `revert`.
- `!` (or a `BREAKING CHANGE:` footer) marks a breaking change.
- `.git/hooks/commit-msg` (source: `harness/tools/commit-msg`) enforces the
  format on every commit; `--no-verify` is reserved for exceptional cases,
  never a workaround.

---

## Code quality

- `ruff check`, `ruff format` and `mypy --strict` are gates: green before every commit, no per-line suppressions without a why-comment.
- Test and build commands run through uv (`uv run pytest tests`, `uv build`); a bare `python3 -m pytest` is the documented fallback only when uv is unavailable.
- Logging via the stdlib `logging` (or structlog), parameterized: `log.info("policy %s approved", pid)` — never f-strings in log calls.
- No `print()` outside CLIs; pin dependencies with hashes in CI (`pip install --require-hashes`).
<!-- harness:module:architecture:start -->
<!-- harness:architecture:start -->
## Architecture: Hexagonal (Ports & Adapters)

- Source dependencies point **inward only** (adapter → port → domain); the domain
  imports no framework, ORM or transport type.
- Ports live in the domain and are named by role (`PolicyStore`), never by technology;
  adapters implement them and own the mapping.
- Every use case is driven through its inbound port — adapters never call each other
  and never reach into the domain except through use cases.
<!-- harness:architecture:end -->

<!-- harness:module:architecture:end -->

---

## Project conventions (debrief)

- **Never write.** No `open(..., "w")`, no `.env`, `BW_ROLE_*` or `models.yaml`
  mutation anywhere in `src/`. Proposals are returned strings (ADR-0001, ADR-0003).
- **Tool names are namespaced**: `bench.*`, `run.*`, `routing.propose` — a tool's
  name names its port, so an agent never confuses "what was measured" with
  "what happened in this run".
- **Structured output only**: every tool returns findings (or a structured
  error) — never a prose blob.
- **Paths are validated at the adapter boundary**: resolve against an explicit
  allowed root, reject traversal outside it (security-audit A03).
- **Domain errors, adapter mapping**: the domain raises typed errors; the MCP
  adapter maps them to tool-error responses. No bare `except:` anywhere.
- **`print()` is allowed only in the CLI adapter** (it is a CLI by contract);
  the MCP adapter and the domain use `logging`, parameterized.
- **Formats stay in adapters**: nothing in the domain imports `mcp`, `ggufbench`
  or `buildwright` — adapters parse and map.
