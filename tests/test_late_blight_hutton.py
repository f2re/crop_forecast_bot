from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from src.domain.late_blight import (
    LateBlightWeatherData,
    LateBlightWeatherMeta,
    calculate_hutton_outlook,
)


def _day_rows(
    local_day: date,
    *,
    timezone_name: str = "Europe/Moscow",
    minimum_temperature_c: float = 12.0,
    humid_hours: int = 6,
) -> pd.DataFrame:
    zone = ZoneInfo(timezone_name)
    start_local = datetime.combine(local_day, time.min, tzinfo=zone)
    end_local = datetime.combine(
        local_day.replace(day=local_day.day) + pd.Timedelta(days=1),
        time.min,
        tzinfo=zone,
    )
    times = pd.date_range(
        start=start_local.astimezone(timezone.utc),
        end=end_local.astimezone(timezone.utc),
        freq="1h",
        inclusive="left",
    )
    return pd.DataFrame(
        {
            "date": times,
            "temperature_2m": [minimum_temperature_c] * len(times),
            "relative_humidity_2m": [95.0] * min(humid_hours, len(times))
            + [80.0] * max(0, len(times) - humid_hours),
        }
    )


def _weather(
    frame: pd.DataFrame,
    *,
    timezone_name: str = "Europe/Moscow",
) -> LateBlightWeatherData:
    return LateBlightWeatherData(
        meta=LateBlightWeatherMeta(
            latitude=55.75,
            longitude=37.62,
            elevation_m=150.0,
            timezone=timezone_name,
            source="test",
            model="test-model",
            retrieved_at=datetime(2026, 8, 3, 12, tzinfo=timezone.utc),
            cache_ttl_seconds=3600,
        ),
        hourly=frame,
    )


def test_two_consecutive_qualifying_days_form_hutton_period() -> None:
    frame = pd.concat(
        [
            _day_rows(date(2026, 7, 20)),
            _day_rows(date(2026, 7, 21), humid_hours=8),
        ],
        ignore_index=True,
    )

    outlook = calculate_hutton_outlook(
        _weather(frame),
        today=date(2026, 7, 22),
    )

    assert outlook.available is True
    assert outlook.status == "критерии Hutton выполнены"
    assert len(outlook.periods) == 1
    assert outlook.periods[0].start_date == date(2026, 7, 20)
    assert outlook.periods[0].end_date == date(2026, 7, 21)
    assert outlook.periods[0].day_count == 2
    assert outlook.periods[0].data_kind == "model_completed"


def test_isolated_qualifying_day_is_not_hutton_period() -> None:
    frame = pd.concat(
        [
            _day_rows(date(2026, 7, 20), humid_hours=6),
            _day_rows(date(2026, 7, 21), humid_hours=5),
            _day_rows(date(2026, 7, 22), humid_hours=7),
        ],
        ignore_index=True,
    )

    outlook = calculate_hutton_outlook(
        _weather(frame),
        today=date(2026, 7, 23),
    )

    assert outlook.available is True
    assert outlook.periods == ()
    assert sum(day.qualifies for day in outlook.days) == 2
    assert outlook.status == "порог выполнен только за отдельные сутки"


def test_missing_hour_is_fail_closed() -> None:
    first = _day_rows(date(2026, 7, 20))
    second = _day_rows(date(2026, 7, 21)).drop(index=[3])
    frame = pd.concat([first, second], ignore_index=True)

    outlook = calculate_hutton_outlook(
        _weather(frame),
        today=date(2026, 7, 22),
    )

    second_day = next(day for day in outlook.days if day.local_date == date(2026, 7, 21))
    assert second_day.expected_hours == 24
    assert second_day.valid_hours == 23
    assert second_day.complete is False
    assert second_day.qualifies is False
    assert outlook.periods == ()


def test_minimum_temperature_threshold_is_inclusive() -> None:
    frame = pd.concat(
        [
            _day_rows(date(2026, 7, 20), minimum_temperature_c=10.0),
            _day_rows(date(2026, 7, 21), minimum_temperature_c=9.9),
        ],
        ignore_index=True,
    )

    outlook = calculate_hutton_outlook(
        _weather(frame),
        today=date(2026, 7, 22),
    )

    assert outlook.days[0].qualifies is True
    assert outlook.days[1].qualifies is False
    assert outlook.periods == ()


def test_dst_fall_day_requires_25_hourly_values() -> None:
    frame = _day_rows(
        date(2026, 10, 25),
        timezone_name="Europe/Berlin",
        humid_hours=6,
    )

    outlook = calculate_hutton_outlook(
        _weather(frame, timezone_name="Europe/Berlin"),
        today=date(2026, 10, 26),
    )

    assert len(outlook.days) == 1
    assert outlook.days[0].expected_hours == 25
    assert outlook.days[0].valid_hours == 25
    assert outlook.days[0].complete is True
    assert outlook.days[0].qualifies is True
    assert outlook.available is False
    assert "двух полных" in outlook.status


def test_out_of_range_humidity_becomes_missing_data() -> None:
    frame = _day_rows(date(2026, 7, 20), humid_hours=6)
    frame.loc[0, "relative_humidity_2m"] = 120.0

    outlook = calculate_hutton_outlook(
        _weather(frame),
        today=date(2026, 7, 21),
    )

    assert outlook.days[0].valid_hours == 23
    assert outlook.days[0].complete is False
    assert outlook.days[0].qualifies is False
