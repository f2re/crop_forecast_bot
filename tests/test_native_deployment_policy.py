from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_only_native_deployment_artifacts_are_present() -> None:
    forbidden = (
        "Dockerfile",
        "docker-compose.yml",
        ".env.docker.example",
    )
    for relative_path in forbidden:
        assert not (ROOT / relative_path).exists(), relative_path


def test_native_operations_commands_are_versioned() -> None:
    required = (
        "scripts/deploy.sh",
        "scripts/update.sh",
        "scripts/rollback.sh",
        "scripts/status.sh",
        "scripts/help.sh",
        "alembic.ini",
        "alembic/versions/20260710_0001_initial_schema.py",
        "alembic/versions/20260710_0002_field_season_profile.py",
        "alembic/versions/20260710_0003_field_metadata_notifications.py",
        "deploy/systemd/crop-forecast-bot.service",
        "deploy/systemd/crop-forecast-bot-update.service",
        "deploy/systemd/crop-forecast-bot-update.timer",
    )
    for relative_path in required:
        assert (ROOT / relative_path).is_file(), relative_path


def test_systemd_service_uses_readiness_and_watchdog() -> None:
    unit = (ROOT / "deploy/systemd/crop-forecast-bot.service").read_text(
        encoding="utf-8"
    )
    assert "Type=notify" in unit
    assert "WatchdogSec=" in unit
    assert "ExecStart=@CURRENT_LINK@/.venv/bin/python -m src.bot.main" in unit


def test_production_startup_requires_alembic_schema() -> None:
    main = (ROOT / "src/bot/main.py").read_text(encoding="utf-8")
    database = (ROOT / "src/database/__init__.py").read_text(encoding="utf-8")
    common = (ROOT / "scripts/common.sh").read_text(encoding="utf-8")
    deploy = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")
    update = (ROOT / "scripts/update.sh").read_text(encoding="utf-8")

    assert "require_current_schema" in main
    assert "create_all" not in database
    assert "run_migrations()" in common
    assert 'run_migrations "${NEW_RELEASE}"' in deploy
    assert 'run_migrations "${NEW_RELEASE}"' in update


def test_field_season_and_multi_field_flows_are_reachable() -> None:
    models = (ROOT / "src/database/models.py").read_text(encoding="utf-8")
    handlers = (ROOT / "src/bot/handlers/core.py").read_text(encoding="utf-8")
    repository = (ROOT / "src/database/crud.py").read_text(encoding="utf-8")
    report = (ROOT / "src/application/agro_report.py").read_text(encoding="utf-8")

    assert "class Field(" in models
    assert "class CropSeason(" in models
    assert "daily_digest_enabled" in models
    assert "frost_alerts_enabled" in models
    assert 'F.data == "season"' in handlers
    assert 'F.data == "fields"' in handlers
    assert "field_activate:" in handlers
    assert "async def create_field(" in repository
    assert "async def activate_field(" in repository
    assert "season_start_date=context.season_start_date" in handlers
    assert "season_start_date: date | None" in report
