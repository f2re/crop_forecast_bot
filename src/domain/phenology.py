from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.agro.crop_catalog import get_crop_phases

DateBasis = Literal["sowing", "emergence", "transplanting", "season_start"]
ProductionSystem = Literal["open_field", "greenhouse", "unknown"]
PlantType = Literal["determinate", "indeterminate", "unknown"]

DATE_BASIS_LABELS: dict[DateBasis, str] = {
    "sowing": "посев",
    "emergence": "появление всходов",
    "transplanting": "высадка рассады",
    "season_start": "условное начало наблюдений",
}
PRODUCTION_SYSTEM_LABELS: dict[ProductionSystem, str] = {
    "open_field": "открытый грунт",
    "greenhouse": "защищённый грунт",
    "unknown": "не указано",
}
PLANT_TYPE_LABELS: dict[PlantType, str] = {
    "determinate": "детерминантный",
    "indeterminate": "индетерминантный",
    "unknown": "не указано",
}

# This is a user-interface reminder interval, not a biological stage threshold.
PHASE_REVIEW_INTERVAL_DAYS = 14


@dataclass(frozen=True, slots=True)
class StageReview:
    """Explain whether an old field observation should be checked again.

    The result is deliberately not a phenology forecast. It uses only the age
    of the last user-confirmed observation and the ordered list of stage labels.
    No stage is changed automatically and no probability is produced.
    """

    needs_review: bool
    status: str
    days_since_confirmation: int | None
    next_stage: str | None
    reminder_interval_days: int = PHASE_REVIEW_INTERVAL_DAYS


def validate_date_basis(value: str) -> DateBasis:
    if value not in DATE_BASIS_LABELS:
        raise ValueError("Неизвестный смысл даты.")
    return value  # type: ignore[return-value]


def validate_production_system(value: str) -> ProductionSystem:
    if value not in PRODUCTION_SYSTEM_LABELS:
        raise ValueError("Неизвестные условия выращивания.")
    return value  # type: ignore[return-value]


def validate_plant_type(value: str) -> PlantType:
    if value not in PLANT_TYPE_LABELS:
        raise ValueError("Неизвестный тип растения.")
    return value  # type: ignore[return-value]


def date_basis_label(value: str | None) -> str:
    if value is None:
        return "условное начало наблюдений"
    return DATE_BASIS_LABELS.get(value, "условное начало наблюдений")


def production_system_label(value: str | None) -> str:
    if value is None:
        return PRODUCTION_SYSTEM_LABELS["unknown"]
    return PRODUCTION_SYSTEM_LABELS.get(value, PRODUCTION_SYSTEM_LABELS["unknown"])


def plant_type_label(value: str | None) -> str:
    if value is None:
        return PLANT_TYPE_LABELS["unknown"]
    return PLANT_TYPE_LABELS.get(value, PLANT_TYPE_LABELS["unknown"])


def _local_confirmation_date(value: datetime, timezone_name: str) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return value.astimezone(zone).date()


def evaluate_stage_review(
    crop_key: str,
    *,
    current_phase: str | None,
    phase_confirmed_at: datetime | None,
    today: date,
    timezone_name: str,
    reminder_interval_days: int = PHASE_REVIEW_INTERVAL_DAYS,
) -> StageReview:
    """Return a review reminder without inferring a biological stage.

    ``reminder_interval_days`` is an operational prompt interval. It is not a
    crop-development parameter and must not be presented as a phase boundary.
    """

    if reminder_interval_days <= 0:
        raise ValueError("Интервал напоминания должен быть положительным.")

    if current_phase is None:
        return StageReview(
            needs_review=True,
            status="stage_missing",
            days_since_confirmation=None,
            next_stage=None,
            reminder_interval_days=reminder_interval_days,
        )

    phases = tuple(get_crop_phases(crop_key))
    try:
        phase_index = phases.index(current_phase)
    except ValueError:
        return StageReview(
            needs_review=True,
            status="stage_not_in_catalog",
            days_since_confirmation=None,
            next_stage=None,
            reminder_interval_days=reminder_interval_days,
        )

    next_stage = phases[phase_index + 1] if phase_index + 1 < len(phases) else None
    if phase_confirmed_at is None:
        return StageReview(
            needs_review=True,
            status="confirmation_time_unknown",
            days_since_confirmation=None,
            next_stage=next_stage,
            reminder_interval_days=reminder_interval_days,
        )

    confirmation_day = _local_confirmation_date(phase_confirmed_at, timezone_name)
    days_since = max(0, (today - confirmation_day).days)
    if days_since >= reminder_interval_days:
        return StageReview(
            needs_review=True,
            status="observation_stale" if next_stage else "terminal_stage_stale",
            days_since_confirmation=days_since,
            next_stage=next_stage,
            reminder_interval_days=reminder_interval_days,
        )

    return StageReview(
        needs_review=False,
        status="observation_recent",
        days_since_confirmation=days_since,
        next_stage=next_stage,
        reminder_interval_days=reminder_interval_days,
    )
