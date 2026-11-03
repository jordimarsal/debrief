"""S3 routing.propose — a BW_ROLE_* diff as text from both ports (R1, R2, R5–R7)."""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from debrief.adapters.buildwright_log import BuildwrightLog
from debrief.adapters.ggufbench_store import RESULTS_FILE, GgufbenchStore
from debrief.domain import FAIL, PASS, Finding, TaskSignature
from debrief.errors import (
    BENCH_SOURCE_MISSING,
    INCOMPARABLE_ROWS,
    PATH_OUTSIDE_ROOT,
    RUN_SOURCE_MISSING,
    SOURCE_UNPARSEABLE,
    DebriefError,
)
from debrief.mcp_server import (
    BENCH_ROOT_ENV,
    DEFAULT_BENCH_ROOT,
    DEFAULT_RUN_ROOT,
    RUN_ROOT_ENV,
    routing_propose,
)
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
    # R6: the registry is named only inside the fixed `not applied:` prose —
    # no line of the answer proposes a models.yaml change.
    registry_mentions = [line for line in answer.splitlines() if "models.yaml" in line]
    assert registry_mentions
    assert all(line.startswith("not applied:") for line in registry_mentions)


def test_propose_role_refuses_rows_spanning_two_baselines() -> None:
    answer = propose(BENCH_ROOT, SQL_JOIN_LOG)

    assert isinstance(answer, DebriefError)
    assert answer.code == INCOMPARABLE_ROWS
    assert "b4937-graded-baseline" in answer.detail
    assert "b4945-graded-baseline" in answer.detail


def _spanning_bench_tree(tmp_path: Path) -> Path:
    """A bench root whose sql-join cohort spans two signatures: the failure's own
    signature holds only the failing model, and the top-scoring candidate sits in
    the other one — so ranking or narrowing would both be ADR-0004 violations."""
    own = {
        "engine_build": "llama.cpp-b4937",
        "baseline": "b4937-graded-baseline",
        "rows": [
            {
                "model": QWEN,
                "task": "sql-join",
                "outcome": "fail",
                "score": 0.52,
                "reason": "join limit exceeded",
                "artifact": "run-a/sql-join/qwen.transcript",
                "graded": {"joins": 40, "limits": 10, "syntax": 20},
            }
        ],
    }
    other = {
        "engine_build": "llama.cpp-b4937",
        "baseline": "b4945-graded-baseline",
        "rows": [
            {
                "model": LLAMA,
                "task": "sql-join",
                "outcome": "pass",
                "score": 0.99,
                "reason": "all dimensions above the pass mark",
                "artifact": "run-b/sql-join/llama.transcript",
                "graded": {"joins": 45, "limits": 10, "syntax": 20},
            }
        ],
    }
    root = tmp_path / "ggufbench"
    for name, document in (("run-a", own), ("run-b", other)):
        run_dir = root / name
        run_dir.mkdir(parents=True)
        (run_dir / RESULTS_FILE).write_text(json.dumps(document), encoding="utf-8")
    return root


def test_propose_refuses_a_spanning_cohort_instead_of_ranking_the_other_signature(
    tmp_path: Path,
) -> None:
    """Ranking the 0.99 candidate against the failure would ignore the shared
    signature rule; silently narrowing the cohort to the failure's own signature
    would drop the only other measured model. The refusal names every signature
    key and carries no winner at all (R7)."""
    answer = propose(_spanning_bench_tree(tmp_path), SQL_JOIN_LOG)

    assert isinstance(answer, DebriefError)
    assert answer.code == INCOMPARABLE_ROWS
    assert "b4937-graded-baseline" in answer.detail
    assert "b4945-graded-baseline" in answer.detail
    assert LLAMA not in str(answer)
    assert "0.99" not in str(answer)


def test_routing_propose_tool_refuses_a_spanning_cohort_with_no_proposal_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(BENCH_ROOT_ENV, str(_spanning_bench_tree(tmp_path)))
    monkeypatch.setenv(RUN_ROOT_ENV, str(RUN_LOGS))

    response = routing_propose(".", "run-2026-11-02T09-14Z.log")

    assert response.proposal == ""
    assert response.error is not None
    assert response.error.code == INCOMPARABLE_ROWS
    assert "b4937-graded-baseline" in response.error.detail
    assert "b4945-graded-baseline" in response.error.detail


