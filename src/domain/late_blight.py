from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

HUTTON_MINIMUM_TEMPERATURE_C = 10.0
HUTTON_RELATIVE_HUMIDITY_PERCENT = 90.0
HUTTON_HUMID_HOURS = 6

LateBlightDataKind = Literal["model_completed", "forecast"]
LateBlightPeriodKind = Literal["model_completed", "forecast", "mixed"]


@dataclass(frozen=True, slots=True)
class LateBlightWeatherMeta:
    latitude: float
    longitude: float
    elevation_m: float | None
    timezone: str
    source: str
    model: str
    retrieved_at: datetime
    cache_ttl_seconds: int


@dataclass(slots=True)
class LateBlightWeatherData:
    meta: LateBlightWeatherMeta
    hourly: pd.DataFrame


@dataclass(frozen=True, slots=True)
class LateBlightDayAssessment:
    local_date: date
    data_kind: LateBlightDataKind
    expected_hours: int
    valid_hours: int
    minimum_temperature_c: float | None
    humid_hours: int
    complete: bool
    qualifies: bool


@dataclass(frozen=True, slots=True)
class LateBlightPeriod:
    start_date: date
    end_date: date
    day_count: int
    data_kind: LateBlightPeriodKind


@dataclass(frozen=True, slots=True)
class LateBlightOutlook:
    available: bool
    status: str
    criteria_name: str
    days: tuple[LateBlightDayAssessment, ...]
    periods: tuple[LateBlightPeriod, ...]
    timezone: str
    source: str
    model: str
    retrieved_at: datetime


def _zone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Неизвестный часовой пояс: {timezone_name}") from exc


def _expected_hours(local_day: date, zone: ZoneInfo) -> int:
    start = datetime.combine(local_day, time.min, tzinfo=zone)
    end = datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=zone)
    seconds = (
        end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
    ).total_seconds()
    return int(seconds // 3600)


def _prepare_hourly(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "temperature_2m", "relative_humidity_2m"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "Для критериев Hutton не хватает столбцов: "
            + ", ".join(sorted(missing))
        )

    prepared = frame[list(required)].copy()
    prepared["date"] = pd.to_datetime(prepared["date"], utc=True, errors="coerce")
    prepared["temperature_2m"] = pd.to_numeric(
        prepared["temperature_2m"], errors="coerce"
    )
    prepared["relative_humidity_2m"] = pd.to_numeric(
        prepared["relative_humidity_2m"], errors="coerce"
    )
    prepared.loc[
        ~prepared["temperature_2m"].between(-80.0, 60.0),
        "temperature_2m",
    ] = pd.NA
    prepared.loc[
        ~prepared["relative_humidity_2m"].between(0.0, 100.0),
        "relative_humidity_2m",
    ] = pd.NA
    prepared = prepared.dropna(subset=["date"])
    prepared = prepared.sort_values("date").drop_duplicates("date", keep="last")
    return prepared


def _period_kind(
    days: list[LateBlightDayAssessment],
) -> LateBlightPeriodKind:
    kinds = {day.data_kind for day in days}
    if kinds == {"model_completed"}:
        return "model_completed"
    if kinds == {"forecast"}:
        return "forecast"
    return "mixed"


def _periods(
    days: tuple[LateBlightDayAssessment, ...],
) -> tuple[LateBlightPeriod, ...]:
    runs: list[list[LateBlightDayAssessment]] = []
    current: list[LateBlightDayAssessment] = []
    for day in days:
        if not day.qualifies:
            if current:
                runs.append(current)
                current = []
            continue
        if current and (day.local_date - current[-1].local_date).days > 1:
            runs.append(current)
            current = []
        current.append(day)
    if current:
        runs.append(current)

    return tuple(
        LateBlightPeriod(
            start_date=run[0].local_date,
            end_date=run[-1].local_date,
            day_count=len(run),
            data_kind=_period_kind(run),
        )
        for run in runs
        if len(run) >= 2
    )


def calculate_hutton_outlook(
    weather: LateBlightWeatherData,
    *,
    today: date,
) -> LateBlightOutlook:
    """Evaluate the published Hutton weather criteria for potato late blight.

    The criteria are a weather suitability screen: two consecutive local days,
    each with a minimum temperature of at least 10 °C and at least six hourly
    values with relative humidity at or above 90%. The result does not establish
    that inoculum is present or that infection occurred.
    """

    zone = _zone(weather.meta.timezone)
    frame = _prepare_hourly(weather.hourly)
    if frame.empty:
        return LateBlightOutlook(
            available=False,
            status="почасовой ряд отсутствует",
            criteria_name="Hutton Criteria",
            days=(),
            periods=(),
            timezone=weather.meta.timezone,
            source=weather.meta.source,
            model=weather.meta.model,
            retrieved_at=weather.meta.retrieved_at,
        )

    frame["local_date"] = frame["date"].dt.tz_convert(zone).dt.date
    assessments: list[LateBlightDayAssessment] = []
    for local_day, group in frame.groupby("local_date", sort=True):
        expected = _expected_hours(local_day, zone)
        valid = group.dropna(
            subset=["temperature_2m", "relative_humidity_2m"]
        )
        valid_hours = int(len(valid))
        complete = valid_hours == expected
        minimum = (
            None
            if valid.empty
            else float(valid["temperature_2m"].min())
        )
        humid_hours = int(
            (valid["relative_humidity_2m"] >= HUTTON_RELATIVE_HUMIDITY_PERCENT).sum()
        )
        qualifies = bool(
            complete
            and minimum is not None
            and minimum >= HUTTON_MINIMUM_TEMPERATURE_C
            and humid_hours >= HUTTON_HUMID_HOURS
        )
        assessments.append(
            LateBlightDayAssessment(
                local_date=local_day,
                data_kind=(
                    "model_completed" if local_day < today else "forecast"
                ),
                expected_hours=expected,
                valid_hours=valid_hours,
                minimum_temperature_c=minimum,
                humid_hours=humid_hours,
                complete=complete,
                qualifies=qualifies,
            )
        )

    days = tuple(assessments)
    complete_days = tuple(day for day in days if day.complete)
    periods = _periods(days)
    if len(complete_days) < 2:
        status = "недостаточно двух полных последовательных местных суток"
        available = False
    elif periods:
        status = "критерии Hutton выполнены"
        available = True
    elif any(day.qualifies for day in complete_days):
        status = "порог выполнен только за отдельные сутки"
        available = True
    else:
        status = "критерии Hutton не выполнены"
        available = True

    return LateBlightOutlook(
        available=available,
        status=status,
        criteria_name="Hutton Criteria",
        days=days,
        periods=periods,
        timezone=weather.meta.timezone,
        source=weather.meta.source,
        model=weather.meta.model,
        retrieved_at=weather.meta.retrieved_at,
    )
