from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from src.domain.late_blight import (
    LateBlightWeatherData,
    LateBlightWeatherMeta,
    calculate_hutton_outlook,
)


def _hourly_days(
    start_day: date,
    *,
    days: int = 2,
    daytime_temperature_c: float = 24.0,
    nighttime_temperature_c: float = 11.0,
    nighttime_humidity_percent: float = 97.0,
    nighttime_dew_point_c: float = 10.4,
) -> pd.DataFrame:
    zone = ZoneInfo("Europe/Moscow")
    start_local = datetime.combine(start_day, datetime.min.time(), tzinfo=zone)
    end_local = start_local + timedelta(days=days)
    timestamps = pd.date_range(
        start=start_local.astimezone(timezone.utc),
        end=end_local.astimezone(timezone.utc),
        freq="1h",
        inclusive="left",
    )
    local = timestamps.tz_convert(zone)
    is_day = [1 if 7 <= timestamp.hour < 19 else 0 for timestamp in local]
    temperature = [
        daytime_temperature_c if day_flag else nighttime_temperature_c
        for day_flag in is_day
    ]
    humidity = [
        65.0 if day_flag else nighttime_humidity_percent
        for day_flag in is_day
    ]
    dew_point = [
        12.0 if day_flag else nighttime_dew_point_c
        for day_flag in is_day
    ]
    weather_code = [0] * len(timestamps)
    visibility = [20_000.0] * len(timestamps)
    precipitation = [0.0] * len(timestamps)

    for index, timestamp in enumerate(local):
        if timestamp.date() == start_day + timedelta(days=1) and timestamp.hour in {3, 4}:
            weather_code[index] = 45
            visibility[index] = 600.0
        if timestamp.date() == start_day + timedelta(days=1) and timestamp.hour == 5:
            precipitation[index] = 0.4

    return pd.DataFrame(
        {
            "date": timestamps,
            "temperature_2m": temperature,
            "relative_humidity_2m": humidity,
            "dew_point_2m": dew_point,
            "precipitation": precipitation,
            "weather_code": weather_code,
            "visibility": visibility,
            "is_day": is_day,
        }
    )


def _weather(frame: pd.DataFrame) -> LateBlightWeatherData:
    return LateBlightWeatherData(
        meta=LateBlightWeatherMeta(
            latitude=55.75,
            longitude=37.62,
            elevation_m=150.0,
            timezone="Europe/Moscow",
            source="test",
            model="test-model",
            retrieved_at=datetime(2026, 8, 3, 12, tzinfo=timezone.utc),
            cache_ttl_seconds=3600,
        ),
        hourly=frame,
    )


def test_night_context_describes_temperature_drop_saturation_fog_and_rain() -> None:
    frame = _hourly_days(date(2026, 8, 4))

    outlook = calculate_hutton_outlook(
        _weather(frame),
        today=date(2026, 8, 4),
    )

    night = next(
        item
        for item in outlook.night_moisture
        if item.night_date == date(2026, 8, 5)
    )
    assert night.preceding_day_maximum_temperature_c == 24.0
    assert night.night_minimum_temperature_c == 11.0
    assert night.day_to_night_drop_c == 13.0
    assert night.maximum_relative_humidity_percent == 97.0
    assert night.minimum_dewpoint_depression_c == 0.6
    assert night.near_saturation_hours >= 10
    assert night.fog_hours == 2
    assert night.precipitation_hours == 1
    assert night.optional_moisture_data_available is True


def test_large_temperature_drop_does_not_trigger_hutton_in_dry_air() -> None:
    frame = _hourly_days(
        date(2026, 8, 4),
        daytime_temperature_c=30.0,
        nighttime_temperature_c=10.5,
        nighttime_humidity_percent=65.0,
        nighttime_dew_point_c=3.0,
    )

    outlook = calculate_hutton_outlook(
        _weather(frame),
        today=date(2026, 8, 4),
    )

    assert outlook.periods == ()
    assert all(day.qualifies is False for day in outlook.days)
    night = next(
        item
        for item in outlook.night_moisture
        if item.night_date == date(2026, 8, 5)
    )
    assert night.day_to_night_drop_c == 19.5
    assert night.near_saturation_hours == 0


def test_missing_optional_fields_preserve_hutton_and_hide_night_context() -> None:
    frame = _hourly_days(date(2026, 8, 4)).drop(
        columns=[
            "dew_point_2m",
            "precipitation",
            "weather_code",
            "visibility",
            "is_day",
        ]
    )

    outlook = calculate_hutton_outlook(
        _weather(frame),
        today=date(2026, 8, 4),
    )

    assert len(outlook.days) == 2
    assert len(outlook.periods) == 1
    assert outlook.night_moisture == ()
