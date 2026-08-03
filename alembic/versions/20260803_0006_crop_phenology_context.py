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
    # Batch mode is required by SQLite tests because SQLite cannot add check
    # constraints with ALTER TABLE. PostgreSQL executes the same operations
    # directly while preserving one migration graph for both environments.
    with op.batch_alter_table("crop_seasons") as batch_op:
        batch_op.add_column(
            sa.Column(
                "date_basis",
                sa.String(length=24),
                nullable=False,
                server_default="season_start",
            )
        )
        batch_op.add_column(
            sa.Column(
                "production_system",
                sa.String(length=20),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column(
                "plant_type",
                sa.String(length=20),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column("cultivar_name", sa.String(length=120), nullable=True)
        )
        batch_op.add_column(
            sa.Column("maturity_group", sa.String(length=80), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "phase_confirmed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "phase_observation_note",
                sa.String(length=500),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_crop_seasons_date_basis",
            "date_basis IN ('sowing', 'emergence', 'transplanting', 'season_start')",
        )
        batch_op.create_check_constraint(
            "ck_crop_seasons_production_system",
            "production_system IN ('open_field', 'greenhouse', 'unknown')",
        )
        batch_op.create_check_constraint(
            "ck_crop_seasons_plant_type",
            "plant_type IN ('determinate', 'indeterminate', 'unknown')",
        )


def downgrade() -> None:
    with op.batch_alter_table("crop_seasons") as batch_op:
        batch_op.drop_constraint(
            "ck_crop_seasons_plant_type",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_crop_seasons_production_system",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_crop_seasons_date_basis",
            type_="check",
        )
        batch_op.drop_column("phase_observation_note")
        batch_op.drop_column("phase_confirmed_at")
        batch_op.drop_column("maturity_group")
        batch_op.drop_column("cultivar_name")
        batch_op.drop_column("plant_type")
        batch_op.drop_column("production_system")
        batch_op.drop_column("date_basis")
