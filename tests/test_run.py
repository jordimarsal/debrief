"""S2 run.inspect — answers come only from one buildwright run log (R1, R2, R4)."""

from __future__ import annotations

import ast
import hashlib
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
from debrief.mcp_server import DEFAULT_RUN_ROOT, RUN_ROOT_ENV, run_inspect
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

    assert [(row.role, row.outcome, row.evidence) for row in answer] == [
        ("planner", PASS, "r-2026-11-02T09-14Z/planner.md"),
        ("worker", FAIL, "r-2026-11-02T09-14Z/worker.patch"),
        ("reviewer", PASS, "r-2026-11-02T09-14Z/reviewer.md"),
    ]
    assert [row.model for row in answer] == [
        "llama-3.2-3b-instruct-q4_k_m",
        "qwen2.5-7b-instruct-q4_k_m",
        "phi-3.5-mini-instruct-q4_k_m",
    ]
    assert all(row.task == "sql-join" for row in answer)
    assert all(row.reason for row in answer)


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
        pytest.param("r-2026-11-02T09-14Z", RUN_SOURCE_MISSING, id="non_regular_path"),
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


def test_run_inspect_root_contract_is_stable() -> None:
    assert RUN_ROOT_ENV == "DEBRIEF_RUN_ROOT"
    assert DEFAULT_RUN_ROOT == "artifacts/buildwright"


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


def test_log_path_through_a_regular_file_parent_refuses_as_missing_not_crashing(
    tmp_path: Path,
) -> None:
    """The `findings()` clause catches both `FileNotFoundError` and
    `NotADirectoryError`: a log whose parent component is a regular file raises
    the latter on stat(), and the adapter answers a structured refusal — never
    the raw exception (R1)."""
    parent = tmp_path / "collide"
    parent.write_text("a regular file where the run root would be", encoding="utf-8")

    answer = InspectRun(BuildwrightLog(parent / "run-2026-11-02T09-14Z.log")).run()

    assert isinstance(answer, DebriefError)
    assert answer.code == RUN_SOURCE_MISSING
    assert answer.message
    assert answer.detail


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


def _fixture_fingerprint(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        str(path.relative_to(root)): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_serving_run_inspect_leaves_the_run_fixtures_byte_identical(run_env: None) -> None:
    before = _fixture_fingerprint(RUN_LOGS)
    assert len(before) >= 8

    broken = run_inspect("run-2026-11-02T09-14Z.log")
    passing = run_inspect("run-2026-11-03T10-00Z.log")
    refused = run_inspect("run-truncated.log")

    assert broken.error is None
    assert [row.role for row in broken.findings] == ["planner", "worker", "reviewer"]
    assert passing.error is None
    assert refused.error is not None
    assert refused.error.code == SOURCE_UNPARSEABLE
    assert _fixture_fingerprint(RUN_LOGS) == before


READ_PATH_MODULES = ("adapters/buildwright_log.py", "use_cases.py", "mcp_server.py")
WRITE_MODE_CHARS = frozenset("wxa+")
MUTATING_CALLS = frozenset(
    {
        "write_text",
        "write_bytes",
        "unlink",
        "mkdir",
        "rename",
        "replace",
        "remove",
        "rmdir",
        "rmtree",
        "touch",
        "truncate",
        "chmod",
    }
)
WRITE_MODULES = frozenset({"shutil"})


def _called_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _opens_for_writing(call: ast.Call) -> bool:
    mode: ast.AST | None = None
    for keyword in call.keywords:
        if keyword.arg == "mode":
            mode = keyword.value
    if mode is None and len(call.args) > 1:
        mode = call.args[1]
    if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str):
        # A non-literal mode cannot be proven read-only at this gate, so it counts
        # as an offender rather than passing silently.
        return mode is not None
    return bool(WRITE_MODE_CHARS & set(mode.value))


def _write_offenses(relative: str, tree: ast.AST) -> list[str]:
    offenses: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name in WRITE_MODULES for alias in node.names
        ):
            offenses.append(f"{relative} imports a filesystem-write module")
        elif isinstance(node, ast.ImportFrom) and node.module in WRITE_MODULES:
            offenses.append(f"{relative} imports a filesystem-write module")
        elif isinstance(node, ast.Call):
            name = _called_name(node.func)
            if name == "open" and _opens_for_writing(node):
                offenses.append(f"{relative} opens a file in a write mode")
            elif name in MUTATING_CALLS:
                offenses.append(f"{relative} calls {name}()")
    return offenses


def test_run_inspect_read_path_has_no_write_mode_open_or_mutation() -> None:
    package = Path(__file__).parents[1] / "src" / "debrief"
    offenses = [
        offense
        for relative in READ_PATH_MODULES
        for offense in _write_offenses(
            relative, ast.parse((package / relative).read_text(encoding="utf-8"))
        )
    ]

    assert offenses == []
