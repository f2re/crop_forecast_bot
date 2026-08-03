from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _workflow() -> str:
    return (
        PROJECT_ROOT / ".github/workflows/deploy-production.yml"
    ).read_text(encoding="utf-8")


def _documentation() -> str:
    return (
        PROJECT_ROOT / "docs/DEPLOYMENT_AND_NOTIFICATION_POLICY.md"
    ).read_text(encoding="utf-8")


def test_deploy_trigger_uses_repository_variable_before_runner_start() -> None:
    workflow = _workflow()
    documentation = _documentation()

    assert "vars.DEPLOY_TRIGGER_ENABLED == 'true'" in workflow
    assert "repository/organization" in workflow
    assert "переменной репозитория" in documentation
    assert "DEPLOY_TRIGGER_ENABLED" in documentation


def test_deploy_secrets_remain_protected_by_production_environment() -> None:
    workflow = _workflow()

    assert "environment: production" in workflow
    for secret_name in (
        "DEPLOY_HOST",
        "DEPLOY_PORT",
        "DEPLOY_USER",
        "DEPLOY_SSH_KEY",
        "DEPLOY_KNOWN_HOSTS",
    ):
        assert f"secrets.{secret_name}" in workflow


def test_deploy_trigger_supports_manual_end_to_end_verification() -> None:
    workflow = _workflow()
    documentation = _documentation()

    assert "workflow_dispatch:" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "gh workflow run deploy-production.yml" in documentation


def test_deploy_configuration_script_is_reproducible_and_secret_safe() -> None:
    script = (
        PROJECT_ROOT / "scripts/configure-github-deploy.sh"
    ).read_text(encoding="utf-8")
    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "gh auth status" not in script  # binary name is configurable
    assert '"${GH_BIN}" auth status' in script
    assert 'secret set DEPLOY_SSH_KEY' in script
    assert 'secret set DEPLOY_KNOWN_HOSTS' in script
    assert 'variable set DEPLOY_TRIGGER_ENABLED' in script
    assert 'workflow run deploy-production.yml' in script
    assert "stat -c '%a'" in script
    assert "stat -f '%Lp'" in script
    assert "scripts/configure-github-deploy.sh" in ci
