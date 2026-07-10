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


def test_migrations_create_user_field_season_and_revision(tmp_path: Path) -> None:
    database_path = tmp_path / "fresh.sqlite"
    _upgrade(database_path)

    inspector = _inspect(database_path)
    assert {
        "users",
        "fields",
        "crop_seasons",
        "alembic_version",
    }.issubset(inspector.get_table_names())

    user_columns = {column["name"] for column in inspector.get_columns("users")}
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
    } == user_columns

    field_columns = {column["name"] for column in inspector.get_columns("fields")}
    assert {
        "id",
        "user_id",
        "name",
        "latitude",
        "longitude",
        "timezone",
        "timezone_source",
        "elevation_m",
        "elevation_source",
        "daily_digest_enabled",
        "frost_alerts_enabled",
        "is_active",
        "created_at",
        "updated_at",
    } == field_columns

    season_columns = {
        column["name"] for column in inspector.get_columns("crop_seasons")
    }
    assert {
        "id",
        "field_id",
        "crop_key",
        "sowing_date",
        "season_start_date",
        "phenological_phase",
        "phase_source",
        "phase_confidence",
        "is_active",
        "created_at",
        "updated_at",
    } == season_columns

    field_indexes = {
        index["name"]: index for index in inspector.get_indexes("fields")
    }
    assert field_indexes["uq_fields_one_active_per_user"]["unique"] == 1
    season_indexes = {
        index["name"]: index for index in inspector.get_indexes("crop_seasons")
    }
    assert season_indexes["uq_crop_seasons_one_active_per_field"]["unique"] == 1

    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        revision = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
    assert revision == expected_schema_revision() == "20260710_0003"


def test_migrations_adopt_legacy_user_and_backfill_field_settings(
    tmp_path: Path,
) -> None:
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
                    selected_crop VARCHAR(50) DEFAULT 'wheat',
                    daily_digest INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO users "
                "(telegram_id, username, latitude, longitude, "
                "selected_crop, daily_digest) "
                "VALUES (1001, 'farmer', 55.75, 37.62, 'sunflower', 1)"
            )
        )

    _upgrade(database_path)

    with engine.connect() as connection:
        user_row = connection.execute(
            sa.text(
                "SELECT id, telegram_id, selected_crop, daily_digest "
                "FROM users WHERE telegram_id = 1001"
            )
        ).one()
        field_row = connection.execute(
            sa.text(
                "SELECT user_id, name, latitude, longitude, timezone, "
                "timezone_source, elevation_source, daily_digest_enabled, "
                "frost_alerts_enabled, is_active FROM fields"
            )
        ).one()
        season_row = connection.execute(
            sa.text(
                "SELECT field_id, crop_key, season_start_date, is_active "
                "FROM crop_seasons"
            )
        ).one()
        revision = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))

    assert user_row[1:] == (1001, "sunflower", 1)
    assert field_row[0] == user_row[0]
    assert field_row[1:5] == ("Основное поле", 55.75, 37.62, "UTC")
    assert field_row[5] == "legacy/default UTC"
    assert field_row[6] is None
    assert bool(field_row[7]) is True
    assert bool(field_row[8]) is True
    assert bool(field_row[9]) is True
    assert season_row[0] is not None
    assert season_row[1] == "sunflower"
    assert season_row[2] is None
    assert bool(season_row[3]) is True
    assert revision == "20260710_0003"
