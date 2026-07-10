"""Add field and crop-season profiles and backfill legacy user data.

Revision ID: 20260710_0002
Revises: 20260710_0001
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "20260710_0002"
down_revision: str | None = "20260710_0001"
branch_labels: str | None = None
depends_on: str | None = None


def _tables():
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("latitude", sa.Float()),
        sa.column("longitude", sa.Float()),
        sa.column("selected_crop", sa.String()),
    )
    fields = sa.table(
        "fields",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("latitude", sa.Float()),
        sa.column("longitude", sa.Float()),
        sa.column("timezone", sa.String()),
        sa.column("elevation_m", sa.Float()),
        sa.column("is_active", sa.Boolean()),
    )
    seasons = sa.table(
        "crop_seasons",
        sa.column("id", sa.Integer()),
        sa.column("field_id", sa.Integer()),
        sa.column("crop_key", sa.String()),
        sa.column("sowing_date", sa.Date()),
        sa.column("season_start_date", sa.Date()),
        sa.column("phenological_phase", sa.String()),
        sa.column("phase_source", sa.String()),
        sa.column("phase_confidence", sa.Float()),
        sa.column("is_active", sa.Boolean()),
    )
    return users, fields, seasons


def _backfill_from_users(bind) -> None:
    users, fields, seasons = _tables()
    rows = bind.execute(
        sa.select(
            users.c.id,
            users.c.latitude,
            users.c.longitude,
            users.c.selected_crop,
        ).where(
            users.c.latitude.is_not(None),
            users.c.longitude.is_not(None),
        )
    ).mappings()

    for row in rows:
        bind.execute(
            sa.insert(fields).values(
                user_id=row["id"],
                name="Основное поле",
                latitude=row["latitude"],
                longitude=row["longitude"],
                timezone="UTC",
                elevation_m=None,
                is_active=True,
            )
        )
        field_id = bind.scalar(
            sa.select(fields.c.id).where(
                fields.c.user_id == row["id"],
                fields.c.name == "Основное поле",
            )
        )
        bind.execute(
            sa.insert(seasons).values(
                field_id=field_id,
                crop_key=row["selected_crop"] or "wheat",
                sowing_date=None,
                season_start_date=None,
                phenological_phase=None,
                phase_source=None,
                phase_confidence=None,
                is_active=True,
            )
        )


def upgrade() -> None:
    op.create_table(
        "fields",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=120),
            nullable=False,
            server_default="Основное поле",
        ),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="UTC",
        ),
        sa.Column("elevation_m", sa.Float(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
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
        sa.UniqueConstraint("user_id", "name", name="uq_fields_user_name"),
    )
    op.create_index("ix_fields_user_id", "fields", ["user_id"], unique=False)
    op.create_index(
        "ix_fields_user_active",
        "fields",
        ["user_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "crop_seasons",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "field_id",
            sa.Integer(),
            sa.ForeignKey("fields.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "crop_key",
            sa.String(length=50),
            nullable=False,
            server_default="wheat",
        ),
        sa.Column("sowing_date", sa.Date(), nullable=True),
        sa.Column("season_start_date", sa.Date(), nullable=True),
        sa.Column("phenological_phase", sa.String(length=120), nullable=True),
        sa.Column("phase_source", sa.String(length=32), nullable=True),
        sa.Column("phase_confidence", sa.Float(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
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
        sa.CheckConstraint(
            "phase_confidence IS NULL OR "
            "(phase_confidence >= 0 AND phase_confidence <= 1)",
            name="ck_crop_seasons_phase_confidence",
        ),
    )
    op.create_index(
        "ix_crop_seasons_field_id",
        "crop_seasons",
        ["field_id"],
        unique=False,
    )
    op.create_index(
        "ix_crop_seasons_field_active",
        "crop_seasons",
        ["field_id", "is_active"],
        unique=False,
    )

    _backfill_from_users(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    users, fields, seasons = _tables()
    rows = bind.execute(
        sa.select(
            fields.c.user_id,
            fields.c.id.label("field_id"),
            fields.c.latitude,
            fields.c.longitude,
        ).where(fields.c.is_active.is_(True))
    ).mappings()

    for row in rows:
        crop_key = bind.scalar(
            sa.select(seasons.c.crop_key)
            .where(
                seasons.c.field_id == row["field_id"],
                seasons.c.is_active.is_(True),
            )
            .limit(1)
        )
        bind.execute(
            sa.update(users)
            .where(users.c.id == row["user_id"])
            .values(
                latitude=row["latitude"],
                longitude=row["longitude"],
                selected_crop=crop_key or "wheat",
            )
        )

    op.drop_index("ix_crop_seasons_field_active", table_name="crop_seasons")
    op.drop_index("ix_crop_seasons_field_id", table_name="crop_seasons")
    op.drop_table("crop_seasons")
    op.drop_index("ix_fields_user_active", table_name="fields")
    op.drop_index("ix_fields_user_id", table_name="fields")
    op.drop_table("fields")
