from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    and_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.database.models import Base, CropSeason, Field, User
from src.domain.pests import PestModel, validate_pest_for_crop


class PestMonitor(Base):
    """One user-enabled, crop-specific pest development monitor."""

    __tablename__ = "pest_monitors"
    __table_args__ = (
        UniqueConstraint(
            "crop_season_id",
            "pest_key",
            name="uq_pest_monitors_crop_pest",
        ),
        Index("ix_pest_monitors_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crop_season_id: Mapped[int] = mapped_column(
        ForeignKey("crop_seasons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pest_key: Mapped[str] = mapped_column(String(64), nullable=False)
    biofix_date: Mapped[date] = mapped_column(Date, nullable=False)
    biofix_type: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_checked_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_notified_stage: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )
    last_notified_advance: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


@dataclass(frozen=True, slots=True)
class ActivePestContext:
    telegram_id: int
    field_id: int
    field_name: str
    latitude: float
    longitude: float
    timezone: str
    season_id: int
    crop_key: str
    monitor_id: int | None
    pest_key: str | None
    biofix_date: date | None
    biofix_type: str | None
    model_version: str | None
    enabled: bool
    last_checked_local_date: date | None
    last_notified_stage: str | None
    last_notified_advance: str | None
    last_notified_at: datetime | None


@dataclass(frozen=True, slots=True)
class PestMonitoringTarget:
    telegram_id: int
    field_id: int
    field_name: str
    latitude: float
    longitude: float
    timezone: str
    season_id: int
    crop_key: str
    monitor_id: int
    pest_key: str
    biofix_date: date
    biofix_type: str
    model_version: str
    last_checked_local_date: date | None
    last_notified_stage: str | None
    last_notified_advance: str | None


def _active_context_from_row(row) -> ActivePestContext:
    return ActivePestContext(
        telegram_id=int(row.telegram_id),
        field_id=int(row.field_id),
        field_name=str(row.field_name),
        latitude=float(row.latitude),
        longitude=float(row.longitude),
        timezone=str(row.timezone or "UTC"),
        season_id=int(row.season_id),
        crop_key=str(row.crop_key),
        monitor_id=(int(row.monitor_id) if row.monitor_id is not None else None),
        pest_key=(str(row.pest_key) if row.pest_key is not None else None),
        biofix_date=row.biofix_date,
        biofix_type=(str(row.biofix_type) if row.biofix_type is not None else None),
        model_version=(
            str(row.model_version) if row.model_version is not None else None
        ),
        enabled=bool(row.enabled) if row.enabled is not None else False,
        last_checked_local_date=row.last_checked_local_date,
        last_notified_stage=row.last_notified_stage,
        last_notified_advance=row.last_notified_advance,
        last_notified_at=row.last_notified_at,
    )


async def get_active_pest_context(
    session: AsyncSession,
    telegram_id: int,
    pest_key: str | None = None,
) -> ActivePestContext | None:
    join_conditions = [PestMonitor.crop_season_id == CropSeason.id]
    if pest_key is not None:
        join_conditions.append(PestMonitor.pest_key == pest_key)

    result = await session.execute(
        select(
            User.telegram_id,
            Field.id.label("field_id"),
            Field.name.label("field_name"),
            Field.latitude,
            Field.longitude,
            Field.timezone,
            CropSeason.id.label("season_id"),
            CropSeason.crop_key,
            PestMonitor.id.label("monitor_id"),
            PestMonitor.pest_key,
            PestMonitor.biofix_date,
            PestMonitor.biofix_type,
            PestMonitor.model_version,
            PestMonitor.enabled,
            PestMonitor.last_checked_local_date,
            PestMonitor.last_notified_stage,
            PestMonitor.last_notified_advance,
            PestMonitor.last_notified_at,
        )
        .join(Field, and_(Field.user_id == User.id, Field.is_active.is_(True)))
        .join(
            CropSeason,
            and_(
                CropSeason.field_id == Field.id,
                CropSeason.is_active.is_(True),
            ),
        )
        .outerjoin(PestMonitor, and_(*join_conditions))
        .where(User.telegram_id == telegram_id)
        .limit(1)
    )
    row = result.one_or_none()
    return None if row is None else _active_context_from_row(row)


async def _locked_active_crop(
    session: AsyncSession,
    telegram_id: int,
) -> tuple[Field, CropSeason]:
    user_result = await session.execute(
        select(User).where(User.telegram_id == telegram_id).with_for_update()
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise ValueError("Сначала добавьте поле.")

    field_result = await session.execute(
        select(Field)
        .where(Field.user_id == user.id, Field.is_active.is_(True))
        .with_for_update()
    )
    field = field_result.scalar_one_or_none()
    if field is None:
        raise ValueError("Сначала добавьте поле.")

    season_result = await session.execute(
        select(CropSeason)
        .where(
            CropSeason.field_id == field.id,
            CropSeason.is_active.is_(True),
        )
        .with_for_update()
    )
    season = season_result.scalar_one_or_none()
    if season is None:
        raise ValueError("Сначала выберите культуру.")
    return field, season


async def upsert_pest_monitor(
    session: AsyncSession,
    telegram_id: int,
    *,
    pest_key: str,
    biofix_date: date,
) -> ActivePestContext:
    _, season = await _locked_active_crop(session, telegram_id)
    model: PestModel = validate_pest_for_crop(pest_key, season.crop_key)

    result = await session.execute(
        select(PestMonitor)
        .where(
            PestMonitor.crop_season_id == season.id,
            PestMonitor.pest_key == model.key,
        )
        .with_for_update()
    )
    monitor = result.scalar_one_or_none()
    changed_origin = monitor is None or monitor.biofix_date != biofix_date
    changed_model = monitor is None or monitor.model_version != model.model_version
    if monitor is None:
        monitor = PestMonitor(
            crop_season_id=season.id,
            pest_key=model.key,
            biofix_date=biofix_date,
            biofix_type=model.biofix_type,
            model_version=model.model_version,
            enabled=True,
        )
        session.add(monitor)
    else:
        monitor.biofix_date = biofix_date
        monitor.biofix_type = model.biofix_type
        monitor.model_version = model.model_version
        monitor.enabled = True

    if changed_origin or changed_model:
        monitor.last_checked_local_date = None
        monitor.last_notified_stage = None
        monitor.last_notified_advance = None
        monitor.last_notified_at = None
    monitor.updated_at = datetime.utcnow()
    await session.commit()

    context = await get_active_pest_context(session, telegram_id, model.key)
    if context is None or context.monitor_id is None:
        raise RuntimeError("Наблюдение за вредителем не сохранилось.")
    return context


async def disable_pest_monitor(
    session: AsyncSession,
    telegram_id: int,
    pest_key: str,
) -> ActivePestContext:
    _, season = await _locked_active_crop(session, telegram_id)
    model = validate_pest_for_crop(pest_key, season.crop_key)
    result = await session.execute(
        select(PestMonitor)
        .where(
            PestMonitor.crop_season_id == season.id,
            PestMonitor.pest_key == model.key,
        )
        .with_for_update()
    )
    monitor = result.scalar_one_or_none()
    if monitor is None:
        raise ValueError("Наблюдение за этим вредителем ещё не включено.")
    monitor.enabled = False
    monitor.updated_at = datetime.utcnow()
    await session.commit()

    context = await get_active_pest_context(session, telegram_id, model.key)
    if context is None:
        raise RuntimeError("Профиль культуры исчез после изменения настройки.")
    return context


async def list_enabled_pest_targets(
    session: AsyncSession,
) -> list[PestMonitoringTarget]:
    result = await session.execute(
        select(
            User.telegram_id,
            Field.id.label("field_id"),
            Field.name.label("field_name"),
            Field.latitude,
            Field.longitude,
            Field.timezone,
            CropSeason.id.label("season_id"),
            CropSeason.crop_key,
            PestMonitor.id.label("monitor_id"),
            PestMonitor.pest_key,
            PestMonitor.biofix_date,
            PestMonitor.biofix_type,
            PestMonitor.model_version,
            PestMonitor.last_checked_local_date,
            PestMonitor.last_notified_stage,
            PestMonitor.last_notified_advance,
        )
        .join(CropSeason, CropSeason.id == PestMonitor.crop_season_id)
        .join(Field, Field.id == CropSeason.field_id)
        .join(User, User.id == Field.user_id)
        .where(PestMonitor.enabled.is_(True))
        .order_by(Field.id.asc(), CropSeason.id.asc(), PestMonitor.id.asc())
    )
    return [
        PestMonitoringTarget(
            telegram_id=int(row.telegram_id),
            field_id=int(row.field_id),
            field_name=str(row.field_name),
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            timezone=str(row.timezone or "UTC"),
            season_id=int(row.season_id),
            crop_key=str(row.crop_key),
            monitor_id=int(row.monitor_id),
            pest_key=str(row.pest_key),
            biofix_date=row.biofix_date,
            biofix_type=str(row.biofix_type),
            model_version=str(row.model_version),
            last_checked_local_date=row.last_checked_local_date,
            last_notified_stage=row.last_notified_stage,
            last_notified_advance=row.last_notified_advance,
        )
        for row in result.all()
    ]


async def mark_pest_monitor_checked(
    session: AsyncSession,
    monitor_id: int,
    *,
    local_date: date,
    stage_event_key: str | None = None,
    advance_event_key: str | None = None,
    notified_at: datetime | None = None,
) -> bool:
    result = await session.execute(
        select(PestMonitor).where(PestMonitor.id == monitor_id).with_for_update()
    )
    monitor = result.scalar_one_or_none()
    if monitor is None:
        return False
    monitor.last_checked_local_date = local_date
    if stage_event_key is not None:
        monitor.last_notified_stage = stage_event_key
    if advance_event_key is not None:
        monitor.last_notified_advance = advance_event_key
    if notified_at is not None:
        timestamp = notified_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        monitor.last_notified_at = timestamp.astimezone(timezone.utc)
    monitor.updated_at = datetime.utcnow()
    await session.commit()
    return True