def test_propose_refuses_a_cohort_where_no_row_carries_a_signature() -> None:
    """The second `incomparable_rows` arm: rows that carry no signature at all.
    Every row a real artifact maps carries one, so this arm is reachable only
    through the domain values the Finding type allows (the port contract leaves
    `signature` optional); the refusal names the rows instead of ranking them."""
    cohort = [
        Finding(
            model=LLAMA,
            task="sql-join",
            outcome=PASS,
            reason="measured outside ggufbench",
            evidence="external/sql-join/llama.transcript",
        ),
        Finding(
            model="gemma-2-9b-it-q4_k_m",
            task="sql-join",
            outcome=PASS,
            reason="measured outside ggufbench",
            evidence="external/sql-join/gemma.transcript",
        ),
    ]

    answer = propose_prebuilt(cohort, [_run_finding("worker", QWEN)])

    assert isinstance(answer, DebriefError)
    assert answer.code == INCOMPARABLE_ROWS
    assert LLAMA in answer.detail
    assert "gemma-2-9b-it-q4_k_m" in answer.detail
    assert "sql-join" in answer.detail
    assert not isinstance(answer, str)


def test_propose_role_reports_when_no_step_failed() -> None:
    answer = propose(BENCH_ROOT / "run-2026-11-01", PASSING_LOG)

    assert answer == "no proposal: every logged step passed"


@dataclass(frozen=True)
class _StaticRows:
    """A port answering prebuilt findings, for the rendering states no fixture can
    express: the buildwright step grammar always records `role=`, so a role-less
    step never parses out of a real log and the keep-the-role branch for one is
    reachable only through the domain values the Finding type already carries."""

    rows: list[Finding]

    def findings(self) -> list[Finding] | DebriefError:
        return list(self.rows)


def _bench_row(
    model: str, task: str = "sql-join", outcome: str = PASS, measure: float = 0.9
) -> Finding:
    return Finding(
        model=model,
        task=task,
        outcome=outcome,
        reason="all graded dimensions above the pass mark",
        evidence=f"run-2026-11-01/{task}/bench.transcript",
        signature=TaskSignature.of(
            {"joins": 40, "limits": 10, "syntax": 20}, "b4937-graded-baseline", "llama.cpp-b4937"
        ),
        measure=measure,
    )


def _run_finding(
    role: str | None,
    model: str,
    task: str = "sql-join",
    outcome: str = FAIL,
    reason: str = "join limit exceeded",
    evidence: str = "r-2026-11-02T09-14Z/worker.patch",
) -> Finding:
    return Finding(
        model=model, task=task, outcome=outcome, reason=reason, evidence=evidence, role=role
    )


def propose_prebuilt(bench_rows: list[Finding], run_rows: list[Finding]) -> str | DebriefError:
    """The same composition the tool serves, over prebuilt port answers."""
    return ProposeRole(QueryBench(_StaticRows(bench_rows)), InspectRun(_StaticRows(run_rows))).run()


@pytest.mark.parametrize(
    ("bench_rows", "run_rows", "note"),
    [
        pytest.param(
            [],
            [_run_finding("worker", QWEN)],
            f"note: ggufbench never measured sql-join, keeping BW_ROLE_WORKER={QWEN}",
            id="unmeasured_task",
        ),
        pytest.param(
            [_bench_row(QWEN, outcome=FAIL), _bench_row(QWEN, outcome=PASS)],
            [_run_finding("worker", QWEN)],
            f"note: no passing model for sql-join in the bench cohort, keeping"
            f" BW_ROLE_WORKER={QWEN}",
            id="no_passing_candidate",
        ),
        pytest.param(
            [_bench_row(LLAMA)],
            [_run_finding(None, QWEN)],
            "note: step on sql-join recorded no role, nothing to propose"
            " (r-2026-11-02T09-14Z/worker.patch)",
            id="roleless_step",
        ),
    ],
)
def test_propose_renders_a_keep_the_role_note_and_no_diff_for_every_keep_case(
    bench_rows: list[Finding], run_rows: list[Finding], note: str
) -> None:
    answer = propose_prebuilt(bench_rows, run_rows)

    assert isinstance(answer, str)
    assert note in answer
    assert not any(line[:2] in {"- ", "+ "} for line in answer.splitlines())
    assert "models.yaml" not in answer


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
        pytest.param(
            BROKEN_ROOT / "nonfinite-score-nan",
            SQL_JOIN_LOG,
            SOURCE_UNPARSEABLE,
            id="bench_refuses_a_nonfinite_score",
        ),
        pytest.param(
            BENCH_ROOT / "run-2026-11-01",
            RUN_LOGS / "run-truncated.log",
            SOURCE_UNPARSEABLE,
            id="run_refuses_a_truncated_step",
        ),
    ],
)
def test_propose_role_propagates_structured_errors_from_both_ports(
    bench_root: Path, run_log: Path, code: str
) -> None:
    answer = propose(bench_root, run_log)

    assert isinstance(answer, DebriefError)
    assert answer.code == code
    # Either port's structured error is the whole answer — never proposal text
    # with an error buried in it (R1).
    assert not isinstance(answer, str)
    assert answer.message
    assert answer.detail


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


