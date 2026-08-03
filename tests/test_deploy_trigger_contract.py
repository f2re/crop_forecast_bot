from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_deploy_trigger_uses_repository_variable_before_runner_start() -> None:
    workflow = (
        PROJECT_ROOT / ".github/workflows/deploy-production.yml"
    ).read_text(encoding="utf-8")
    documentation = (
        PROJECT_ROOT / "docs/DEPLOYMENT_AND_NOTIFICATION_POLICY.md"
    ).read_text(encoding="utf-8")

    assert "vars.DEPLOY_TRIGGER_ENABLED == 'true'" in workflow
    assert "repository/organization" in workflow
    assert "переменную репозитория" in documentation
    assert "Settings → Secrets and variables → Actions → Variables" in documentation
    assert "DEPLOY_TRIGGER_ENABLED=true" in documentation


def test_deploy_secrets_remain_protected_by_production_environment() -> None:
    workflow = (
        PROJECT_ROOT / ".github/workflows/deploy-production.yml"
    ).read_text(encoding="utf-8")

    assert "environment: production" in workflow
    for secret_name in (
        "DEPLOY_HOST",
        "DEPLOY_PORT",
        "DEPLOY_USER",
        "DEPLOY_SSH_KEY",
        "DEPLOY_KNOWN_HOSTS",
    ):
        assert f"secrets.{secret_name}" in workflow
