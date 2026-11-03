"""S3 routing.propose — a BW_ROLE_* diff as text from both ports (R1, R2, R5–R7)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from debrief.adapters.buildwright_log import BuildwrightLog
from debrief.adapters.ggufbench_store import RESULTS_FILE, GgufbenchStore
from debrief.errors import (
    BENCH_SOURCE_MISSING,
    INCOMPARABLE_ROWS,
    PATH_OUTSIDE_ROOT,
    RUN_SOURCE_MISSING,
    SOURCE_UNPARSEABLE,
    DebriefError,
)
from debrief.mcp_server import BENCH_ROOT_ENV, RUN_ROOT_ENV, routing_propose
from debrief.use_cases import InspectRun, ProposeRole, QueryBench

FIXTURES = Path(__file__).parent / "fixtures"
BENCH_ROOT = FIXTURES / "ggufbench"
BROKEN_ROOT = FIXTURES / "ggufbench_broken"
RUN_LOGS = FIXTURES / "buildwright"
SQL_JOIN_LOG = RUN_LOGS / "run-2026-11-02T09-14Z.log"
PASSING_LOG = RUN_LOGS / "run-2026-11-03T10-00Z.log"
LLAMA = "llama-3.1-8b-instruct-q4_k_m"
QWEN = "qwen2.5-7b-instruct-q4_k_m"


@pytest.fixture
def proposal_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(BENCH_ROOT_ENV, str(BENCH_ROOT))
    monkeypatch.setenv(RUN_ROOT_ENV, str(RUN_LOGS))
    yield


def propose(bench_root: Path, run_log: Path) -> str | DebriefError:
    return ProposeRole(
        QueryBench(GgufbenchStore(bench_root)), InspectRun(BuildwrightLog(run_log))
    ).run()


def test_propose_role_diffs_the_failed_role_to_the_bench_winner() -> None:
    answer = propose(BENCH_ROOT / "run-2026-11-01", SQL_JOIN_LOG)

    assert isinstance(answer, str)
    assert (
        "proposal: BW_ROLE_WORKER holds qwen2.5-7b-instruct-q4_k_m, which failed task sql-join"
        in answer
    )
    assert f"- BW_ROLE_WORKER={QWEN}" in answer
    assert f"+ BW_ROLE_WORKER={LLAMA}" in answer
    assert "why run:" in answer and "why bench:" in answer
    assert "score 0.86" in answer
    assert "signature: joins:40,limits:10,syntax:20@b4937-graded-baseline@llama.cpp-b4937" in answer
    assert "not applied" in answer


def test_proposal_diff_lines_target_bw_roles_only() -> None:
    answer = propose(BENCH_ROOT / "run-2026-11-01", SQL_JOIN_LOG)

    assert isinstance(answer, str)
    diff_lines = [line for line in answer.splitlines() if line[:2] in {"- ", "+ "}]
    assert diff_lines
    assert all(line[2:].startswith("BW_ROLE_") for line in diff_lines)


def test_propose_role_refuses_rows_spanning_two_baselines() -> None:
    answer = propose(BENCH_ROOT, SQL_JOIN_LOG)

    assert isinstance(answer, DebriefError)
    assert answer.code == INCOMPARABLE_ROWS
    assert "b4937-graded-baseline" in answer.detail
    assert "b4945-graded-baseline" in answer.detail


def test_propose_role_reports_when_no_step_failed() -> None:
    answer = propose(BENCH_ROOT / "run-2026-11-01", PASSING_LOG)

    assert answer == "no proposal: every logged step passed"


@pytest.mark.parametrize(
    "role_token",
    [
        pytest.param("worker", id="bare_lowercase"),
        pytest.param("WORKER", id="bare_uppercase"),
        pytest.param("BW_ROLE_WORKER", id="prefixed_as_written_in_the_roles_header"),
        pytest.param("bw_role_worker", id="prefixed_lowercase"),
    ],
)
def test_role_tokens_carrying_the_env_prefix_still_render_a_pasteable_diff(
    tmp_path: Path, role_token: str
) -> None:
    run_log = tmp_path / "prefixed-role.log"
    run_log.write_text(
        "\n".join(
            [
                "run: r-synthetic-prefixed-role",
                "engine_build: llama.cpp-b4937",
                "task: sql-join",
                "roles: BW_ROLE_WORKER=qwen2.5-7b-instruct-q4_k_m",
                f"step: 01 role={role_token} model={QWEN} outcome=fail "
                'reason="join limit exceeded" evidence=r-prefixed/worker.patch',
                "result: fail failed_steps=01",
                "",
            ]
        ),
        encoding="utf-8",
    )

    answer = propose(BENCH_ROOT / "run-2026-11-01", run_log)

    assert isinstance(answer, str)
    assert f"proposal: BW_ROLE_WORKER holds {QWEN}, which failed task sql-join" in answer
    assert f"+ BW_ROLE_WORKER={LLAMA}" in answer
    assert "BW_ROLE_BW_ROLE_" not in answer


def _escaping_bench_tree(tmp_path: Path) -> Path:
    """A bench cohort whose only sql-join row (a winning one) lives outside the root."""
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            {
                "engine_build": "llama.cpp-b4937",
                "baseline": "b4937-graded-baseline",
                "rows": [
                    {
                        "model": "LEAKED-model",
                        "task": "sql-join",
                        "outcome": "pass",
                        "score": 1.0,
                        "reason": "row read outside the evidence root",
                        "artifact": "/outside/leaked.transcript",
                        "graded": {"joins": 40, "limits": 10, "syntax": 20},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "ggufbench"
    run_dir = root / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / RESULTS_FILE).symlink_to(outside)
    return root


@pytest.mark.parametrize(
    "subpath",
    [pytest.param("", id="artifact_root_scan"), pytest.param("r1", id="run_dir_requested")],
)
def test_symlink_escaping_the_bench_root_never_reaches_the_proposal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, subpath: str
) -> None:
    root = _escaping_bench_tree(tmp_path)
    monkeypatch.setenv(BENCH_ROOT_ENV, str(root))

    response = routing_propose(subpath, "run-2026-11-02T09-14Z.log")

    assert response.proposal == ""
    assert response.error is not None
    assert response.error.code == SOURCE_UNPARSEABLE
    assert "outside the artifact root" in response.error.detail
    assert "LEAKED-model" not in response.error.detail


@pytest.mark.parametrize("outcome_token", ["FAIL", "Pass", "timeout"])
def test_unknown_outcome_step_never_yields_the_all_passed_claim(
    tmp_path: Path, outcome_token: str
) -> None:
    run_log = tmp_path / "hostile-outcome.log"
    run_log.write_text(
        "\n".join(
            [
                "run: r-synthetic-hostile-outcome",
                "engine_build: llama.cpp-b4937",
                "task: sql-join",
                "roles: BW_ROLE_WORKER=qwen2.5-7b-instruct-q4_k_m",
                f"step: 01 role=worker model={QWEN} outcome={outcome_token} "
                'reason="join limit exceeded" evidence=r-hostile/worker.patch',
                "result: fail failed_steps=01",
                "",
            ]
        ),
        encoding="utf-8",
    )

    answer = propose(BENCH_ROOT / "run-2026-11-01", run_log)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    assert outcome_token in answer.detail


@pytest.mark.parametrize(
    "artifact_dir",
    [
        "nonfinite-score-nan",
        "nonfinite-score-infinity",
        "nonfinite-score-neg-infinity",
        "huge-int-score",
    ],
)
def test_poisoned_bench_scores_never_reach_the_proposal_ranking(artifact_dir: str) -> None:
    answer = propose(BROKEN_ROOT / artifact_dir, SQL_JOIN_LOG)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    assert "evil-model" not in answer.detail


def test_propose_role_keeps_the_role_when_bench_never_measured_the_task(tmp_path: Path) -> None:
    run_log = tmp_path / "unmeasured.log"
    run_log.write_text(
        "\n".join(
            [
                "run: r-synthetic-unmeasured",
                "engine_build: llama.cpp-b4937",
                "task: regex-extract",
                "roles: BW_ROLE_WORKER=qwen2.5-7b-instruct-q4_k_m",
                f"step: 01 role=worker model={QWEN} outcome=fail "
                'reason="anchors missed" evidence=r-synthetic/worker.patch',
                "result: fail failed_steps=01",
                "",
            ]
        ),
        encoding="utf-8",
    )

    answer = propose(BENCH_ROOT / "run-2026-11-02", run_log)

    assert isinstance(answer, str)
    assert "note: ggufbench never measured regex-extract" in answer
    assert f"keeping BW_ROLE_WORKER={QWEN}" in answer


def test_propose_role_keeps_the_role_when_no_other_model_passed(tmp_path: Path) -> None:
    run_log = tmp_path / "solo.log"
    run_log.write_text(
        "\n".join(
            [
                "run: r-synthetic-solo",
                "engine_build: llama.cpp-b4937",
                "task: sql-join",
                "roles: BW_ROLE_WORKER=gemma-2-9b-it-q4_k_m",
                "step: 01 role=worker model=gemma-2-9b-it-q4_k_m outcome=fail "
                'reason="join limit exceeded" evidence=r-synthetic-solo/worker.patch',
                "result: fail failed_steps=01",
                "",
            ]
        ),
        encoding="utf-8",
    )

    answer = propose(BENCH_ROOT / "run-2026-11-02", run_log)

    assert isinstance(answer, str)
    assert "note: no passing model for sql-join in the bench cohort" in answer
    assert "keeping BW_ROLE_WORKER=gemma-2-9b-it-q4_k_m" in answer


@pytest.mark.parametrize(
    ("bench_root", "run_log", "code"),
    [
        pytest.param(
            BENCH_ROOT / "does-not-exist", SQL_JOIN_LOG, BENCH_SOURCE_MISSING, id="bench_missing"
        ),
        pytest.param(
            BENCH_ROOT / "run-2026-11-01",
            RUN_LOGS / "does-not-exist.log",
            RUN_SOURCE_MISSING,
            id="run_missing",
        ),
    ],
)
def test_propose_role_propagates_structured_errors_from_both_ports(
    bench_root: Path, run_log: Path, code: str
) -> None:
    answer = propose(bench_root, run_log)

    assert isinstance(answer, DebriefError)
    assert answer.code == code


def test_routing_propose_tool_renders_the_recorded_demo_diff(proposal_env: None) -> None:
    response = routing_propose("run-2026-11-01", "run-2026-11-02T09-14Z.log")

    assert response.error is None
    assert f"+ BW_ROLE_WORKER={LLAMA}" in response.proposal
    assert "never writes" in response.proposal


def test_routing_propose_tool_refuses_incomparable_rows(proposal_env: None) -> None:
    response = routing_propose(".", "run-2026-11-02T09-14Z.log")

    assert response.proposal == ""
    assert response.error is not None
    assert response.error.code == INCOMPARABLE_ROWS


@pytest.mark.parametrize(
    ("bench_path", "run_path"),
    [
        pytest.param("run-2026-11-01\x00", "run-2026-11-02T09-14Z.log", id="nul_in_bench_path"),
        pytest.param("run-2026-11-01", "run-2026-11-02T09-14Z.log\x00", id="nul_in_run_path"),
    ],
)
def test_routing_propose_tool_refuses_nul_bytes_in_path_arguments(
    proposal_env: None, bench_path: str, run_path: str
) -> None:
    response = routing_propose(bench_path, run_path)

    assert response.proposal == ""
    assert response.error is not None
    assert response.error.code == PATH_OUTSIDE_ROOT


@pytest.mark.parametrize(
    ("field", "sep", "forged_line"),
    [
        pytest.param(
            "model", "\n", "+ BW_ROLE_WORKER=evil-model", id="model_forges_a_role_change_line"
        ),
        pytest.param(
            "model",
            "\n",
            "+ models.yaml: rewrite-every-role",
            id="model_forges_a_registry_line",
        ),
        pytest.param("reason", "\n", "+ BW_ROLE_WORKER=evil-model", id="reason_forges_a_role_line"),
        pytest.param(
            "artifact",
            "\n",
            "- BW_ROLE_WORKER=qwen2.5-7b-instruct-q4_k_m",
            id="artifact_forges_removal",
        ),
        pytest.param(
            "reason",
            " ",
            "+ BW_ROLE_WORKER=evil-model",
            id="reason_forges_via_unicode_line_separator",
        ),
    ],
)
def test_poisoned_bench_fields_never_reach_the_proposal_output(
    tmp_path: Path, field: str, sep: str, forged_line: str
) -> None:
    """End-to-end: a cohort with a poisoned string field refuses as a structured
    error, so no forged `- `/`+ ` diff line can reach the caller's output (R6
    holds even when the artifact itself is the attack). The last row forges
    through a Unicode line separator (U+2029), which a pure control-character
    check would let through because it sits above ``ord(ch) < 0x20``."""
    row = {
        "model": "trusted-winner",
        "task": "sql-join",
        "outcome": "pass",
        "score": 0.99,
        "reason": "clean reason",
        "artifact": "run-2026-11-01/sql-join/winner.transcript",
        "graded": {"joins": 40, "limits": 10, "syntax": 20},
    }
    row[field] = f"trusted-value{sep}{forged_line}"
    poisoned = tmp_path / "poisoned-bench"
    poisoned.mkdir()
    document = {
        "engine_build": "llama.cpp-b4937",
        "baseline": "b4937-graded-baseline",
        "rows": [row],
    }
    (poisoned / RESULTS_FILE).write_text(json.dumps(document), encoding="utf-8")

    answer = propose(poisoned, SQL_JOIN_LOG)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    # The refusal is the whole output: the answer is never proposal text, so
    # the forged diff line cannot be rendered to the caller (not even as a
    # `- `/`+ ` line of a seemingly valid diff).
    assert not isinstance(answer, str)


def test_propose_does_not_claim_all_passed_for_a_step_stripped_log(tmp_path: Path) -> None:
    bench_root = tmp_path / "bench"
    bench_root.mkdir()
    document = {
        "engine_build": "llama.cpp-b4937",
        "baseline": "b4937-graded-baseline",
        "rows": [
            {
                "model": QWEN,
                "task": "sql-join",
                "outcome": "fail",
                "score": 0.52,
                "reason": "join limit exceeded",
                "artifact": "run/sql-join/qwen.transcript",
                "graded": {"joins": 40, "limits": 10, "syntax": 20},
            }
        ],
    }
    (bench_root / RESULTS_FILE).write_text(json.dumps(document), encoding="utf-8")

    run_log = tmp_path / "run-step-stripped.log"
    run_log.write_text(
        "\n".join(
            [
                "run: r-step-stripped",
                "engine_build: llama.cpp-b4937",
                "task: sql-join",
                "result: fail failed_steps=01",
                "",
            ]
        ),
        encoding="utf-8",
    )

    answer = propose(bench_root, run_log)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE


@pytest.mark.parametrize(
    "result_line",
    [
        pytest.param("result: pass", id="pass_header_over_a_logged_failure"),
        pytest.param("result: fail failed_steps=07", id="failed_steps_names_a_step_that_passed"),
    ],
)
def test_propose_does_not_claim_all_passed_for_a_log_whose_result_header_lies(
    tmp_path: Path, result_line: str
) -> None:
    run_log = tmp_path / "run-contradicted-header.log"
    run_log.write_text(
        "\n".join(
            [
                "run: r-contradicted-header",
                "engine_build: llama.cpp-b4937",
                "task: sql-join",
                f"step: 01 role=worker model={QWEN} outcome=fail "
                'reason="join limit exceeded" evidence=r-contradicted/worker.patch',
                result_line,
                "",
            ]
        ),
        encoding="utf-8",
    )

    answer = propose(BENCH_ROOT / "run-2026-11-01", run_log)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
