"""The mechanical quality gates stay configured over src and tests (R8)."""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).parents[1] / "pyproject.toml"


def test_quality_gate_tooling_is_configured_over_src_and_tests() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    mypy = config["tool"]["mypy"]
    assert mypy["strict"] is True
    assert mypy["files"] == ["src", "tests"]
    assert {"E", "F", "W", "I", "UP", "B"} <= set(config["tool"]["ruff"]["lint"]["select"])
    assert config["project"]["scripts"]["debrief"] == "debrief:main"

    dev = config["dependency-groups"]["dev"]
    for gate_tool in ("pytest", "ruff", "mypy"):
        assert any(str(dependency).startswith(gate_tool) for dependency in dev), gate_tool
