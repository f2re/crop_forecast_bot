from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import AsyncIterator

from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CropSeason, Field, User


@dataclass(frozen=True, slots=True)
class FieldSummary:
    field_id: int
    field_name: str
    latitude: float
    longitude: float
    timezone: str
    timezone_source: str | None
    elevation_m: float | None
    elevation_source: str | None
    crop_key: str
    season_start_date: date | None
    phenological_phase: str | None
    is_active: bool
    daily_digest_enabled: bool
    frost_alerts_enabled: bool


@dataclass(frozen=True, slots=True)
class FieldSeasonContext:
    telegram_id: int
    field_id: int
    field_name: str
    latitude: float
    longitude: float
    timezone: str
    timezone_source: str | None
    elevation_m: float | None
    elevation_source: str | None
    crop_key: str
    sowing_date: date | None
    season_start_date: date | None
    phenological_phase: str | None
    phase_source: str | None
    phase_confidence: float | None
    daily_digest: bool
    frost_alerts: bool


@dataclass(frozen=True, slots=True)
class NotificationTarget:
    telegram_id: int
    field_id: int
    field_name: str
    latitude: float
    longitude: float
    timezone: str
    elevation_m: float | None
    elevation_source: str | None
    selected_crop: str
    season_start_date: date | None
    phenological_phase: str | None
    daily_digest_enabled: bool
    frost_alerts_enabled: bool


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        session.add(user)
    else:
        if username is not None:
            user.username = username
        if first_name is not None:
            user.first_name = first_name
        user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def _lock_user(session: AsyncSession, telegram_id: int) -> User:
    await get_or_create_user(session, telegram_id)
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id).with_for_update()
    )
    return result.scalar_one()


