from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _config(database_path: Path) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
    )
    return config


def _columns(database_path: Path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        return {
            column["name"]
            for column in sa.inspect(engine).get_columns("fields")
        }
    finally:
        engine.dispose()


def test_risk_delivery_migration_downgrade_and_reupgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "risk-delivery-migration.sqlite"
    config = _config(database_path)

    command.upgrade(config, "head")
    assert {
        "risk_delivery_mode",
        "quiet_hours_start",
        "quiet_hours_end",
    }.issubset(_columns(database_path))

    command.downgrade(config, "20260718_0004")
    assert {
        "risk_delivery_mode",
        "quiet_hours_start",
        "quiet_hours_end",
    }.isdisjoint(_columns(database_path))

    command.upgrade(config, "head")
    assert {
        "risk_delivery_mode",
        "quiet_hours_start",
        "quiet_hours_end",
    }.issubset(_columns(database_path))
