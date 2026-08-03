"""Persist semantic weather-risk delivery state per field.

Revision ID: 20260803_0008
Revises: 20260803_0007
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0008"
down_revision: str | None = "20260803_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_delivery_states",
        sa.Column("field_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("delivery_mode", sa.String(length=16), nullable=False),
        sa.Column(
            "state_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(), nullable=False),
        sa.Column("last_notified_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "delivery_mode IN ('immediate', 'digest', 'high_only')",
            name="ck_risk_delivery_states_mode",
        ),
        sa.ForeignKeyConstraint(
            ["field_id"],
            ["fields.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("field_id"),
    )
    op.create_index(
        "ix_risk_delivery_states_observed_at",
        "risk_delivery_states",
        ["last_observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_risk_delivery_states_observed_at",
        table_name="risk_delivery_states",
    )
    op.drop_table("risk_delivery_states")
