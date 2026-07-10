"""Create or adopt the initial users schema.

Revision ID: 20260710_0001
Revises:
Create Date: 2026-07-10

The migration deliberately adopts databases previously bootstrapped through
SQLAlchemy ``create_all()``. Missing non-key columns are added, while an
incompatible table without the required identity columns is rejected.
"""
from __future__ import annotations

from collections.abc import Callable

from alembic import op
import sqlalchemy as sa

revision: str = "20260710_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def _columns(bind) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns("users")}


def _add_column_if_missing(
    bind,
    existing: set[str],
    name: str,
    factory: Callable[[], sa.Column],
) -> None:
    if name in existing:
        return
    op.add_column("users", factory())
    existing.add(name)


def _telegram_id_is_unique(bind) -> bool:
    inspector = sa.inspect(bind)
    for index in inspector.get_indexes("users"):
        if index.get("unique") and index.get("column_names") == ["telegram_id"]:
            return True
    for constraint in inspector.get_unique_constraints("users"):
        if constraint.get("column_names") == ["telegram_id"]:
            return True
    return False


def _create_users_table() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "selected_crop",
            sa.String(length=50),
            nullable=True,
            server_default="wheat",
        ),
        sa.Column(
            "daily_digest",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
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
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)


def _adopt_existing_users_table(bind) -> None:
    existing = _columns(bind)
    required_identity = {"id", "telegram_id"}
    missing_identity = required_identity - existing
    if missing_identity:
        missing = ", ".join(sorted(missing_identity))
        raise RuntimeError(
            "Existing users table is incompatible with the baseline migration; "
            f"missing required columns: {missing}"
        )

    _add_column_if_missing(
        bind,
        existing,
        "username",
        lambda: sa.Column("username", sa.String(length=255), nullable=True),
    )
    _add_column_if_missing(
        bind,
        existing,
        "first_name",
        lambda: sa.Column("first_name", sa.String(length=255), nullable=True),
    )
    _add_column_if_missing(
        bind,
        existing,
        "latitude",
        lambda: sa.Column("latitude", sa.Float(), nullable=True),
    )
    _add_column_if_missing(
        bind,
        existing,
        "longitude",
        lambda: sa.Column("longitude", sa.Float(), nullable=True),
    )
    _add_column_if_missing(
        bind,
        existing,
        "selected_crop",
        lambda: sa.Column(
            "selected_crop",
            sa.String(length=50),
            nullable=True,
            server_default="wheat",
        ),
    )
    _add_column_if_missing(
        bind,
        existing,
        "daily_digest",
        lambda: sa.Column(
            "daily_digest",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    _add_column_if_missing(
        bind,
        existing,
        "created_at",
        lambda: sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    _add_column_if_missing(
        bind,
        existing,
        "updated_at",
        lambda: sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    if not _telegram_id_is_unique(bind):
        op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)


def upgrade() -> None:
    bind = op.get_bind()
    if "users" not in sa.inspect(bind).get_table_names():
        _create_users_table()
        return
    _adopt_existing_users_table(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The initial schema baseline is intentionally irreversible. "
        "Restore a PostgreSQL backup instead of downgrading it."
    )
