from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import CropSeason, Field, User


@dataclass(frozen=True, slots=True)
class FieldCropProfile:
    season_id: int
    crop_key: str
    sowing_date: date | None
    season_start_date: date | None
    phenological_phase: str | None
    is_selected: bool


async def _lock_user_and_active_field(
    session: AsyncSession,
    telegram_id: int,
) -> tuple[User, Field]:
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
    return user, field


async def list_field_crops(
    session: AsyncSession,
    telegram_id: int,
    *,
    field_id: int | None = None,
) -> tuple[FieldCropProfile, ...]:
    user_result = await session.execute(
        select(User.id).where(User.telegram_id == telegram_id)
    )
    user_id = user_result.scalar_one_or_none()
    if user_id is None:
        return ()

    if field_id is None:
        field_result = await session.execute(
            select(Field.id).where(
                Field.user_id == user_id,
                Field.is_active.is_(True),
            )
        )
        field_id = field_result.scalar_one_or_none()
        if field_id is None:
            return ()
    else:
        owned = await session.execute(
            select(Field.id).where(Field.id == field_id, Field.user_id == user_id)
        )
        if owned.scalar_one_or_none() is None:
            raise ValueError("Поле не найдено или недоступно пользователю.")

    result = await session.execute(
        select(CropSeason)
        .where(CropSeason.field_id == field_id)
        .order_by(
            CropSeason.is_active.desc(),
            CropSeason.created_at.asc(),
            CropSeason.id.asc(),
        )
    )
    return tuple(
        FieldCropProfile(
            season_id=season.id,
            crop_key=season.crop_key,
            sowing_date=season.sowing_date,
            season_start_date=season.season_start_date,
            phenological_phase=season.phenological_phase,
            is_selected=bool(season.is_active),
        )
        for season in result.scalars().all()
    )


async def list_field_crop_keys(
    session: AsyncSession,
    field_id: int,
) -> tuple[str, ...]:
    result = await session.execute(
        select(CropSeason.crop_key)
        .where(CropSeason.field_id == field_id)
        .order_by(CropSeason.is_active.desc(), CropSeason.created_at.asc())
    )
    return tuple(dict.fromkeys(result.scalars().all()))


async def add_or_select_crop(
    session: AsyncSession,
    telegram_id: int,
    crop_key: str,
) -> FieldCropProfile:
    """Add a crop profile at the active coordinates and select it for editing."""

    user, field = await _lock_user_and_active_field(session, telegram_id)
    existing_result = await session.execute(
        select(CropSeason)
        .where(CropSeason.field_id == field.id, CropSeason.crop_key == crop_key)
        .order_by(CropSeason.updated_at.desc(), CropSeason.id.desc())
        .limit(1)
        .with_for_update()
    )
    season = existing_result.scalar_one_or_none()

    # ``is_active`` remains the selected profile marker for backward-compatible
    # report/phase code. Other rows are additional crop profiles at the same point.
    await session.execute(
        update(CropSeason)
        .where(CropSeason.field_id == field.id, CropSeason.is_active.is_(True))
        .values(is_active=False, updated_at=datetime.utcnow())
    )
    await session.flush()

    if season is None:
        season = CropSeason(
            field_id=field.id,
            crop_key=crop_key,
            is_active=True,
        )
        session.add(season)
        await session.flush()
    else:
        season.is_active = True
        season.updated_at = datetime.utcnow()

    user.selected_crop = crop_key
    user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(season)
    return FieldCropProfile(
        season_id=season.id,
        crop_key=season.crop_key,
        sowing_date=season.sowing_date,
        season_start_date=season.season_start_date,
        phenological_phase=season.phenological_phase,
        is_selected=True,
    )


async def select_field_crop(
    session: AsyncSession,
    telegram_id: int,
    season_id: int,
) -> FieldCropProfile:
    user, field = await _lock_user_and_active_field(session, telegram_id)
    result = await session.execute(
        select(CropSeason)
        .where(CropSeason.id == season_id, CropSeason.field_id == field.id)
        .with_for_update()
    )
    season = result.scalar_one_or_none()
    if season is None:
        raise ValueError("Культура не найдена для активного поля.")

    await session.execute(
        update(CropSeason)
        .where(CropSeason.field_id == field.id, CropSeason.is_active.is_(True))
        .values(is_active=False, updated_at=datetime.utcnow())
    )
    await session.flush()
    season.is_active = True
    season.updated_at = datetime.utcnow()
    user.selected_crop = season.crop_key
    user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(season)
    return FieldCropProfile(
        season_id=season.id,
        crop_key=season.crop_key,
        sowing_date=season.sowing_date,
        season_start_date=season.season_start_date,
        phenological_phase=season.phenological_phase,
        is_selected=True,
    )


async def remove_field_crop(
    session: AsyncSession,
    telegram_id: int,
    season_id: int,
) -> FieldCropProfile:
    user, field = await _lock_user_and_active_field(session, telegram_id)
    result = await session.execute(
        select(CropSeason)
        .where(CropSeason.field_id == field.id)
        .order_by(CropSeason.is_active.desc(), CropSeason.created_at.asc())
        .with_for_update()
    )
    seasons = list(result.scalars().all())
    if len(seasons) <= 1:
        raise ValueError("Нельзя удалить единственную культуру поля.")

    target = next((item for item in seasons if item.id == season_id), None)
    if target is None:
        raise ValueError("Культура не найдена для активного поля.")

    remaining = [item for item in seasons if item.id != season_id]
    if target.is_active:
        # Release the partial unique index before selecting the replacement.
        # SQLAlchemy may otherwise flush UPDATEs before DELETE and temporarily
        # create two selected rows in PostgreSQL.
        target.is_active = False
        target.updated_at = datetime.utcnow()
        await session.flush()
        selected = remaining[0]
        selected.is_active = True
        selected.updated_at = datetime.utcnow()
    else:
        selected = next((item for item in remaining if item.is_active), remaining[0])
        if not selected.is_active:
            selected.is_active = True
            selected.updated_at = datetime.utcnow()

    await session.delete(target)
    user.selected_crop = selected.crop_key
    user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(selected)
    return FieldCropProfile(
        season_id=selected.id,
        crop_key=selected.crop_key,
        sowing_date=selected.sowing_date,
        season_start_date=selected.season_start_date,
        phenological_phase=selected.phenological_phase,
        is_selected=True,
    )
