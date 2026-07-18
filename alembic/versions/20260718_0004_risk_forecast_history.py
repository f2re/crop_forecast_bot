"""Add persistent ensemble risk forecast history.

Revision ID: 20260718_0004
Revises: 20260710_0003
Create Date: 2026-07-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "20260718_0004"
down_revision: str | None = "20260710_0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "risk_forecast_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "field_id",
            sa.Integer(),
            sa.ForeignKey("fields.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=180), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(), nullable=False),
        sa.Column("analysis_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("forecast_days", sa.Integer(), nullable=False),
        sa.Column("valid_days", sa.Integer(), nullable=False),
        sa.Column("incomplete_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=240), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "field_id",
            "model",
            "retrieved_at",
            name="uq_risk_forecast_runs_identity",
        ),
    )
    op.create_index(
        "ix_risk_forecast_runs_field_retrieved_at",
        "risk_forecast_runs",
        ["field_id", "retrieved_at"],
    )

    op.create_table(
        "risk_forecast_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("risk_forecast_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("risk_type", sa.String(length=32), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("members_exceeding", sa.Integer(), nullable=False),
        sa.Column("valid_members", sa.Integer(), nullable=False),
        sa.Column("member_fraction", sa.Float(), nullable=False),
        sa.Column("severe_member_fraction", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("severe_threshold", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("p10", sa.Float(), nullable=False),
        sa.Column("median", sa.Float(), nullable=False),
        sa.Column("p90", sa.Float(), nullable=False),
        sa.Column(
            "delivery_state",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'not_attempted'"),
        ),
        sa.Column("notified_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "member_fraction >= 0 AND member_fraction <= 1",
            name="ck_risk_forecast_signals_member_fraction",
        ),
        sa.CheckConstraint(
            "severe_member_fraction >= 0 AND severe_member_fraction <= 1",
            name="ck_risk_forecast_signals_severe_fraction",
        ),
        sa.UniqueConstraint(
            "run_id",
            "risk_type",
            "event_date",
            name="uq_risk_forecast_signals_event",
        ),
    )
    op.create_index(
        "ix_risk_forecast_signals_run_id",
        "risk_forecast_signals",
        ["run_id"],
    )
    op.create_index(
        "ix_risk_forecast_signals_type_date",
        "risk_forecast_signals",
        ["risk_type", "event_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_risk_forecast_signals_type_date",
        table_name="risk_forecast_signals",
    )
    op.drop_index(
        "ix_risk_forecast_signals_run_id",
        table_name="risk_forecast_signals",
    )
    op.drop_table("risk_forecast_signals")
    op.drop_index(
        "ix_risk_forecast_runs_field_retrieved_at",
        table_name="risk_forecast_runs",
    )
    op.drop_table("risk_forecast_runs")
