from datetime import date, timedelta

import pandas as pd
import pytest

from src.agro.pest_phenology import (
    calculate_pest_outlook,
    choose_pest_notification,
    daily_average_degree_days,
)


def _weather_rows(
    start: date,
    values: list[tuple[float, float, str]],
) -> pd.DataFrame:
    rows = []
    for offset, (t_min, t_max, kind) in enumerate(values):
        day = start + timedelta(days=offset)
        rows.append(
            {
                "date": pd.Timestamp(day, tz="UTC"),
                "local_date": day.isoformat(),
                "t_min": t_min,
                "t_max": t_max,
                "data_kind": kind,
                "data_source": "test",
            }
        )
    return pd.DataFrame(rows)


def test_daily_average_degree_days_is_transparent() -> None:
    assert daily_average_degree_days(
        10.0,
        30.0,
        lower_threshold_c=11.1,
    ) == pytest.approx(8.9)
    assert daily_average_degree_days(
        0.0,
        10.0,
        lower_threshold_c=11.1,
    ) == 0.0
    assert daily_average_degree_days(
        10.0,
        40.0,
        lower_threshold_c=11.1,
        upper_threshold_c=25.0,
    ) == pytest.approx(13.9)


def test_pest_outlook_separates_completed_and_forecast_heat() -> None:
    biofix = date(2026, 6, 1)
    today = date(2026, 6, 5)
    frame = _weather_rows(
        biofix,
        [
            (11.1, 51.1, "reanalysis"),
            (11.1, 51.1, "reanalysis"),
            (11.1, 51.1, "operational_past"),
            (11.1, 51.1, "operational_past"),
            (11.1, 51.1, "current_forecast"),
            (11.1, 51.1, "forecast"),
            (11.1, 51.1, "forecast"),
        ],
    )

    outlook = calculate_pest_outlook(
        frame,
        "colorado_potato_beetle",
        biofix_date=biofix,
        today=today,
    )

    assert outlook.available is True
    assert outlook.accumulated_dd_c == pytest.approx(80.0)
    assert outlook.forecast_added_dd_c == pytest.approx(60.0)
    assert outlook.current_stage is not None
    assert outlook.current_stage.key == "eggs"
    assert outlook.next_stage is not None
    assert outlook.next_stage.key == "larva_1"
    assert outlook.projected_crossing_date == date(2026, 6, 6)
    assert outlook.completed_days == 4
    assert outlook.forecast_days == 3


def test_pest_outlook_is_hidden_when_completed_day_is_missing() -> None:
    biofix = date(2026, 6, 1)
    today = date(2026, 6, 5)
    frame = _weather_rows(
        biofix,
        [
            (10.0, 30.0, "reanalysis"),
            (10.0, 30.0, "reanalysis"),
            (10.0, 30.0, "operational_past"),
            (10.0, 30.0, "current_forecast"),
        ],
    )
    # Remove 3 June while retaining a later completed day.
    frame = frame.drop(index=2).copy()
    frame.loc[len(frame)] = {
        "date": pd.Timestamp(date(2026, 6, 4), tz="UTC"),
        "local_date": "2026-06-04",
        "t_min": 10.0,
        "t_max": 30.0,
        "data_kind": "operational_past",
        "data_source": "test",
    }

    outlook = calculate_pest_outlook(
        frame,
        "colorado_potato_beetle",
        biofix_date=biofix,
        today=today,
    )

    assert outlook.available is False
    assert outlook.missing_days == 1
    assert "пропущено 1 из 4 суток" in outlook.status


def test_pest_notifications_are_stage_and_advance_deduplicated() -> None:
    biofix = date(2026, 6, 1)
    today = date(2026, 6, 5)
    frame = _weather_rows(
        biofix,
        [
            (11.1, 51.1, "reanalysis"),
            (11.1, 51.1, "reanalysis"),
            (11.1, 51.1, "operational_past"),
            (11.1, 51.1, "operational_past"),
            (11.1, 51.1, "current_forecast"),
            (11.1, 51.1, "forecast"),
        ],
    )
    outlook = calculate_pest_outlook(
        frame,
        "colorado_potato_beetle",
        biofix_date=biofix,
        today=today,
    )

    current = choose_pest_notification(
        outlook,
        last_notified_stage=None,
        last_notified_advance=None,
        today=today,
    )
    assert current is not None
    assert current.kind == "current_window"
    assert current.stage.key == "eggs"

    advance = choose_pest_notification(
        outlook,
        last_notified_stage=current.event_key,
        last_notified_advance=None,
        today=today,
    )
    assert advance is not None
    assert advance.kind == "approaching_window"
    assert advance.stage.key == "larva_1"
    assert advance.expected_date == date(2026, 6, 6)

    assert (
        choose_pest_notification(
            outlook,
            last_notified_stage=current.event_key,
            last_notified_advance=advance.event_key,
            today=today,
        )
        is None
    )