@pytest.mark.parametrize(
    ("field", "sep", "forged_line"),
    [
        pytest.param(
            "model", "\n", "+ BW_ROLE_WORKER=evil-model", id="newline_forge_through_the_tool"
        ),
        pytest.param(
            "reason",
            " ",
            "+ models.yaml: rewrite-every-role",
            id="unicode_separator_registry_forge_through_the_tool",
        ),
    ],
)
def test_routing_propose_answers_a_poisoned_bench_cohort_with_a_structured_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str, sep: str, forged_line: str
) -> None:
    """End-to-end through the tool boundary: a poisoned cohort refuses as a
    structured error and the response carries no proposal text at all, so a
    newline- or Unicode-separator-forged `- `/`+ ` line — including a models.yaml
    forge — cannot ride into the caller's output (R6)."""
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
    monkeypatch.setenv(BENCH_ROOT_ENV, str(poisoned))

    response = routing_propose(".", "run-2026-11-02T09-14Z.log")

    assert response.proposal == ""
    assert response.error is not None
    assert response.error.code == SOURCE_UNPARSEABLE
    assert "+ BW_ROLE_WORKER=evil-model" not in response.proposal
    assert "models.yaml" not in response.proposal


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


def test_routing_propose_root_contract_is_stable() -> None:
    """The agent-facing path contract: both tool arguments resolve inside their
    own evidence root, whose names and defaults are the documented surface."""
    assert BENCH_ROOT_ENV == "DEBRIEF_BENCH_ROOT"
    assert DEFAULT_BENCH_ROOT == "artifacts/ggufbench"
    assert RUN_ROOT_ENV == "DEBRIEF_RUN_ROOT"
    assert DEFAULT_RUN_ROOT == "artifacts/buildwright"


@pytest.mark.parametrize(
    ("bench_path", "run_path", "detail_names"),
    [
        pytest.param(
            "../pyproject.toml",
            "run-2026-11-02T09-14Z.log",
            "resolves outside",
            id="bench_path_traversal_escape",
        ),
        pytest.param(
            "run-2026-11-01",
            "../pyproject.toml",
            "resolves outside",
            id="run_path_traversal_escape",
        ),
        pytest.param(
            "../buildwright/run-2026-11-02T09-14Z.log",
            "run-2026-11-02T09-14Z.log",
            "resolves outside",
            id="bench_path_names_a_run_log_outside_the_bench_root",
        ),
        pytest.param(
            "run-2026-11-01",
            "../ggufbench/run-2026-11-01/results.json",
            "resolves outside",
            id="run_path_names_a_bench_artifact_outside_the_run_root",
        ),
    ],
)
def test_routing_propose_tool_refuses_paths_outside_the_roots(
    proposal_env: None, bench_path: str, run_path: str, detail_names: str
) -> None:
    """Traversal in either argument refuses as `path_outside_root` before either
    port is read — including the cross-port rows: a bench path pointing at a run
    log and a run path pointing at a bench artifact never resolve (ADR-0002 at
    the path layer)."""
    response = routing_propose(bench_path, run_path)

    assert response.proposal == ""
    assert response.error is not None
    assert response.error.code == PATH_OUTSIDE_ROOT
    assert response.error.message
    assert detail_names in response.error.detail
    assert bench_path in response.error.detail or run_path in response.error.detail


SLICE_FIXTURE_ROOTS = (BENCH_ROOT, BROKEN_ROOT, RUN_LOGS)


