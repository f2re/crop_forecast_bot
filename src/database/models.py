from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """Telegram identity and transitional compatibility fields."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
    )
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Transitional columns retained for one compatibility window.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    selected_crop: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default="wheat",
        server_default="wheat",
    )
    daily_digest: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    fields: Mapped[list["Field"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            "<User("
            f"id={self.id}, telegram_id={self.telegram_id}, username={self.username!r}"
            ")>"
        )


class Field(Base):
    """A geographically fixed agricultural field owned by a Telegram user."""

    __tablename__ = "fields"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_fields_user_name"),
        CheckConstraint(
            "risk_delivery_mode IN ('immediate', 'digest', 'high_only')",
            name="ck_fields_risk_delivery_mode",
        ),
        CheckConstraint(
            "(quiet_hours_start IS NULL AND quiet_hours_end IS NULL) OR "
            "(quiet_hours_start BETWEEN 0 AND 23 AND "
            "quiet_hours_end BETWEEN 0 AND 23 AND "
            "quiet_hours_start <> quiet_hours_end)",
            name="ck_fields_quiet_hours",
        ),
        Index(
            "uq_fields_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="Основное поле",
        server_default="Основное поле",
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="UTC",
        server_default="UTC",
    )
    timezone_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    elevation_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    daily_digest_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    frost_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    risk_delivery_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="immediate",
        server_default="immediate",
    )
    quiet_hours_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quiet_hours_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    user: Mapped["User"] = relationship(back_populates="fields")
    seasons: Mapped[list["CropSeason"]] = relationship(
        back_populates="field",
        cascade="all, delete-orphan",
    )
    risk_forecast_runs: Mapped[list["RiskForecastRun"]] = relationship(
        back_populates="field",
        cascade="all, delete-orphan",
    )


class CropSeason(Base):
    """Crop and agronomic context for one active field season."""

    __tablename__ = "crop_seasons"
    __table_args__ = (
        CheckConstraint(
            "phase_confidence IS NULL OR "
            "(phase_confidence >= 0 AND phase_confidence <= 1)",
            name="ck_crop_seasons_phase_confidence",
        ),
        Index(
            "uq_crop_seasons_one_active_per_field",
            "field_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(
        ForeignKey("fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    crop_key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="wheat",
        server_default="wheat",
    )
    sowing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    season_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    phenological_phase: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phase_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phase_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    field: Mapped["Field"] = relationship(back_populates="seasons")


class RiskForecastRun(Base):
    """One accepted ensemble forecast run for one field."""

    __tablename__ = "risk_forecast_runs"
    __table_args__ = (
        UniqueConstraint(
            "field_id",
            "model",
            "retrieved_at",
            name="uq_risk_forecast_runs_identity",
        ),
        Index(
            "ix_risk_forecast_runs_field_retrieved_at",
            "field_id",
            "retrieved_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(
        ForeignKey("fields.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(180), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    analysis_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_days: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_days: Mapped[int] = mapped_column(Integer, nullable=False)
    incomplete_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(240), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    field: Mapped["Field"] = relationship(back_populates="risk_forecast_runs")
    signals: Mapped[list["RiskForecastSignal"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RiskForecastSignal.event_date, RiskForecastSignal.id",
    )


class RiskForecastSignal(Base):
    """One risk threshold crossing produced by an accepted forecast run."""

    __tablename__ = "risk_forecast_signals"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "risk_type",
            "event_date",
            name="uq_risk_forecast_signals_event",
        ),
        CheckConstraint(
            "member_fraction >= 0 AND member_fraction <= 1",
            name="ck_risk_forecast_signals_member_fraction",
        ),
        CheckConstraint(
            "severe_member_fraction >= 0 AND severe_member_fraction <= 1",
            name="ck_risk_forecast_signals_severe_fraction",
        ),
        Index(
            "ix_risk_forecast_signals_type_date",
            "risk_type",
            "event_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("risk_forecast_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    risk_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    lead_days: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    members_exceeding: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_members: Mapped[int] = mapped_column(Integer, nullable=False)
    member_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    severe_member_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    severe_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    p10: Mapped[float] = mapped_column(Float, nullable=False)
    median: Mapped[float] = mapped_column(Float, nullable=False)
    p90: Mapped[float] = mapped_column(Float, nullable=False)
    delivery_state: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="not_attempted",
        server_default="not_attempted",
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    run: Mapped["RiskForecastRun"] = relationship(back_populates="signals")
