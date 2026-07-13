from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_contains_selective_live_provider_gate() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "live-provider:" in workflow
    assert "Live provider contracts (relevant PRs)" in workflow
    assert "Detect provider-contract changes" in workflow
    assert "src/ops/provider_smoke.py" in workflow
    assert "src/ops/climate_smoke.py" in workflow
    assert "Operational Forecast/Historical contract" in workflow
    assert "Homogeneous ERA5-Land current/reference contract" in workflow
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
