from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
PROVIDER_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "provider-smoke.yml"


def test_ci_contains_selective_live_provider_gate() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "live-provider:" in workflow
    assert "Live provider contracts (relevant PRs)" in workflow
    assert "Detect provider-contract changes" in workflow
    assert "Operational Forecast/Historical contract" in workflow
    assert "Homogeneous ERA5-Land current/reference contract" in workflow
    assert "python -m src.ops.provider_smoke" in workflow
    assert "python -m src.ops.climate_smoke" in workflow
    assert "pr-live-provider-smoke-${{ github.run_id }}" in workflow
    assert "retention-days: 14" in workflow


def test_live_provider_gate_is_pull_request_only_and_diff_scoped() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    live_job = workflow.split("  live-provider:\n", maxsplit=1)[1]

    assert "if: github.event_name == 'pull_request'" in live_job
    assert 'git diff --name-only "origin/${{ github.base_ref }}...HEAD"' in live_job
    assert "steps.changes.outputs.run == 'true'" in live_job
    assert "requirements[^/]*\\.txt" in live_job
    assert "src/(agro/climate_reference|api/open_meteo|api/open_meteo_climate" in live_job
    assert "ops/provider_smoke|ops/climate_smoke" in live_job


def test_workflows_do_not_use_runner_context_before_runner_allocation() -> None:
    ci_workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    provider_workflow = PROVIDER_WORKFLOW.read_text(encoding="utf-8")

    assert "${{ runner.temp }}" not in ci_workflow
    assert "${{ runner.temp }}" not in provider_workflow
    assert (
        "OPEN_METEO_CACHE_PATH: ${{ github.workspace }}/.cache/openmeteo"
        in ci_workflow
    )
    assert (
        "OPEN_METEO_CACHE_PATH: ${{ github.workspace }}/.cache/openmeteo"
        in provider_workflow
    )


def test_scheduled_workflow_publishes_a_concrete_run_url() -> None:
    workflow = PROVIDER_WORKFLOW.read_text(encoding="utf-8")

    assert (
        "RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/"
        "${{ github.run_id }}"
        in workflow
    )
    assert "target_url: process.env.RUN_URL" in workflow
    assert "context.serverUrl" not in workflow
