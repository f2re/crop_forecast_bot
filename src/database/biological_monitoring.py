from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    insert,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Base, CropSeason, Field, User
from src.domain.late_blight_delivery import (
    LATE_BLIGHT_MODEL_KEY,
    LATE_BLIGHT_STATE_VERSION,
    InoculumContext,
    LateBlightDeliveryState,
    deserialize_late_blight_delivery_state,
    empty_late_blight_delivery_state,
    serialize_late_blight_delivery_state,
    validate_inoculum_context,
)
from src.domain.risk_delivery import RiskDeliveryMode, validate_risk_delivery_mode


def _register_table(metadata: MetaData) -> Table:
    existing = metadata.tables.get("biological_monitors")
    if existing is not None:
        return existing
    return Table(
        "biological_monitors",
        metadata,
        Column("id", Integer, primary_key=True),
        Column(
            "crop_season_id",
            Integer,
            ForeignKey("crop_seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("model_key", String(80), nullable=False),
        Column("enabled", Boolean, nullable=False, default=True),
        Column(
            "inoculum_context",
            String(32),
            nullable=False,
            default="unknown",
        ),
        Column(
            "state_version",
            Integer,
            nullable=False,
            default=LATE_BLIGHT_STATE_VERSION,
        ),
        Column("state_json", Text, nullable=False),
        Column("last_checked_local_date", Date, nullable=True),
        Column("last_observed_at", DateTime, nullable=True),
        Column("last_notified_at", DateTime, nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        UniqueConstraint(
            "crop_season_id",
            "model_key",
            name="uq_biological_monitors_season_model",
        ),
        CheckConstraint(
            "inoculum_context IN ("
            "'unknown', 'regional_alert_confirmed', "
            "'nearby_outbreak_confirmed', 'field_source_suspected', "
            "'field_symptoms_observed')",
            name="ck_biological_monitors_inoculum_context",
        ),
        Index("ix_biological_monitors_enabled", "enabled"),
        Index("ix_biological_monitors_observed_at", "last_observed_at"),
    )


biological_monitors = _register_table(Base.metadata)


@dataclass(frozen=True, slots=True)
class LateBlightMonitorContext:
    telegram_id: int
    field_id: int
    field_name: str
    latitude: float
    longitude: float
    timezone: str
    season_id: int
    crop_key: str
    monitor_id: int | None
    enabled: bool
    inoculum_context: InoculumContext
    delivery_state: LateBlightDeliveryState
    last_checked_local_date: date | None
    last_observed_at: datetime | None
    last_notified_at: datetime | None
    risk_delivery_mode: RiskDeliveryMode
    quiet_hours_start: int | None
    quiet_hours_end: int | None


@dataclass(frozen=True, slots=True)
class LateBlightMonitoringTarget:
    telegram_id: int
    monitor_id: int
    monitor_ids: tuple[int, ...]
    field_id: int
    field_ids: tuple[int, ...]
    field_name: str
    field_names: tuple[str, ...]
    latitude: float
    longitude: float
    timezone: str
    season_id: int
    crop_key: str
    inoculum_context: InoculumContext
    delivery_state: LateBlightDeliveryState
    last_checked_local_date: date | None
    last_observed_at: datetime | None
    last_notified_at: datetime | None
    risk_delivery_mode: RiskDeliveryMode
    quiet_hours_start: int | None
    quiet_hours_end: int | None


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _decode_state(raw_value: str | None, version: int | None) -> LateBlightDeliveryState:
    if not raw_value or version != LATE_BLIGHT_STATE_VERSION:
        return empty_late_blight_delivery_state()
    try:
        return deserialize_late_blight_delivery_state(raw_value)
    except ValueError as exc:
        raise RuntimeError("Повреждено состояние наблюдения за фитофторозом") from exc


def _base_context_statement(telegram_id: int):
    return (
        select(
            User.telegram_id,
            Field.id.label("field_id"),
            Field.name.label("field_name"),
            Field.latitude,
            Field.longitude,
            Field.timezone,
            Field.risk_delivery_mode,
            Field.quiet_hours_start,
            Field.quiet_hours_end,
            CropSeason.id.label("season_id"),
            CropSeason.crop_key,
            biological_monitors.c.id.label("monitor_id"),
            biological_monitors.c.enabled,
            biological_monitors.c.inoculum_context,
            biological_monitors.c.state_version,
            biological_monitors.c.state_json,
            biological_monitors.c.last_checked_local_date,
            biological_monitors.c.last_observed_at,
            biological_monitors.c.last_notified_at,
        )
        .join(
            Field,
            and_(Field.user_id == User.id, Field.is_active.is_(True)),
        )
        .join(
            CropSeason,
            and_(
                CropSeason.field_id == Field.id,
                CropSeason.is_active.is_(True),
            ),
        )
        .outerjoin(
            biological_monitors,
            and_(
                biological_monitors.c.crop_season_id == CropSeason.id,
                biological_monitors.c.model_key == LATE_BLIGHT_MODEL_KEY,
            ),
        )
        .where(User.telegram_id == telegram_id)
        .limit(1)
    )


def _context_from_row(row) -> LateBlightMonitorContext:
    context = validate_inoculum_context(row.inoculum_context or "unknown")
    return LateBlightMonitorContext(
        telegram_id=int(row.telegram_id),
        field_id=int(row.field_id),
        field_name=str(row.field_name),
        latitude=float(row.latitude),
        longitude=float(row.longitude),
        timezone=str(row.timezone or "UTC"),
        season_id=int(row.season_id),
        crop_key=str(row.crop_key),
        monitor_id=(int(row.monitor_id) if row.monitor_id is not None else None),
        enabled=bool(row.enabled) if row.monitor_id is not None else False,
        inoculum_context=context,
        delivery_state=_decode_state(row.state_json, row.state_version),
        last_checked_local_date=row.last_checked_local_date,
        last_observed_at=row.last_observed_at,
        last_notified_at=row.last_notified_at,
        risk_delivery_mode=validate_risk_delivery_mode(
            row.risk_delivery_mode or "immediate"
        ),
        quiet_hours_start=row.quiet_hours_start,
        quiet_hours_end=row.quiet_hours_end,
    )


async def get_active_late_blight_context(
    session: AsyncSession,
    telegram_id: int,
) -> LateBlightMonitorContext | None:
    result = await session.execute(_base_context_statement(telegram_id))
    row = result.one_or_none()
    return None if row is None else _context_from_row(row)


async def enable_late_blight_monitor(
    session: AsyncSession,
    telegram_id: int,
) -> LateBlightMonitorContext:
    context = await get_active_late_blight_context(session, telegram_id)
    if context is None:
        raise ValueError("Сначала добавьте поле и выберите культуру.")
    if context.crop_key != "potato":
        raise ValueError("Наблюдение Hutton сейчас доступно только для картофеля.")

    now = datetime.utcnow()
    empty_state = empty_late_blight_delivery_state()
    if context.monitor_id is None:
        await session.execute(
            insert(biological_monitors).values(
                crop_season_id=context.season_id,
                model_key=LATE_BLIGHT_MODEL_KEY,
                enabled=True,
                inoculum_context="unknown",
                state_version=LATE_BLIGHT_STATE_VERSION,
                state_json=serialize_late_blight_delivery_state(empty_state),
                created_at=now,
                updated_at=now,
            )
        )
    elif not context.enabled:
        await session.execute(
            update(biological_monitors)
            .where(biological_monitors.c.id == context.monitor_id)
            .values(
                enabled=True,
                inoculum_context="unknown",
                state_version=LATE_BLIGHT_STATE_VERSION,
                state_json=serialize_late_blight_delivery_state(empty_state),
                last_checked_local_date=None,
                last_observed_at=None,
                last_notified_at=None,
                updated_at=now,
            )
        )
    await session.commit()

    saved = await get_active_late_blight_context(session, telegram_id)
    if saved is None or saved.monitor_id is None:
        raise RuntimeError("Наблюдение за фитофторозом не сохранилось.")
    return saved


async def disable_late_blight_monitor(
    session: AsyncSession,
    telegram_id: int,
) -> LateBlightMonitorContext:
    context = await get_active_late_blight_context(session, telegram_id)
    if context is None:
        raise ValueError("Сначала добавьте поле и выберите культуру.")
    if context.monitor_id is not None and context.enabled:
        await session.execute(
            update(biological_monitors)
            .where(biological_monitors.c.id == context.monitor_id)
            .values(enabled=False, updated_at=datetime.utcnow())
        )
        await session.commit()
    saved = await get_active_late_blight_context(session, telegram_id)
    if saved is None:
        raise RuntimeError("Профиль поля исчез после изменения настройки.")
    return saved


def _target_from_row(row) -> LateBlightMonitoringTarget:
    monitor_id = int(row.monitor_id)
    return LateBlightMonitoringTarget(
        telegram_id=int(row.telegram_id),
        monitor_id=monitor_id,
        monitor_ids=(monitor_id,),
        field_id=int(row.field_id),
        field_ids=(int(row.field_id),),
        field_name=str(row.field_name),
        field_names=(str(row.field_name),),
        latitude=float(row.latitude),
        longitude=float(row.longitude),
        timezone=str(row.timezone or "UTC"),
        season_id=int(row.season_id),
        crop_key=str(row.crop_key),
        inoculum_context=validate_inoculum_context(row.inoculum_context),
        delivery_state=_decode_state(row.state_json, row.state_version),
        last_checked_local_date=row.last_checked_local_date,
        last_observed_at=row.last_observed_at,
        last_notified_at=row.last_notified_at,
        risk_delivery_mode=validate_risk_delivery_mode(
            row.risk_delivery_mode or "immediate"
        ),
        quiet_hours_start=row.quiet_hours_start,
        quiet_hours_end=row.quiet_hours_end,
    )


def _location_key(target: LateBlightMonitoringTarget) -> tuple[object, ...]:
    return (
        target.telegram_id,
        round(target.latitude, 5),
        round(target.longitude, 5),
        target.timezone,
        target.risk_delivery_mode,
        target.quiet_hours_start,
        target.quiet_hours_end,
        target.inoculum_context,
    )


def _timestamp_key(value: datetime | None) -> datetime:
    return datetime.min if value is None else _utc_naive(value)


def collapse_late_blight_targets(
    targets: list[LateBlightMonitoringTarget],
) -> list[LateBlightMonitoringTarget]:
    groups: dict[tuple[object, ...], list[LateBlightMonitoringTarget]] = {}
    for target in targets:
        groups.setdefault(_location_key(target), []).append(target)

    collapsed: list[LateBlightMonitoringTarget] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda item: (item.field_id, item.monitor_id))
        primary = ordered[0]
        state_source = max(
            ordered,
            key=lambda item: (
                _timestamp_key(item.last_notified_at),
                _timestamp_key(item.last_observed_at),
                -item.monitor_id,
            ),
        )
        field_names = tuple(dict.fromkeys(item.field_name for item in ordered))
        combined_name = " / ".join(field_names)
        if len(combined_name) > 120:
            combined_name = combined_name[:117].rstrip() + "…"
        collapsed.append(
            replace(
                primary,
                monitor_ids=tuple(item.monitor_id for item in ordered),
                field_ids=tuple(item.field_id for item in ordered),
                field_names=field_names,
                field_name=combined_name,
                delivery_state=state_source.delivery_state,
                last_checked_local_date=max(
                    (
                        item.last_checked_local_date
                        for item in ordered
                        if item.last_checked_local_date is not None
                    ),
                    default=None,
                ),
                last_observed_at=max(
                    (
                        item.last_observed_at
                        for item in ordered
                        if item.last_observed_at is not None
                    ),
                    key=_timestamp_key,
                    default=None,
                ),
                last_notified_at=max(
                    (
                        item.last_notified_at
                        for item in ordered
                        if item.last_notified_at is not None
                    ),
                    key=_timestamp_key,
                    default=None,
                ),
            )
        )
    collapsed.sort(key=lambda item: (item.telegram_id, item.field_id))
    return collapsed


async def list_enabled_late_blight_targets(
    session: AsyncSession,
) -> list[LateBlightMonitoringTarget]:
    result = await session.execute(
        select(
            User.telegram_id,
            Field.id.label("field_id"),
            Field.name.label("field_name"),
            Field.latitude,
            Field.longitude,
            Field.timezone,
            Field.risk_delivery_mode,
            Field.quiet_hours_start,
            Field.quiet_hours_end,
            CropSeason.id.label("season_id"),
            CropSeason.crop_key,
            biological_monitors.c.id.label("monitor_id"),
            biological_monitors.c.inoculum_context,
            biological_monitors.c.state_version,
            biological_monitors.c.state_json,
            biological_monitors.c.last_checked_local_date,
            biological_monitors.c.last_observed_at,
            biological_monitors.c.last_notified_at,
        )
        .join(CropSeason, CropSeason.id == biological_monitors.c.crop_season_id)
        .join(Field, Field.id == CropSeason.field_id)
        .join(User, User.id == Field.user_id)
        .where(
            biological_monitors.c.enabled.is_(True),
            biological_monitors.c.model_key == LATE_BLIGHT_MODEL_KEY,
            CropSeason.is_active.is_(True),
            CropSeason.crop_key == "potato",
        )
        .order_by(User.telegram_id.asc(), Field.id.asc())
    )
    return collapse_late_blight_targets(
        [_target_from_row(row) for row in result.all()]
    )


async def save_late_blight_delivery_state(
    session: AsyncSession,
    *,
    monitor_ids: tuple[int, ...],
    state: LateBlightDeliveryState,
    checked_local_date: date,
    observed_at: datetime,
    notified_at: datetime | None = None,
) -> None:
    if not monitor_ids:
        raise ValueError("monitor_ids must not be empty")
    values: dict[str, object] = {
        "state_version": LATE_BLIGHT_STATE_VERSION,
        "state_json": serialize_late_blight_delivery_state(state),
        "last_checked_local_date": checked_local_date,
        "last_observed_at": _utc_naive(observed_at),
        "updated_at": datetime.utcnow(),
    }
    if notified_at is not None:
        values["last_notified_at"] = _utc_naive(notified_at)
    await session.execute(
        update(biological_monitors)
        .where(biological_monitors.c.id.in_(monitor_ids))
        .values(**values)
    )
    await session.commit()


async def mark_late_blight_observed(
    session: AsyncSession,
    *,
    monitor_ids: tuple[int, ...],
    checked_local_date: date,
    observed_at: datetime,
) -> None:
    if not monitor_ids:
        return
    await session.execute(
        update(biological_monitors)
        .where(biological_monitors.c.id.in_(monitor_ids))
        .values(
            last_checked_local_date=checked_local_date,
            last_observed_at=_utc_naive(observed_at),
            updated_at=datetime.utcnow(),
        )
    )
    await session.commit()
