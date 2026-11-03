"""S2 run.inspect — answers come only from one buildwright run log (R1, R2, R4)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from debrief.adapters.buildwright_log import BuildwrightLog
from debrief.domain import FAIL, PASS
from debrief.errors import (
    PATH_OUTSIDE_ROOT,
    RUN_SOURCE_MISSING,
    SOURCE_UNPARSEABLE,
    DebriefError,
)
from debrief.mcp_server import RUN_ROOT_ENV, run_inspect
from debrief.use_cases import InspectRun

FIXTURES = Path(__file__).parent / "fixtures"
RUN_LOGS = FIXTURES / "buildwright"
BROKEN_RUN = RUN_LOGS / "run-2026-11-02T09-14Z.log"


@pytest.fixture
def run_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(RUN_ROOT_ENV, str(RUN_LOGS))
    yield


def test_inspect_run_maps_each_logged_step_to_a_finding() -> None:
    answer = InspectRun(BuildwrightLog(BROKEN_RUN)).run()

    assert isinstance(answer, list)
    assert len(answer) == 3
    worker = answer[1]

    assert worker.task == "sql-join"
    assert worker.role == "worker"
    assert worker.model == "qwen2.5-7b-instruct-q4_k_m"
    assert worker.outcome == FAIL
    assert "41 rows" in worker.reason
    assert worker.evidence == "r-2026-11-02T09-14Z/worker.patch"


def test_run_steps_carry_no_bench_knowledge() -> None:
    answer = InspectRun(BuildwrightLog(BROKEN_RUN)).run()

    assert isinstance(answer, list)
    assert all(row.signature is None and row.measure is None for row in answer)


def test_inspect_run_reports_a_passing_run_as_pass_findings() -> None:
    answer = InspectRun(BuildwrightLog(RUN_LOGS / "run-2026-11-03T10-00Z.log")).run()

    assert isinstance(answer, list)
    assert len(answer) == 1
    assert answer[0].task == "regex-extract"
    assert answer[0].outcome == PASS
    assert answer[0].role == "worker"


@pytest.mark.parametrize(
    ("log_name", "code"),
    [
        pytest.param("does-not-exist.log", RUN_SOURCE_MISSING, id="missing_log"),
        pytest.param("run-truncated.log", SOURCE_UNPARSEABLE, id="truncated_step_line"),
        pytest.param("run-no-task.log", SOURCE_UNPARSEABLE, id="no_task_header"),
        pytest.param("run-invalid-utf8.log", SOURCE_UNPARSEABLE, id="undecodable_bytes"),
    ],
)
def test_inspect_run_refuses_with_structured_error(log_name: str, code: str) -> None:
    answer = InspectRun(BuildwrightLog(RUN_LOGS / log_name)).run()

    assert isinstance(answer, DebriefError)
    assert answer.code == code
    assert answer.message
    assert answer.detail


@pytest.mark.parametrize(
    ("log_name", "token"),
    [
        pytest.param("run-bad-outcome-FAIL.log", "FAIL", id="uppercase_outcome"),
        pytest.param("run-bad-outcome-token.log", "timeout", id="unknown_outcome_token"),
    ],
)
def test_inspect_run_refuses_steps_with_outcome_tokens_outside_the_enum(
    log_name: str, token: str
) -> None:
    answer = InspectRun(BuildwrightLog(RUN_LOGS / log_name)).run()

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    assert token in answer.detail


def test_run_inspect_tool_answers_within_the_allowed_root(run_env: None) -> None:
    response = run_inspect("run-2026-11-02T09-14Z.log")

    assert response.error is None
    assert [row.role for row in response.findings] == ["planner", "worker", "reviewer"]
    assert response.findings[1].outcome == FAIL


@pytest.mark.parametrize(
    ("requested", "code"),
    [
        pytest.param("missing.log", RUN_SOURCE_MISSING, id="missing_log"),
        pytest.param("../pyproject.toml", PATH_OUTSIDE_ROOT, id="outside_root"),
        pytest.param("run-2026-11-02T09-14Z.log\x00", PATH_OUTSIDE_ROOT, id="nul_suffix"),
        pytest.param("\x00", PATH_OUTSIDE_ROOT, id="nul_only"),
    ],
)
def test_run_inspect_tool_refuses_with_structured_error(
    run_env: None, requested: str, code: str
) -> None:
    response = run_inspect(requested)

    assert response.findings == []
    assert response.error is not None
    assert response.error.code == code


@pytest.mark.skipif(os.geteuid() == 0, reason="permission modes do not bind for root")
def test_existing_run_log_behind_unreadable_parent_is_unparseable_not_missing(
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "run-locked" / "run-2026-11-02T09-14Z.log"
    log_file.parent.mkdir(parents=True)
    log_file.write_text("run: r\nengine_build: llama.cpp-b4937\ntask: sql-join\n", encoding="utf-8")
    log_file.parent.chmod(0o000)
    try:
        answer = InspectRun(BuildwrightLog(log_file)).run()
    finally:
        log_file.parent.chmod(0o755)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE


def test_headers_only_run_log_refuses_as_unparseable(tmp_path: Path) -> None:
    log_file = tmp_path / "run-headers-only.log"
    log_file.write_text(
        "\n".join(
            [
                "run: r-headers-only",
                "engine_build: llama.cpp-b4937",
                "task: sql-join",
                "result: fail failed_steps=01",
                "",
            ]
        ),
        encoding="utf-8",
    )

    answer = InspectRun(BuildwrightLog(log_file)).run()

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE


def _log_with_result(tmp_path: Path, name: str, result_line: str) -> Path:
    log_file = tmp_path / name
    log_file.write_text(
        "\n".join(
            [
                "run: r-result-header",
                "engine_build: llama.cpp-b4937",
                "task: sql-join",
                "step: 01 role=planner model=llama-3.2-3b-instruct-q4_k_m outcome=pass "
                'reason="plan covers every graded dimension" evidence=r-result-header/planner.md',
                "step: 02 role=worker model=qwen2.5-7b-instruct-q4_k_m outcome=fail "
                'reason="join limit exceeded" evidence=r-result-header/worker.patch',
                result_line,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return log_file


@pytest.mark.parametrize(
    ("result_line", "detail_token"),
    [
        pytest.param("result: pass", "declares pass", id="pass_header_over_a_logged_failure"),
        pytest.param(
            "result: fail failed_steps=03",
            "does not match",
            id="failed_steps_names_a_step_that_passed",
        ),
        pytest.param(
            "result: fail failed_steps=02,03",
            "does not match",
            id="failed_steps_lists_one_failure_too_many",
        ),
        pytest.param(
            "result: fail",
            "failed_steps",
            id="failure_header_without_a_failed_steps_list",
        ),
        pytest.param(
            "result: fail failed_steps=",
            "failed_steps is empty",
            id="empty_failed_steps_list",
        ),
        pytest.param(
            "result: timeout failed_steps=02",
            "timeout",
            id="header_outcome_outside_the_enum",
        ),
        pytest.param(
            "result: fail failed_steps=02 extra",
            "malformed result",
            id="malformed_header",
        ),
    ],
)
def test_result_header_contradicting_the_logged_steps_refuses_the_log(
    tmp_path: Path, result_line: str, detail_token: str
) -> None:
    answer = InspectRun(
        BuildwrightLog(_log_with_result(tmp_path, "contradicted.log", result_line))
    ).run()

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    assert detail_token in answer.detail


def test_result_header_agreeing_with_the_logged_steps_still_parses(tmp_path: Path) -> None:
    answer = InspectRun(
        BuildwrightLog(_log_with_result(tmp_path, "consistent.log", "result: fail failed_steps=02"))
    ).run()

    assert isinstance(answer, list)
    assert [row.outcome for row in answer] == [PASS, FAIL]


def test_failed_steps_without_zero_padding_still_matches_the_logged_step(tmp_path: Path) -> None:
    answer = InspectRun(
        BuildwrightLog(_log_with_result(tmp_path, "unpadded.log", "result: fail failed_steps=2"))
    ).run()

    assert isinstance(answer, list)
    assert [row.outcome for row in answer] == [PASS, FAIL]
