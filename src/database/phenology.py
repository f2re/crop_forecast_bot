from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agro.crop_catalog import get_crop_phases
from src.database.models import CropSeason, Field, User
from src.domain.phenology import (
    DateBasis,
    PlantType,
    ProductionSystem,
    validate_date_basis,
    validate_plant_type,
    validate_production_system,
)


@dataclass(frozen=True, slots=True)
class CropPhenologyContext:
    telegram_id: int
    field_id: int
    field_name: str
    timezone: str
    season_id: int
    crop_key: str
    season_start_date: date | None
    sowing_date: date | None
    date_basis: DateBasis
    production_system: ProductionSystem
    plant_type: PlantType
    cultivar_name: str | None
    maturity_group: str | None
    phenological_phase: str | None
    phase_source: str | None
    phase_confirmed_at: datetime | None
    phase_observation_note: str | None


def _context_from_row(row) -> CropPhenologyContext:
    return CropPhenologyContext(
        telegram_id=int(row.telegram_id),
        field_id=int(row.field_id),
        field_name=str(row.field_name),
        timezone=str(row.timezone or "UTC"),
        season_id=int(row.season_id),
        crop_key=str(row.crop_key),
        season_start_date=row.season_start_date,
        sowing_date=row.sowing_date,
        date_basis=validate_date_basis(str(row.date_basis or "season_start")),
        production_system=validate_production_system(
            str(row.production_system or "unknown")
        ),
        plant_type=validate_plant_type(str(row.plant_type or "unknown")),
        cultivar_name=row.cultivar_name,
        maturity_group=row.maturity_group,
        phenological_phase=row.phenological_phase,
        phase_source=row.phase_source,
        phase_confirmed_at=row.phase_confirmed_at,
        phase_observation_note=row.phase_observation_note,
    )


async def get_active_crop_phenology(
    session: AsyncSession,
    telegram_id: int,
) -> CropPhenologyContext | None:
    result = await session.execute(
        select(
            User.telegram_id,
            Field.id.label("field_id"),
            Field.name.label("field_name"),
            Field.timezone,
            CropSeason.id.label("season_id"),
            CropSeason.crop_key,
            CropSeason.season_start_date,
            CropSeason.sowing_date,
            CropSeason.date_basis,
            CropSeason.production_system,
            CropSeason.plant_type,
            CropSeason.cultivar_name,
            CropSeason.maturity_group,
            CropSeason.phenological_phase,
            CropSeason.phase_source,
            CropSeason.phase_confirmed_at,
            CropSeason.phase_observation_note,
        )
        .join(Field, and_(Field.user_id == User.id, Field.is_active.is_(True)))
        .join(
            CropSeason,
            and_(
                CropSeason.field_id == Field.id,
                CropSeason.is_active.is_(True),
            ),
        )
        .where(User.telegram_id == telegram_id)
        .limit(1)
    )
    row = result.one_or_none()
    return None if row is None else _context_from_row(row)


async def _locked_active_profile(
    session: AsyncSession,
    telegram_id: int,
) -> tuple[User, Field, CropSeason]:
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
    return user, field, season


async def set_season_date_with_basis(
    session: AsyncSession,
    telegram_id: int,
    value: date,
    date_basis: str,
) -> CropPhenologyContext:
    """Store one explicit calculation start and the meaning of that date."""

    basis = validate_date_basis(date_basis)
    _, _, season = await _locked_active_profile(session, telegram_id)
    season.season_start_date = value
    season.sowing_date = value if basis == "sowing" else None
    season.date_basis = basis

    # A changed origin date can make an old stage label misleading. Require a
    # fresh field observation instead of carrying it across silently.
    season.phenological_phase = None
    season.phase_source = None
    season.phase_confidence = None
    season.phase_confirmed_at = None
    season.phase_observation_note = None
    season.updated_at = datetime.utcnow()
    await session.commit()

    context = await get_active_crop_phenology(session, telegram_id)
    if context is None:
        raise RuntimeError("Профиль культуры исчез после сохранения даты.")
    return context


async def set_growth_context(
    session: AsyncSession,
    telegram_id: int,
    *,
    production_system: str | None = None,
    plant_type: str | None = None,
) -> CropPhenologyContext:
    _, _, season = await _locked_active_profile(session, telegram_id)
    if production_system is not None:
        season.production_system = validate_production_system(production_system)
    if plant_type is not None:
        season.plant_type = validate_plant_type(plant_type)
    if season.crop_key != "tomato":
        season.plant_type = "unknown"
    season.updated_at = datetime.utcnow()
    await session.commit()

    context = await get_active_crop_phenology(session, telegram_id)
    if context is None:
        raise RuntimeError("Профиль культуры исчез после сохранения условий.")
    return context


async def set_observed_phase(
    session: AsyncSession,
    telegram_id: int,
    phase: str,
    *,
    note: str | None = None,
    confirmed_at: datetime | None = None,
) -> CropPhenologyContext:
    _, _, season = await _locked_active_profile(session, telegram_id)
    if phase not in get_crop_phases(season.crop_key):
        raise ValueError("Стадия не входит в справочник выбранной культуры.")

    cleaned_note = None if note is None else note.strip()
    if cleaned_note and len(cleaned_note) > 500:
        raise ValueError("Примечание к стадии должно быть не длиннее 500 знаков.")

    timestamp = confirmed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    season.phenological_phase = phase
    season.phase_source = "user"
    season.phase_confidence = None
    season.phase_confirmed_at = timestamp.astimezone(timezone.utc)
    season.phase_observation_note = cleaned_note or None
    season.updated_at = datetime.utcnow()
    await session.commit()

    context = await get_active_crop_phenology(session, telegram_id)
    if context is None:
        raise RuntimeError("Профиль культуры исчез после сохранения стадии.")
    return context


async def clear_observed_phase(
    session: AsyncSession,
    telegram_id: int,
) -> CropPhenologyContext:
    _, _, season = await _locked_active_profile(session, telegram_id)
    season.phenological_phase = None
    season.phase_source = None
    season.phase_confidence = None
    season.phase_confirmed_at = None
    season.phase_observation_note = None
    season.updated_at = datetime.utcnow()
    await session.commit()

    context = await get_active_crop_phenology(session, telegram_id)
    if context is None:
        raise RuntimeError("Профиль культуры исчез после удаления стадии.")
    return context
