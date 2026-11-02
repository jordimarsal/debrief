"""Smoke gate: the package installs and exposes its CLI entry point.

harness/init.sh runs `uv run pytest tests` as the project's test gate; this file
is the minimum green evidence that the scaffold is importable. Feature work
replaces this file's role with real per-module tests.
"""

import debrief


def test_cli_entrypoint_is_callable() -> None:
    assert callable(debrief.main)
