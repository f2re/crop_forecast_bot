"""Add persistent crop-pest monitoring profiles.

Revision ID: 20260803_0007
Revises: 20260803_0006
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0007"
down_revision: str | None = "20260803_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A failed/non-transactional test migration can leave this new extension
    # table behind while the Alembic marker and its parent tables are reset.
    # Since revision 0007 is the table's first owner, rebuilding that orphan is
    # safer than failing the whole next upgrade. Normal production upgrades do
    # not enter this branch.
    if sa.inspect(op.get_bind()).has_table("pest_monitors"):
        op.drop_table("pest_monitors")

    op.create_table(
        "pest_monitors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("crop_season_id", sa.Integer(), nullable=False),
        sa.Column("pest_key", sa.String(length=64), nullable=False),
        sa.Column("biofix_date", sa.Date(), nullable=False),
        sa.Column("biofix_type", sa.String(length=32), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_checked_local_date", sa.Date(), nullable=True),
        sa.Column("last_notified_stage", sa.String(length=180), nullable=True),
        sa.Column("last_notified_advance", sa.String(length=180), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["crop_season_id"],
            ["crop_seasons.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "crop_season_id",
            "pest_key",
            name="uq_pest_monitors_crop_pest",
        ),
    )
    op.create_index(
        "ix_pest_monitors_crop_season_id",
        "pest_monitors",
        ["crop_season_id"],
        unique=False,
    )
    op.create_index(
        "ix_pest_monitors_enabled",
        "pest_monitors",
        ["enabled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pest_monitors_enabled", table_name="pest_monitors")
    op.drop_index("ix_pest_monitors_crop_season_id", table_name="pest_monitors")
    op.drop_table("pest_monitors")
