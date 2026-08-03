"""Add persistent crop-disease monitoring state.

Revision ID: 20260803_0009
Revises: 20260803_0008
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0009"
down_revision: str | None = "20260803_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPTY_STATE = (
    '{"active_periods":[],"inoculum_context":"unknown",'
    '"withdrawn_periods":[]}'
)


def upgrade() -> None:
    op.create_table(
        "biological_monitors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("crop_season_id", sa.Integer(), nullable=False),
        sa.Column("model_key", sa.String(length=80), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "inoculum_context",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "state_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "state_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'" + _EMPTY_STATE + "'"),
        ),
        sa.Column("last_checked_local_date", sa.Date(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "inoculum_context IN ("
            "'unknown', 'regional_alert_confirmed', "
            "'nearby_outbreak_confirmed', 'field_source_suspected', "
            "'field_symptoms_observed')",
            name="ck_biological_monitors_inoculum_context",
        ),
        sa.ForeignKeyConstraint(
            ["crop_season_id"],
            ["crop_seasons.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "crop_season_id",
            "model_key",
            name="uq_biological_monitors_season_model",
        ),
    )
    op.create_index(
        "ix_biological_monitors_enabled",
        "biological_monitors",
        ["enabled"],
        unique=False,
    )
    op.create_index(
        "ix_biological_monitors_observed_at",
        "biological_monitors",
        ["last_observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_biological_monitors_observed_at",
        table_name="biological_monitors",
    )
    op.drop_index(
        "ix_biological_monitors_enabled",
        table_name="biological_monitors",
    )
    op.drop_table("biological_monitors")
