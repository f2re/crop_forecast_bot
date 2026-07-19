"""Add per-field risk delivery mode and quiet hours.

Revision ID: 20260719_0005
Revises: 20260718_0004
Create Date: 2026-07-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "20260719_0005"
down_revision: str | None = "20260718_0004"
branch_labels: str | None = None
depends_on: str | None = None


_MODE_CHECK = "risk_delivery_mode IN ('immediate', 'digest', 'high_only')"
_QUIET_HOURS_CHECK = (
    "(quiet_hours_start IS NULL AND quiet_hours_end IS NULL) OR "
    "(quiet_hours_start BETWEEN 0 AND 23 AND "
    "quiet_hours_end BETWEEN 0 AND 23 AND "
    "quiet_hours_start <> quiet_hours_end)"
)


def upgrade() -> None:
    with op.batch_alter_table("fields") as batch:
        batch.add_column(
            sa.Column(
                "risk_delivery_mode",
                sa.String(length=16),
                nullable=False,
                server_default="immediate",
            )
        )
        batch.add_column(sa.Column("quiet_hours_start", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("quiet_hours_end", sa.Integer(), nullable=True))
        batch.create_check_constraint("ck_fields_risk_delivery_mode", _MODE_CHECK)
        batch.create_check_constraint("ck_fields_quiet_hours", _QUIET_HOURS_CHECK)


def downgrade() -> None:
    with op.batch_alter_table("fields") as batch:
        batch.drop_constraint("ck_fields_quiet_hours", type_="check")
        batch.drop_constraint("ck_fields_risk_delivery_mode", type_="check")
        batch.drop_column("quiet_hours_end")
        batch.drop_column("quiet_hours_start")
        batch.drop_column("risk_delivery_mode")
