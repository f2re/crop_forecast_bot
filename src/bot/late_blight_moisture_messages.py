from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Protocol

from src.domain.late_blight import (
    LateBlightNightMoistureAssessment,
    LateBlightOutlook,
)


class PeriodLike(Protocol):
    start_date: date
    end_date: date


def _night_label(night_date: date) -> str:
    evening = night_date - timedelta(days=1)
    if evening.month == night_date.month:
        return f"{evening:%d}→{night_date:%d.%m}"
    return f"{evening:%d.%m}→{night_date:%d.%m}"


def _matches_periods(
    night: LateBlightNightMoistureAssessment,
    periods: Sequence[PeriodLike],
) -> bool:
    return any(
        period.start_date <= night.night_date <= period.end_date
        for period in periods
    )


def relevant_night_moisture(
    outlook: LateBlightOutlook,
    *,
    periods: Sequence[PeriodLike] | None = None,
    max_items: int = 3,
) -> tuple[LateBlightNightMoistureAssessment, ...]:
    if max_items < 1:
        return ()
    candidates = list(outlook.night_moisture)
    selected_periods = tuple(periods or outlook.periods)
    if selected_periods:
        matched = [
            night
            for night in candidates
            if _matches_periods(night, selected_periods)
        ]
        if matched:
            return tuple(matched[:max_items])

    forecast = [night for night in candidates if night.data_kind == "forecast"]
    if forecast:
        return tuple(forecast[:max_items])
    return tuple(candidates[-max_items:])


def _night_parts(night: LateBlightNightMoistureAssessment) -> list[str]:
    parts: list[str] = []
    if night.day_to_night_drop_c is not None:
        parts.append(f"падение T {night.day_to_night_drop_c:.1f} °C")
    if night.near_saturation_hours:
        parts.append(
            f"воздух почти насыщен {night.near_saturation_hours} ч"
        )
    if night.fog_hours:
        parts.append(
            f"туман/видимость <1 км {night.fog_hours} ч"
        )
    if night.precipitation_hours:
        parts.append(f"осадки {night.precipitation_hours} ч")
    if (
        night.minimum_dewpoint_depression_c is not None
        and night.near_saturation_hours == 0
    ):
        parts.append(
            f"мин. T−Td {night.minimum_dewpoint_depression_c:.1f} °C"
        )
    if not parts:
        if night.optional_moisture_data_available:
            parts.append("явных признаков насыщения воздуха нет")
        else:
            parts.append("дополнительные поля влаги недоступны")
    return parts


def format_night_moisture_section(
    outlook: LateBlightOutlook,
    *,
    max_items: int = 3,
) -> list[str]:
    nights = relevant_night_moisture(outlook, max_items=max_items)
    if not nights:
        return []
    lines = ["", "🌫 <b>Ночное увлажнение — поясняющий контекст</b>"]
    for night in nights:
        lines.append(
            f"• {_night_label(night.night_date)}: "
            + "; ".join(_night_parts(night))
            + "."
        )
    lines.extend(
        [
            "Резкий перепад температуры сам по себе не является триггером. "
            "Он важен только как возможная причина насыщения воздуха, росы или "
            "тумана.",
            "Это модельные признаки на высоте 2 м, а не измерение воды на "
            "листьях внутри ботвы; они не меняют пороги Hutton и не создают "
            "отдельное уведомление.",
        ]
    )
    return lines


def format_compact_night_moisture(
    outlook: LateBlightOutlook,
    *,
    periods: Sequence[PeriodLike],
) -> str | None:
    nights = relevant_night_moisture(
        outlook,
        periods=periods,
        max_items=4,
    )
    if not nights:
        return None

    parts: list[str] = []
    maximum_saturation = max(night.near_saturation_hours for night in nights)
    fog_nights = sum(1 for night in nights if night.fog_hours > 0)
    precipitation_nights = sum(
        1 for night in nights if night.precipitation_hours > 0
    )
    drops = [
        night.day_to_night_drop_c
        for night in nights
        if night.day_to_night_drop_c is not None
    ]
    if maximum_saturation:
        parts.append(f"почти насыщенный воздух до {maximum_saturation} ч/ночь")
    if fog_nights:
        parts.append(f"туман или видимость <1 км в {fog_nights} ноч.")
    if precipitation_nights:
        parts.append(f"осадки в {precipitation_nights} ноч.")
    if drops:
        parts.append(f"падение T до {max(drops):.1f} °C")
    if not parts:
        return None
    return (
        "🌫 Ночной контекст: "
        + "; ".join(parts)
        + ". Это пояснение, не отдельный триггер."
    )