def _slice_fixture_fingerprint() -> dict[str, tuple[int, int, str]]:
    return {
        str(path): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for root in SLICE_FIXTURE_ROOTS
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_serving_routing_propose_leaves_the_slice_fixtures_byte_identical(
    proposal_env: None,
) -> None:
    """R2: every debrief answer is printable text, so serving the tool — proposal,
    all-passed text, and refusals on both ports — may not touch a byte or a
    timestamp of the evidence it read."""
    before = _slice_fixture_fingerprint()
    assert len(before) >= 20

    proposal = routing_propose("run-2026-11-01", "run-2026-11-02T09-14Z.log")
    spanning = routing_propose(".", "run-2026-11-02T09-14Z.log")
    all_passed = routing_propose("run-2026-11-01", "run-2026-11-03T10-00Z.log")
    missing_bench = routing_propose("does-not-exist", "run-2026-11-02T09-14Z.log")
    missing_run = routing_propose("run-2026-11-01", "does-not-exist.log")
    poisoned = propose(BROKEN_ROOT / "nonfinite-score-nan", SQL_JOIN_LOG)

    assert proposal.error is None
    assert "+ BW_ROLE_WORKER=" in proposal.proposal
    assert spanning.error is not None and spanning.error.code == INCOMPARABLE_ROWS
    assert all_passed.proposal == "no proposal: every logged step passed"
    assert missing_bench.error is not None and missing_bench.error.code == BENCH_SOURCE_MISSING
    assert missing_run.error is not None and missing_run.error.code == RUN_SOURCE_MISSING
    assert isinstance(poisoned, DebriefError)
    assert poisoned.code == SOURCE_UNPARSEABLE
    assert _slice_fixture_fingerprint() == before


READ_PATH_MODULES = (
    "adapters/ggufbench_store.py",
    "adapters/buildwright_log.py",
    "use_cases.py",
    "mcp_server.py",
)
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


def _opens_for_writing(call: ast.Call, method_form: bool) -> bool:
    """Whether an open() call carries a write mode. A `mode=` keyword wins over
    either positional slot; the bound method form (`path.open('w')`) keeps the
    mode in slot 0, the builtin (`open(path, 'w')`) in slot 1. A non-literal
    mode cannot be proven read-only at this gate, so it counts as an offender
    rather than passing silently."""
    mode: ast.AST | None = None
    for keyword in call.keywords:
        if keyword.arg == "mode":
            mode = keyword.value
    if mode is None:
        if method_form and len(call.args) == 1:
            mode = call.args[0]
        elif len(call.args) > 1:
            mode = call.args[1]
    if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str):
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
            if name == "open" and _opens_for_writing(node, isinstance(node.func, ast.Attribute)):
                offenses.append(f"{relative} opens a file in a write mode")
            elif name in MUTATING_CALLS:
                offenses.append(f"{relative} calls {name}()")
    return offenses


@pytest.mark.parametrize(
    ("snippet", "offense_part"),
    [
        pytest.param("path.open('w')", "opens a file in a write mode", id="write_mode"),
        pytest.param("open(path, 'wb')", "opens a file in a write mode", id="write_mode_builtin"),
        pytest.param(
            "path.open(mode='a')", "opens a file in a write mode", id="append_mode_keyword"
        ),
        pytest.param(
            "path.open(mode)", "opens a file in a write mode", id="non_literal_mode_is_an_offender"
        ),
        pytest.param("path.write_text('x')", "calls write_text()", id="write_text"),
        pytest.param("path.write_bytes(b'x')", "calls write_bytes()", id="write_bytes"),
        pytest.param("path.unlink()", "calls unlink()", id="unlink"),
        pytest.param("path.mkdir()", "calls mkdir()", id="mkdir"),
        pytest.param("path.replace(other)", "calls replace()", id="replace"),
        pytest.param("import shutil", "imports a filesystem-write module", id="shutil_import"),
    ],
)
def test_the_slice_write_gate_flags_every_write_shape(snippet: str, offense_part: str) -> None:
    offenses = _write_offenses("synthetic.py", ast.parse(snippet))

    assert len(offenses) == 1
    assert offense_part in offenses[0]


@pytest.mark.parametrize(
    "snippet",
    [
        pytest.param("path.open()", id="default_read_mode"),
        pytest.param("path.open('rb')", id="binary_read_mode"),
        pytest.param("path.read_text()", id="read_text"),
        pytest.param("path.read_bytes()", id="read_bytes"),
        pytest.param("path.stat()", id="stat_probe"),
    ],
)
def test_the_slice_write_gate_passes_every_read_shape(snippet: str) -> None:
    assert _write_offenses("synthetic.py", ast.parse(snippet)) == []


def test_routing_propose_read_path_has_no_write_mode_open_or_mutation() -> None:
    """R2 statically: the whole slice read path — both adapters, the composing
    use case, and the MCP transport — opens nothing for writing and calls no
    mutating filesystem API."""
    package = Path(__file__).parents[1] / "src" / "debrief"
    offenses = [
        offense
        for relative in READ_PATH_MODULES
        for offense in _write_offenses(
            relative, ast.parse((package / relative).read_text(encoding="utf-8"))
        )
    ]

    assert offenses == []
