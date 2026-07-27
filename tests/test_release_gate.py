from __future__ import annotations

from urllib.error import URLError

import pytest

import src.ops.release_gate as release_gate
from src.ops.release_gate import GateDecision, evaluate_workflow_runs

_SHA = "a" * 40


def _run(*, status: str, conclusion: str | None, run_number: int = 1) -> dict:
    return {
        "id": run_number,
        "run_number": run_number,
        "head_sha": _SHA,
        "status": status,
        "conclusion": conclusion,
    }


def test_required_ci_must_exist_and_succeed() -> None:
    missing = evaluate_workflow_runs(
        {"workflow_runs": []},
        sha=_SHA,
        workflow_label="CI",
        required=True,
    )
    assert missing.state == "pending"
    assert missing.deployable is False

    success = evaluate_workflow_runs(
        {"workflow_runs": [_run(status="completed", conclusion="success")]},
        sha=_SHA,
        workflow_label="CI",
        required=True,
    )
    assert success.state == "ready"
    assert success.deployable is True


def test_optional_provider_workflow_may_be_absent() -> None:
    decision = evaluate_workflow_runs(
        {"workflow_runs": []},
        sha=_SHA,
        workflow_label="Live provider smoke",
        required=False,
    )
    assert decision.state == "absent"
    assert decision.deployable is True


def test_pending_or_failed_workflow_blocks_deployment() -> None:
    pending = evaluate_workflow_runs(
        {"workflow_runs": [_run(status="in_progress", conclusion=None)]},
        sha=_SHA,
        workflow_label="CI",
        required=True,
    )
    failed = evaluate_workflow_runs(
        {"workflow_runs": [_run(status="completed", conclusion="failure")]},
        sha=_SHA,
        workflow_label="CI",
        required=True,
    )
    assert pending.state == "pending"
    assert failed.state == "blocked"
    assert pending.deployable is False
    assert failed.deployable is False


def test_latest_exact_sha_run_wins() -> None:
    payload = {
        "workflow_runs": [
            _run(status="completed", conclusion="failure", run_number=1),
            {**_run(status="completed", conclusion="success", run_number=2)},
            {
                **_run(status="completed", conclusion="failure", run_number=99),
                "head_sha": "b" * 40,
            },
        ]
    }
    decision = evaluate_workflow_runs(
        payload,
        sha=_SHA,
        workflow_label="CI",
        required=True,
    )
    assert decision.state == "ready"


def test_release_gate_cli_is_fail_closed_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(**kwargs):
        raise URLError("offline")

    monkeypatch.setattr(release_gate, "check_release", fail)
    assert (
        release_gate.main(
            ["--repository", "f2re/crop_forecast_bot", "--sha", _SHA]
        )
        == 3
    )


def test_release_gate_cli_accepts_green_ci_and_optional_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        release_gate,
        "check_release",
        lambda **kwargs: (
            GateDecision("ready", "CI passed"),
            GateDecision("absent", "provider smoke not required"),
        ),
    )
    assert (
        release_gate.main(
            ["--repository", "f2re/crop_forecast_bot", "--sha", _SHA]
        )
        == 0
    )
