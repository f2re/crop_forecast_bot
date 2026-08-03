from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from src.database.schema import expected_schema_revision

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _upgrade(database_path: Path, revision: str = "head") -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
    )
    command.upgrade(config, revision)


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
        "risk_forecast_runs",
        "risk_forecast_signals",
        "risk_delivery_states",
        "pest_monitors",
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
        "risk_delivery_mode",
        "quiet_hours_start",
        "quiet_hours_end",
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
        "date_basis",
        "production_system",
        "plant_type",
        "cultivar_name",
        "maturity_group",
        "phenological_phase",
        "phase_source",
        "phase_confidence",
        "phase_confirmed_at",
        "phase_observation_note",
        "is_active",
        "created_at",
        "updated_at",
    } == season_columns

    run_columns = {
        column["name"] for column in inspector.get_columns("risk_forecast_runs")
    }
    assert {
        "id",
        "field_id",
        "source",
        "model",
        "retrieved_at",
        "analysis_date",
        "timezone",
        "member_count",
        "forecast_days",
        "valid_days",
        "incomplete_days",
        "status",
        "created_at",
    } == run_columns

    signal_columns = {
        column["name"]
        for column in inspector.get_columns("risk_forecast_signals")
    }
    assert {
        "id",
        "run_id",
        "risk_type",
        "event_date",
        "lead_days",
        "level",
        "members_exceeding",
        "valid_members",
        "member_fraction",
        "severe_member_fraction",
        "threshold",
        "severe_threshold",
        "unit",
        "p10",
        "median",
        "p90",
        "delivery_state",
        "notified_at",
        "created_at",
    } == signal_columns

    delivery_columns = {
        column["name"]
        for column in inspector.get_columns("risk_delivery_states")
    }
    assert {
        "field_id",
        "model",
        "delivery_mode",
        "state_version",
        "state_json",
        "last_observed_at",
        "last_notified_at",
    } == delivery_columns

    pest_columns = {
        column["name"] for column in inspector.get_columns("pest_monitors")
    }
    assert {
        "id",
        "crop_season_id",
        "pest_key",
        "biofix_date",
        "biofix_type",
        "model_version",
        "enabled",
        "last_checked_local_date",
        "last_notified_stage",
        "last_notified_advance",
        "last_notified_at",
        "created_at",
        "updated_at",
    } == pest_columns

    field_indexes = {
        index["name"]: index for index in inspector.get_indexes("fields")
    }
    assert field_indexes["uq_fields_one_active_per_user"]["unique"] == 1
    field_checks = {
        constraint["name"] for constraint in inspector.get_check_constraints("fields")
    }
    assert "ck_fields_risk_delivery_mode" in field_checks
    assert "ck_fields_quiet_hours" in field_checks

    season_indexes = {
        index["name"]: index for index in inspector.get_indexes("crop_seasons")
    }
    assert season_indexes["uq_crop_seasons_one_active_per_field"]["unique"] == 1
    season_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("crop_seasons")
    }
    assert "ck_crop_seasons_date_basis" in season_checks
    assert "ck_crop_seasons_production_system" in season_checks
    assert "ck_crop_seasons_plant_type" in season_checks

    run_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("risk_forecast_runs")
    }
    assert "uq_risk_forecast_runs_identity" in run_unique_constraints
    signal_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("risk_forecast_signals")
    }
    assert "uq_risk_forecast_signals_event" in signal_unique_constraints
    delivery_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("risk_delivery_states")
    }
    assert "ck_risk_delivery_states_mode" in delivery_checks
    delivery_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("risk_delivery_states")
    }
    assert "ix_risk_delivery_states_observed_at" in delivery_indexes
    pest_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("pest_monitors")
    }
    assert "uq_pest_monitors_crop_pest" in pest_unique_constraints
    pest_indexes = {
        index["name"]: index for index in inspector.get_indexes("pest_monitors")
    }
    assert "ix_pest_monitors_crop_season_id" in pest_indexes
    assert "ix_pest_monitors_enabled" in pest_indexes

    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        revision = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
    assert revision == expected_schema_revision() == "20260803_0008"


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
                "frost_alerts_enabled, risk_delivery_mode, quiet_hours_start, "
                "quiet_hours_end, is_active FROM fields"
            )
        ).one()
        season_row = connection.execute(
            sa.text(
                "SELECT field_id, crop_key, season_start_date, is_active, "
                "date_basis, production_system, plant_type, phase_confirmed_at "
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
    assert field_row[9] == "immediate"
    assert field_row[10] is None
    assert field_row[11] is None
    assert bool(field_row[12]) is True
    assert season_row[0] is not None
    assert season_row[1] == "sunflower"
    assert season_row[2] is None
    assert bool(season_row[3]) is True
    assert season_row[4] == "season_start"
    assert season_row[5] == "unknown"
    assert season_row[6] == "unknown"
    assert season_row[7] is None
    assert revision == "20260803_0008"


def test_field_metadata_provenance_is_preserved_when_upgrading_from_0002(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "metadata.sqlite"
    _upgrade(database_path, "20260710_0002")
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")

    with engine.begin() as connection:
        user_id = connection.execute(
            sa.text(
                "INSERT INTO users (telegram_id, selected_crop, daily_digest) "
                "VALUES (3003, 'wheat', 1) RETURNING id"
            )
        ).scalar_one()
        connection.execute(
            sa.text(
                "INSERT INTO fields "
                "(user_id, name, latitude, longitude, timezone, elevation_m, is_active) "
                "VALUES (:user_id, 'Западное', 51.0, 40.0, "
                "'Europe/Moscow', 172.0, 1)"
            ),
            {"user_id": user_id},
        )

    _upgrade(database_path)

    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT timezone_source, elevation_source, "
                "daily_digest_enabled, frost_alerts_enabled, risk_delivery_mode, "
                "quiet_hours_start, quiet_hours_end "
                "FROM fields WHERE user_id = :user_id"
            ),
            {"user_id": user_id},
        ).one()

    # This fixture deliberately inserts only a field at revision 0002. Later
    # migrations preserve that field's metadata and do not invent a crop profile.
    expected_source = "legacy/provider metadata; exact source not recorded"
    assert row[0] == expected_source
    assert row[1] == expected_source
    assert bool(row[2]) is True
    assert bool(row[3]) is True
    assert row[4] == "immediate"
    assert row[5] is None
    assert row[6] is None
