"""debrief — answers agent questions from receipts; never writes (ADR-0001)."""

from __future__ import annotations

from typing import Any

__all__ = ["main"]


def __getattr__(name: str) -> Any:
    # Lazy on purpose: `import debrief` (and so debrief.domain) must not pull in the mcp SDK.
    if name == "main":
        from debrief.mcp_server import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
