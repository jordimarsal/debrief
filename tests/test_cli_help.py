"""CLI surface: --help/--version answer and exit; unknown args fail fast (no server start)."""

from __future__ import annotations

import importlib.metadata

import pytest

from debrief.mcp_server import _HELP, main


def test_help_prints_usage_and_exits_0(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["debrief", "--help"])

    main()  # must return without starting the stdio session

    out = capsys.readouterr().out
    assert out == _HELP
    for needle in (
        "usage: debrief",
        "bench.query",
        "run.inspect",
        "routing.propose",
        "DEBRIEF_BENCH_ROOT",
        "DEBRIEF_RUN_ROOT",
        "DEBRIEF_LOG_LEVEL",
        "exit codes",
    ):
        assert needle in out


def test_short_help_flag_is_equivalent(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["debrief", "-h"])

    main()

    assert capsys.readouterr().out == _HELP


def test_version_prints_package_version(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["debrief", "--version"])

    main()

    out = capsys.readouterr().out
    assert out == f"debrief {importlib.metadata.version('debrief')}\n"


@pytest.mark.parametrize("argv", [["debrief", "--wat"], ["debrief", "run-2026-11-01"]])
def test_unknown_arguments_exit_2_without_starting(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    monkeypatch.setattr("sys.argv", argv)

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "unrecognized argument(s)" in err
    assert "--help" in err