async def get_active_field(session: AsyncSession, user_id: int) -> Field | None:
    result = await session.execute(
        select(Field)
        .where(Field.user_id == user_id, Field.is_active.is_(True))
        .order_by(Field.updated_at.desc(), Field.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_active_season(session: AsyncSession, field_id: int) -> CropSeason | None:
    result = await session.execute(
        select(CropSeason)
        .where(
            CropSeason.field_id == field_id,
            CropSeason.is_active.is_(True),
        )
        .order_by(CropSeason.updated_at.desc(), CropSeason.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _owned_field(
    session: AsyncSession,
    user_id: int,
    field_id: int,
    *,
    lock: bool = False,
) -> Field:
    statement = select(Field).where(Field.id == field_id, Field.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    field = result.scalar_one_or_none()
    if field is None:
        raise ValueError("Поле не найдено или недоступно пользователю.")
    return field


async def _ensure_active_season(
    session: AsyncSession,
    field: Field,
    crop_key: str,
) -> CropSeason:
    season = await get_active_season(session, field.id)
    if season is None:
        season = CropSeason(field_id=field.id, crop_key=crop_key, is_active=True)
        session.add(season)
        await session.flush()
    return season


def _sync_legacy_profile(user: User, field: Field, season: CropSeason) -> None:
    user.latitude = field.latitude
    user.longitude = field.longitude
    user.selected_crop = season.crop_key
    user.daily_digest = 1 if field.daily_digest_enabled else 0
    user.updated_at = datetime.utcnow()


async def _ensure_unique_field_name(
    session: AsyncSession,
    user_id: int,
    name: str,
    *,
    exclude_field_id: int | None = None,
) -> None:
    result = await session.execute(
        select(Field.id, Field.name).where(Field.user_id == user_id)
    )
    normalized = name.casefold()
    for field_id, existing_name in result.all():
        if field_id != exclude_field_id and existing_name.casefold() == normalized:
            raise ValueError("Поле с таким названием уже существует.")


async def save_coordinates(
    session: AsyncSession,
    telegram_id: int,
    latitude: float,
    longitude: float,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    """Create the first field or update coordinates of the active field."""
    user = await get_or_create_user(session, telegram_id, username, first_name)
    field = await get_active_field(session, user.id)
    if field is None:
        result = await session.execute(
            select(Field)
            .where(Field.user_id == user.id)
            .order_by(Field.updated_at.desc(), Field.id.desc())
            .limit(1)
        )
        field = result.scalar_one_or_none()
    if field is None:
        field = Field(
            user_id=user.id,
            name="Основное поле",
            latitude=latitude,
            longitude=longitude,
            timezone="UTC",
            timezone_source="default until provider response",
            daily_digest_enabled=bool(user.daily_digest),
            frost_alerts_enabled=True,
            is_active=True,
        )
        session.add(field)
        await session.flush()
    else:
        await session.execute(
            update(Field)
            .where(Field.user_id == user.id, Field.is_active.is_(True))
            .values(is_active=False)
        )
        await session.flush()
        field.is_active = True
        field.latitude = latitude
        field.longitude = longitude
        field.timezone = "UTC"
        field.timezone_source = "reset after coordinate change"
        field.elevation_m = None
        field.elevation_source = None
        field.updated_at = datetime.utcnow()

    season = await _ensure_active_season(session, field, user.selected_crop or "wheat")
    _sync_legacy_profile(user, field, season)
    await session.commit()
    await session.refresh(user)
    return user


async def create_field(
    session: AsyncSession,
    telegram_id: int,
    *,
    name: str,
    latitude: float,
    longitude: float,
) -> FieldSummary:
    user = await _lock_user(session, telegram_id)
    await _ensure_unique_field_name(session, user.id, name)
    current = await get_active_field(session, user.id)
    default_crop = user.selected_crop or "wheat"
    default_digest = bool(current.daily_digest_enabled) if current else bool(user.daily_digest)

    await session.execute(
        update(Field)
        .where(Field.user_id == user.id, Field.is_active.is_(True))
        .values(is_active=False, updated_at=datetime.utcnow())
    )
    await session.flush()

    field = Field(
        user_id=user.id,
        name=name,
        latitude=latitude,
        longitude=longitude,
        timezone="UTC",
        timezone_source="default until provider response",
        elevation_m=None,
        elevation_source=None,
        daily_digest_enabled=default_digest,
        frost_alerts_enabled=True,
        is_active=True,
    )
    session.add(field)
    await session.flush()
    season = CropSeason(field_id=field.id, crop_key=default_crop, is_active=True)
    session.add(season)
    await session.flush()
    _sync_legacy_profile(user, field, season)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Не удалось создать поле: название уже используется.") from exc
    return await get_field_summary(session, telegram_id, field.id)


async def update_field_coordinates(
    session: AsyncSession,
    telegram_id: int,
    field_id: int,
    *,
    latitude: float,
    longitude: float,
) -> FieldSummary:
    user = await _lock_user(session, telegram_id)
    field = await _owned_field(session, user.id, field_id, lock=True)
    field.latitude = latitude
    field.longitude = longitude
    field.timezone = "UTC"
    field.timezone_source = "reset after coordinate change"
    field.elevation_m = None
    field.elevation_source = None
    field.updated_at = datetime.utcnow()
    season = await _ensure_active_season(session, field, user.selected_crop or "wheat")
    if field.is_active:
        _sync_legacy_profile(user, field, season)
    await session.commit()
    return await get_field_summary(session, telegram_id, field.id)


async def rename_field(
    session: AsyncSession,
    telegram_id: int,
    field_id: int,
    name: str,
) -> FieldSummary:
    user = await _lock_user(session, telegram_id)
    field = await _owned_field(session, user.id, field_id, lock=True)
    await _ensure_unique_field_name(
        session,
        user.id,
        name,
        exclude_field_id=field.id,
    )
    field.name = name
    field.updated_at = datetime.utcnow()
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Поле с таким названием уже существует.") from exc
    return await get_field_summary(session, telegram_id, field.id)


async def activate_field(
    session: AsyncSession,
    telegram_id: int,
    field_id: int,
) -> FieldSummary:
    user = await _lock_user(session, telegram_id)
    target = await _owned_field(session, user.id, field_id, lock=True)
    await session.execute(
        update(Field)
        .where(Field.user_id == user.id, Field.is_active.is_(True))
        .values(is_active=False, updated_at=datetime.utcnow())
    )
    await session.flush()
    target.is_active = True
    target.updated_at = datetime.utcnow()
    season = await _ensure_active_season(session, target, user.selected_crop or "wheat")
    _sync_legacy_profile(user, target, season)
    await session.commit()
    return await get_field_summary(session, telegram_id, target.id)


async def list_fields(
    session: AsyncSession,
    telegram_id: int,
) -> list[FieldSummary]:
    user = await get_user(session, telegram_id)
    if user is None:
        return []
    result = await session.execute(
        select(
            Field.id,
            Field.name,
            Field.latitude,
            Field.longitude,
            Field.timezone,
            Field.timezone_source,
            Field.elevation_m,
            Field.elevation_source,
            Field.is_active,
            Field.daily_digest_enabled,
            Field.frost_alerts_enabled,
            CropSeason.crop_key,
            CropSeason.season_start_date,
            CropSeason.phenological_phase,
        )
        .outerjoin(
            CropSeason,
            and_(
                CropSeason.field_id == Field.id,
                CropSeason.is_active.is_(True),
            ),
        )
        .where(Field.user_id == user.id)
        .order_by(Field.is_active.desc(), Field.name.asc(), Field.id.asc())
    )
    return [
        FieldSummary(
            field_id=row.id,
            field_name=row.name,
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            timezone=row.timezone or "UTC",
            timezone_source=row.timezone_source,
            elevation_m=(float(row.elevation_m) if row.elevation_m is not None else None),
            elevation_source=row.elevation_source,
            crop_key=row.crop_key or user.selected_crop or "wheat",
            season_start_date=row.season_start_date,
            phenological_phase=row.phenological_phase,
            is_active=bool(row.is_active),
            daily_digest_enabled=bool(row.daily_digest_enabled),
            frost_alerts_enabled=bool(row.frost_alerts_enabled),
        )
        for row in result.all()
    ]


async def get_field_summary(
    session: AsyncSession,
    telegram_id: int,
    field_id: int,
) -> FieldSummary:
    fields = await list_fields(session, telegram_id)
    for field in fields:
        if field.field_id == field_id:
            return field
    raise ValueError("Поле не найдено или недоступно пользователю.")


async def load_coordinates(
    session: AsyncSession,
    telegram_id: int,
) -> tuple[float, float] | None:
    context = await get_field_context(session, telegram_id)
    if context is not None:
        return context.latitude, context.longitude
    user = await get_user(session, telegram_id)
    if user is None or user.latitude is None or user.longitude is None:
        return None
    return user.latitude, user.longitude


async def get_field_context(
    session: AsyncSession,
    telegram_id: int,
) -> FieldSeasonContext | None:
    user = await get_user(session, telegram_id)
    if user is None:
        return None
    field = await get_active_field(session, user.id)
    if field is None:
        return None
    season = await get_active_season(session, field.id)
    return FieldSeasonContext(
        telegram_id=user.telegram_id,
        field_id=field.id,
        field_name=field.name,
        latitude=field.latitude,
        longitude=field.longitude,
        timezone=field.timezone,
        timezone_source=field.timezone_source,
        elevation_m=field.elevation_m,
        elevation_source=field.elevation_source,
        crop_key=(season.crop_key if season else user.selected_crop) or "wheat",
        sowing_date=season.sowing_date if season else None,
        season_start_date=season.season_start_date if season else None,
        phenological_phase=season.phenological_phase if season else None,
        phase_source=season.phase_source if season else None,
        phase_confidence=season.phase_confidence if season else None,
        daily_digest=bool(field.daily_digest_enabled),
        frost_alerts=bool(field.frost_alerts_enabled),
    )


async def get_user_crop(session: AsyncSession, telegram_id: int) -> str:
    context = await get_field_context(session, telegram_id)
    if context is not None:
        return context.crop_key
    user = await get_user(session, telegram_id)
    return user.selected_crop if user and user.selected_crop else "wheat"


async def update_user_crop(
    session: AsyncSession,
    telegram_id: int,
    crop_key: str,
) -> User:
    user = await get_or_create_user(session, telegram_id)
    user.selected_crop = crop_key
    user.updated_at = datetime.utcnow()
    field = await get_active_field(session, user.id)
    if field is not None:
        season = await _ensure_active_season(session, field, crop_key)
        if season.crop_key != crop_key:
            season.crop_key = crop_key
            season.phenological_phase = None
            season.phase_source = None
            season.phase_confidence = None
        season.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def set_season_start(
    session: AsyncSession,
    telegram_id: int,
    season_start: date,
) -> CropSeason:
    user = await get_or_create_user(session, telegram_id)
    field = await get_active_field(session, user.id)
    if field is None:
        raise ValueError("Сначала задайте координаты поля.")
    season = await _ensure_active_season(session, field, user.selected_crop or "wheat")
    season.sowing_date = season_start
    season.season_start_date = season_start
    season.phenological_phase = None
    season.phase_source = None
    season.phase_confidence = None
    season.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(season)
    return season


async def set_manual_phase(
    session: AsyncSession,
    telegram_id: int,
    phase: str,
) -> CropSeason:
    user = await get_or_create_user(session, telegram_id)
    field = await get_active_field(session, user.id)
    if field is None:
        raise ValueError("Сначала задайте координаты поля.")
    season = await _ensure_active_season(session, field, user.selected_crop or "wheat")
    season.phenological_phase = phase
    season.phase_source = "user"
    season.phase_confidence = None
    season.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(season)
    return season


async def clear_manual_phase(session: AsyncSession, telegram_id: int) -> None:
    user = await get_user(session, telegram_id)
    if user is None:
        return
    field = await get_active_field(session, user.id)
    if field is None:
        return
    season = await get_active_season(session, field.id)
    if season is None:
        return
    season.phenological_phase = None
    season.phase_source = None
    season.phase_confidence = None
    season.updated_at = datetime.utcnow()
    await session.commit()


async def update_field_metadata(
    session: AsyncSession,
    field_id: int,
    *,
    timezone: str,
    timezone_source: str,
    elevation_m: float | None,
    elevation_source: str | None,
) -> None:
    field = await session.get(Field, field_id)
    if field is None:
        return
    field.timezone = timezone
    field.timezone_source = timezone_source
    field.elevation_m = elevation_m
    field.elevation_source = elevation_source
    field.updated_at = datetime.utcnow()
    await session.commit()


async def set_field_notifications(
    session: AsyncSession,
    telegram_id: int,
    *,
    daily_digest: bool | None = None,
    frost_alerts: bool | None = None,
) -> FieldSeasonContext:
    user = await _lock_user(session, telegram_id)
    field = await get_active_field(session, user.id)
    if field is None:
        raise ValueError("Сначала задайте поле.")
    if daily_digest is not None:
        field.daily_digest_enabled = daily_digest
        user.daily_digest = 1 if daily_digest else 0
    if frost_alerts is not None:
        field.frost_alerts_enabled = frost_alerts
    field.updated_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    await session.commit()
    context = await get_field_context(session, telegram_id)
    if context is None:
        raise RuntimeError("Активное поле исчезло после сохранения настроек.")
    return context


async def set_daily_digest(
    session: AsyncSession,
    telegram_id: int,
    enabled: bool,
) -> User:
    await set_field_notifications(session, telegram_id, daily_digest=enabled)
    user = await get_user(session, telegram_id)
    if user is None:
        raise RuntimeError("Пользователь не найден после сохранения настроек.")
    return user


async def list_notification_targets(
    session: AsyncSession,
    *,
    daily_digest_only: bool = False,
    frost_alerts_only: bool = False,
) -> list[NotificationTarget]:
    statement = (
        select(
            User.telegram_id,
            User.selected_crop.label("legacy_crop"),
            Field.id.label("field_id"),
            Field.name.label("field_name"),
            Field.latitude,
            Field.longitude,
            Field.timezone,
            Field.elevation_m,
            Field.elevation_source,
            Field.daily_digest_enabled,
            Field.frost_alerts_enabled,
            CropSeason.crop_key,
            CropSeason.season_start_date,
            CropSeason.phenological_phase,
        )
        .join(
            Field,
            and_(Field.user_id == User.id, Field.is_active.is_(True)),
        )
        .outerjoin(
            CropSeason,
            and_(
                CropSeason.field_id == Field.id,
                CropSeason.is_active.is_(True),
            ),
        )
    )
    if daily_digest_only:
        statement = statement.where(Field.daily_digest_enabled.is_(True))
    if frost_alerts_only:
        statement = statement.where(Field.frost_alerts_enabled.is_(True))

    result = await session.execute(statement)
    targets: dict[int, NotificationTarget] = {}
    for row in result.all():
        targets.setdefault(
            row.telegram_id,
            NotificationTarget(
                telegram_id=row.telegram_id,
                field_id=row.field_id,
                field_name=row.field_name,
                latitude=float(row.latitude),
                longitude=float(row.longitude),
                timezone=row.timezone or "UTC",
                elevation_m=(
                    float(row.elevation_m) if row.elevation_m is not None else None
                ),
                elevation_source=row.elevation_source,
                selected_crop=row.crop_key or row.legacy_crop or "wheat",
                season_start_date=row.season_start_date,
                phenological_phase=row.phenological_phase,
                daily_digest_enabled=bool(row.daily_digest_enabled),
                frost_alerts_enabled=bool(row.frost_alerts_enabled),
            ),
        )
    return list(targets.values())


async def get_all_active_users(session: AsyncSession) -> AsyncIterator[User]:
    result = await session.stream(
        select(User).join(
            Field,
            and_(Field.user_id == User.id, Field.is_active.is_(True)),
        )
    )
    async for user in result.scalars().unique():
        yield user


async def get_users_with_daily_digest(session: AsyncSession) -> AsyncIterator[User]:
    result = await session.stream(
        select(User)
        .join(
            Field,
            and_(Field.user_id == User.id, Field.is_active.is_(True)),
        )
        .where(Field.daily_digest_enabled.is_(True))
    )
    async for user in result.scalars().unique():
        yield user
