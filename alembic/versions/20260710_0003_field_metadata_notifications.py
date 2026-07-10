"""Add field metadata provenance and notification preferences.

Revision ID: 20260710_0003
Revises: 20260710_0002
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "20260710_0003"
down_revision: str | None = "20260710_0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "fields",
        sa.Column("timezone_source", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "fields",
        sa.Column("elevation_source", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "fields",
        sa.Column(
            "daily_digest_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "fields",
        sa.Column(
            "frost_alerts_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("daily_digest", sa.Integer()),
    )
    fields = sa.table(
        "fields",
        sa.column("user_id", sa.Integer()),
        sa.column("timezone_source", sa.String()),
        sa.column("daily_digest_enabled", sa.Boolean()),
    )
    bind = op.get_bind()
    user_digest = (
        sa.select(users.c.daily_digest)
        .where(users.c.id == fields.c.user_id)
        .scalar_subquery()
    )
    bind.execute(
        sa.update(fields).values(
            timezone_source="legacy/default UTC",
            daily_digest_enabled=sa.case((user_digest == 1, True), else_=False),
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("fields") as batch:
        batch.drop_column("frost_alerts_enabled")
        batch.drop_column("daily_digest_enabled")
        batch.drop_column("elevation_source")
        batch.drop_column("timezone_source")
