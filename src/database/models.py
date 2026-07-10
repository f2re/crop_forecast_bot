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
