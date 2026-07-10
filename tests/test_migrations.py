from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from src.database.schema import expected_schema_revision

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _upgrade(database_path: Path) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
    )
    command.upgrade(config, "head")


def _inspect(database_path: Path) -> sa.Inspector:
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    return sa.inspect(engine)


def test_initial_migration_creates_users_and_revision(tmp_path: Path) -> None:
    database_path = tmp_path / "fresh.sqlite"
    _upgrade(database_path)

    inspector = _inspect(database_path)
    assert {"users", "alembic_version"}.issubset(inspector.get_table_names())
    columns = {column["name"] for column in inspector.get_columns("users")}
    assert {
        "id",
        "telegram_id",
        "username",
        "first_name",
        "latitude",
        "longitude",
        "selected_crop",
        "daily_digest",
        "created_at",
        "updated_at",
    } == columns

    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        revision = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
    assert revision == expected_schema_revision() == "20260710_0001"


def test_initial_migration_adopts_existing_create_all_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite"
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    telegram_id BIGINT NOT NULL UNIQUE,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    latitude FLOAT,
                    longitude FLOAT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO users (telegram_id, username) VALUES (1001, 'farmer')"
            )
        )

    _upgrade(database_path)

    inspector = _inspect(database_path)
    columns = {column["name"] for column in inspector.get_columns("users")}
    assert "selected_crop" in columns
    assert "daily_digest" in columns

    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT telegram_id, selected_crop, daily_digest "
                "FROM users WHERE telegram_id = 1001"
            )
        ).one()
    assert row == (1001, "wheat", 0)
