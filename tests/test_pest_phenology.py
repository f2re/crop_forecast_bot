from datetime import date, timedelta

import pandas as pd
import pytest

from src.agro.pest_phenology import (
    calculate_pest_outlook,
    choose_pest_notification,
    daily_average_degree_days,
    single_sine_horizontal_degree_days,
)
from src.domain.pests import (
    automatic_biofix_date,
    get_pest_model,
    stage_for_accumulation,
    supported_pests_for_crop,
    validate_pest_for_crop,
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


def test_single_sine_horizontal_cutoff_matches_method_boundaries() -> None:
    assert single_sine_horizontal_degree_days(
        0.0,
        3.0,
        lower_threshold_c=3.9,
        upper_threshold_c=29.0,
    ) == 0.0
    assert single_sine_horizontal_degree_days(
        3.9,
        29.0,
        lower_threshold_c=3.9,
        upper_threshold_c=29.0,
    ) == pytest.approx(12.55)
    assert single_sine_horizontal_degree_days(
        29.0,
        35.0,
        lower_threshold_c=3.9,
        upper_threshold_c=29.0,
    ) == pytest.approx(25.1)
    assert single_sine_horizontal_degree_days(
        0.0,
        40.0,
        lower_threshold_c=3.9,
        upper_threshold_c=29.0,
    ) == pytest.approx(14.0997, abs=1e-4)


def test_pest_catalog_is_strictly_bound_to_supported_crops() -> None:
    assert {model.key for model in supported_pests_for_crop("potato")} == {
        "colorado_potato_beetle"
    }
    assert {model.key for model in supported_pests_for_crop("corn")} == {
        "black_cutworm",
        "seedcorn_maggot_soil",
    }
    assert {model.key for model in supported_pests_for_crop("soy")} == {
        "seedcorn_maggot_soil"
    }
    assert supported_pests_for_crop("tomato") == ()
    with pytest.raises(ValueError, match="не применяется"):
        validate_pest_for_crop("black_cutworm", "tomato")
    with pytest.raises(ValueError, match="не применяется"):
        validate_pest_for_crop("seedcorn_maggot_soil", "onion")


def test_black_cutworm_windows_use_converted_published_thresholds() -> None:
    model = get_pest_model("black_cutworm")
    assert model.temperature_driver == "air_2m"
    assert model.lower_threshold_c == pytest.approx(10.0)
    assert stage_for_accumulation(model, 49.9).key == "eggs"
    assert stage_for_accumulation(model, 50.0).key == "larvae_1_3"
    assert stage_for_accumulation(model, 173.3).key == "larva_4"
    assert stage_for_accumulation(model, 202.8).key == "larva_5"
    assert stage_for_accumulation(model, 356.1).key == "pupae"


def test_seedcorn_maggot_uses_soil_driver_and_calendar_start() -> None:
    model = get_pest_model("seedcorn_maggot_soil")
    assert model.temperature_driver == "soil_0_to_7cm"
    assert model.calculation_method == "single_sine_horizontal"
    assert model.lower_threshold_c == pytest.approx(3.9)
    assert model.upper_threshold_c == pytest.approx(29.0)
    assert automatic_biofix_date(model, date(2026, 8, 3)) == date(2026, 1, 1)
    assert stage_for_accumulation(model, 205.9).key == "overwintering_pupae"
    assert stage_for_accumulation(model, 206.0).key == "spring_emergence"


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


def test_soil_model_uses_single_sine_and_reaches_emergence_window() -> None:
    biofix = date(2026, 1, 1)
    today = date(2026, 1, 16)
    frame = _weather_rows(
        biofix,
        [(29.0, 35.0, "reanalysis")] * 15
        + [(29.0, 35.0, "forecast")],
    )
    outlook = calculate_pest_outlook(
        frame,
        "seedcorn_maggot_soil",
        biofix_date=biofix,
        today=today,
    )
    assert outlook.available is True
    assert outlook.accumulated_dd_c == pytest.approx(376.5)
    assert outlook.current_stage is not None
    assert outlook.current_stage.key == "spring_emergence"


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
