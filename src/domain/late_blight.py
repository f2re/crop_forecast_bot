from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

HUTTON_MINIMUM_TEMPERATURE_C = 10.0
HUTTON_RELATIVE_HUMIDITY_PERCENT = 90.0
HUTTON_HUMID_HOURS = 6

# These are deliberately conservative diagnostics of near-saturated 2 m air.
# They are not pathogen thresholds and never create an alert by themselves.
NEAR_SATURATION_RELATIVE_HUMIDITY_PERCENT = 95.0
NEAR_SATURATION_DEWPOINT_DEPRESSION_C = 1.0
FOG_VISIBILITY_METERS = 1000.0
FOG_WMO_CODES = frozenset({45, 48})

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
class LateBlightNightMoistureAssessment:
    """Supporting evidence for nocturnal condensation in open-field weather.

    ``night_date`` is the local morning on which the night ends. The assessment
    describes model-grid air at 2 m and visibility; it is not a measurement of
    dew or leaf wetness inside the potato canopy.
    """

    night_date: date
    data_kind: LateBlightDataKind
    start_local: datetime
    end_local: datetime
    night_hours: int
    valid_temperature_humidity_hours: int
    preceding_day_maximum_temperature_c: float | None
    night_minimum_temperature_c: float | None
    day_to_night_drop_c: float | None
    maximum_relative_humidity_percent: float | None
    minimum_dewpoint_depression_c: float | None
    near_saturation_hours: int
    fog_hours: int
    precipitation_hours: int
    optional_moisture_data_available: bool


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
    night_moisture: tuple[LateBlightNightMoistureAssessment, ...] = ()


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
    required = ("date", "temperature_2m", "relative_humidity_2m")
    missing = set(required).difference(frame.columns)
    if missing:
        raise ValueError(
            "Для критериев Hutton не хватает столбцов: "
            + ", ".join(sorted(missing))
        )

    optional = (
        "dew_point_2m",
        "precipitation",
        "weather_code",
        "visibility",
        "is_day",
    )
    prepared = frame[list(required)].copy()
    for column in optional:
        prepared[column] = frame[column] if column in frame.columns else pd.NA

    prepared["date"] = pd.to_datetime(prepared["date"], utc=True, errors="coerce")
    for column in (
        "temperature_2m",
        "relative_humidity_2m",
        "dew_point_2m",
        "precipitation",
        "weather_code",
        "visibility",
        "is_day",
    ):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    prepared.loc[
        ~prepared["temperature_2m"].between(-80.0, 60.0),
        "temperature_2m",
    ] = pd.NA
    prepared.loc[
        ~prepared["relative_humidity_2m"].between(0.0, 100.0),
        "relative_humidity_2m",
    ] = pd.NA
    prepared.loc[
        ~prepared["dew_point_2m"].between(-100.0, 60.0),
        "dew_point_2m",
    ] = pd.NA
    prepared.loc[prepared["precipitation"] < 0.0, "precipitation"] = pd.NA
    prepared.loc[
        ~prepared["weather_code"].between(0.0, 99.0),
        "weather_code",
    ] = pd.NA
    prepared.loc[prepared["visibility"] < 0.0, "visibility"] = pd.NA
    prepared.loc[~prepared["is_day"].isin((0.0, 1.0)), "is_day"] = pd.NA

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


def _optional_moisture_available(group: pd.DataFrame) -> bool:
    return any(
        group[column].notna().any()
        for column in (
            "dew_point_2m",
            "precipitation",
            "weather_code",
            "visibility",
        )
    )


