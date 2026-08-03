"""Add explicit date meaning and phenology observation context.

Revision ID: 20260803_0006
Revises: 20260719_0005
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0006"
down_revision: str | None = "20260719_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crop_seasons",
        sa.Column(
            "date_basis",
            sa.String(length=24),
            nullable=False,
            server_default="season_start",
        ),
    )
    op.add_column(
        "crop_seasons",
        sa.Column(
            "production_system",
            sa.String(length=20),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "crop_seasons",
        sa.Column(
            "plant_type",
            sa.String(length=20),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "crop_seasons",
        sa.Column("cultivar_name", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "crop_seasons",
        sa.Column("maturity_group", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "crop_seasons",
        sa.Column("phase_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "crop_seasons",
        sa.Column("phase_observation_note", sa.String(length=500), nullable=True),
    )

    op.create_check_constraint(
        "ck_crop_seasons_date_basis",
        "crop_seasons",
        "date_basis IN ('sowing', 'emergence', 'transplanting', 'season_start')",
    )
    op.create_check_constraint(
        "ck_crop_seasons_production_system",
        "crop_seasons",
        "production_system IN ('open_field', 'greenhouse', 'unknown')",
    )
    op.create_check_constraint(
        "ck_crop_seasons_plant_type",
        "crop_seasons",
        "plant_type IN ('determinate', 'indeterminate', 'unknown')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_crop_seasons_plant_type",
        "crop_seasons",
        type_="check",
    )
    op.drop_constraint(
        "ck_crop_seasons_production_system",
        "crop_seasons",
        type_="check",
    )
    op.drop_constraint(
        "ck_crop_seasons_date_basis",
        "crop_seasons",
        type_="check",
    )
    op.drop_column("crop_seasons", "phase_observation_note")
    op.drop_column("crop_seasons", "phase_confirmed_at")
    op.drop_column("crop_seasons", "maturity_group")
    op.drop_column("crop_seasons", "cultivar_name")
    op.drop_column("crop_seasons", "plant_type")
    op.drop_column("crop_seasons", "production_system")
    op.drop_column("crop_seasons", "date_basis")