def _night_moisture_assessments(
    frame: pd.DataFrame,
    *,
    zone: ZoneInfo,
    today: date,
) -> tuple[LateBlightNightMoistureAssessment, ...]:
    if frame["is_day"].notna().sum() == 0:
        return ()

    prepared = frame.copy()
    prepared["local_datetime"] = prepared["date"].dt.tz_convert(zone)
    prepared["local_date"] = prepared["local_datetime"].dt.date
    prepared["local_hour"] = prepared["local_datetime"].dt.hour

    night = prepared[prepared["is_day"] == 0.0].copy()
    if night.empty:
        return ()

    # Evening hours belong to the following morning. This joins sunset-to-24:00
    # with 00:00-to-sunrise into one local night without a fixed clock window.
    night["night_date"] = [
        local_day + timedelta(days=1) if hour >= 12 else local_day
        for local_day, hour in zip(
            night["local_date"],
            night["local_hour"],
            strict=True,
        )
    ]

    assessments: list[LateBlightNightMoistureAssessment] = []
    for night_date, group in night.groupby("night_date", sort=True):
        group = group.sort_values("date")
        valid = group.dropna(
            subset=["temperature_2m", "relative_humidity_2m"]
        )
        night_minimum = (
            None if valid.empty else float(valid["temperature_2m"].min())
        )
        maximum_humidity = (
            None
            if valid.empty
            else float(valid["relative_humidity_2m"].max())
        )

        preceding_day = night_date - timedelta(days=1)
        daylight = prepared[
            (prepared["local_date"] == preceding_day)
            & (prepared["is_day"] == 1.0)
        ].dropna(subset=["temperature_2m"])
        preceding_maximum = (
            None
            if daylight.empty
            else float(daylight["temperature_2m"].max())
        )
        temperature_drop = (
            None
            if preceding_maximum is None or night_minimum is None
            else max(0.0, preceding_maximum - night_minimum)
        )

        dew_valid = group.dropna(
            subset=[
                "temperature_2m",
                "relative_humidity_2m",
                "dew_point_2m",
            ]
        ).copy()
        if dew_valid.empty:
            minimum_depression = None
            near_saturation_hours = 0
        else:
            dew_valid["dewpoint_depression"] = (
                dew_valid["temperature_2m"] - dew_valid["dew_point_2m"]
            ).clip(lower=0.0)
            minimum_depression = float(dew_valid["dewpoint_depression"].min())
            near_saturation_hours = int(
                (
                    (
                        dew_valid["relative_humidity_2m"]
                        >= NEAR_SATURATION_RELATIVE_HUMIDITY_PERCENT
                    )
                    & (
                        dew_valid["dewpoint_depression"]
                        <= NEAR_SATURATION_DEWPOINT_DEPRESSION_C
                    )
                ).sum()
            )

        fog_from_code = group["weather_code"].isin(FOG_WMO_CODES)
        fog_from_visibility = group["visibility"].lt(FOG_VISIBILITY_METERS)
        fog_hours = int((fog_from_code | fog_from_visibility).sum())
        precipitation_hours = int(group["precipitation"].gt(0.0).sum())

        start_local = group["local_datetime"].iloc[0].to_pydatetime()
        end_local = (
            group["local_datetime"].iloc[-1] + pd.Timedelta(hours=1)
        ).to_pydatetime()
        assessments.append(
            LateBlightNightMoistureAssessment(
                night_date=night_date,
                data_kind=(
                    "model_completed" if night_date < today else "forecast"
                ),
                start_local=start_local,
                end_local=end_local,
                night_hours=int(len(group)),
                valid_temperature_humidity_hours=int(len(valid)),
                preceding_day_maximum_temperature_c=preceding_maximum,
                night_minimum_temperature_c=night_minimum,
                day_to_night_drop_c=temperature_drop,
                maximum_relative_humidity_percent=maximum_humidity,
                minimum_dewpoint_depression_c=minimum_depression,
                near_saturation_hours=near_saturation_hours,
                fog_hours=fog_hours,
                precipitation_hours=precipitation_hours,
                optional_moisture_data_available=_optional_moisture_available(group),
            )
        )
    return tuple(assessments)


def calculate_hutton_outlook(
    weather: LateBlightWeatherData,
    *,
    today: date,
) -> LateBlightOutlook:
    """Evaluate Hutton and describe, but do not score, nocturnal wetness context.

    Hutton remains the only alert trigger: two consecutive local days, each with
    minimum temperature at least 10 °C and six or more hourly RH values at or
    above 90%. A large day-to-night temperature drop is not a criterion by
    itself. Dew-point proximity, fog, visibility and precipitation are reported
    only as supporting evidence of possible nocturnal moisture.
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
    night_moisture = _night_moisture_assessments(
        frame,
        zone=zone,
        today=today,
    )
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
        night_moisture=night_moisture,
    )
