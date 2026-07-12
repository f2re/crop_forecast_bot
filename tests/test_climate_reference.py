from datetime import date

import pandas as pd

from src.agro.climate_reference import calc_season_climate_reference


def _reference(start_year: int = 1991, end_year: int = 2020) -> pd.DataFrame:
    dates = pd.date_range(
        f"{start_year}-01-01",
        f"{end_year}-12-31",
        freq="D",
        tz="UTC",
    )
    years = pd.Series(dates.year, index=dates)
    day = pd.Series(dates.dayofyear, index=dates)
    return pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_mean": (years - 1990).to_numpy(dtype=float),
            "precip_sum": ((years - 1990) / 10.0).to_numpy(dtype=float),
            "et0_sum": (2.0 + day * 0.0).to_numpy(dtype=float),
            "data_kind": ["reanalysis"] * len(dates),
            "data_source": ["ERA5-Land"] * len(dates),
        }
    )


def _current(
    start: str = "2026-04-01",
    days: int = 10,
    *,
    t_mean: float = 20.0,
    precipitation: float = 2.0,
    et0: float = 3.0,
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=days, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_mean": [t_mean] * days,
            "precip_sum": [precipitation] * days,
            "et0_sum": [et0] * days,
            "data_kind": ["reanalysis"] * (days - 1) + ["operational_past"],
            "data_source": ["history"] * days,
        }
    )


def test_reference_uses_same_length_windows_and_empirical_percentiles() -> None:
    result = calc_season_climate_reference(
        _current(),
        _reference(),
        crop="sunflower",
        season_start=date(2026, 4, 1),
    )

    assert result["available"] is True
    assert result["period_is_season"] is True
    assert result["window_days"] == 10
    temperature = result["metrics"]["mean_temperature_c"]
    assert temperature["reference_years"] == 30
    assert temperature["reference_mean"] == 15.5
    assert temperature["current"] == 20.0
    assert temperature["anomaly_from_mean"] == 4.5
    assert temperature["empirical_percentile"] == 65.0
    precipitation = result["metrics"]["precip_sum_mm"]
    assert precipitation["current"] == 20.0
    assert precipitation["reference_mean"] == 15.5
    assert precipitation["percent_of_mean"] == 129.0
    gdd = result["metrics"]["gdd_c_day"]
    assert gdd["current"] == 140.0
    assert gdd["reference_mean"] == 100.0


def test_forecast_overlap_cannot_replace_completed_current_day() -> None:
    current = _current(days=7, precipitation=1.0)
    overlap = current.iloc[[-1]].copy()
    overlap["date"] = overlap["date"] + pd.Timedelta(hours=12)
    overlap["precip_sum"] = 100.0
    overlap["data_kind"] = "forecast"
    current = pd.concat([current, overlap], ignore_index=True)

    result = calc_season_climate_reference(
        current,
        _reference(),
        crop="sunflower",
        season_start=date(2026, 4, 1),
    )

    assert result["metrics"]["precip_sum_mm"]["current"] == 7.0


def test_reference_with_fewer_than_twenty_valid_years_is_withheld() -> None:
    result = calc_season_climate_reference(
        _current(),
        _reference(2005, 2020),
        crop="sunflower",
        season_start=date(2026, 4, 1),
    )

    assert result["available"] is False
    assert result["metrics"]["mean_temperature_c"]["reference_years"] == 16
    assert result["metrics"]["mean_temperature_c"]["reference_mean"] is None


def test_missing_season_start_fails_closed() -> None:
    result = calc_season_climate_reference(
        _current(start="2026-04-02", days=9),
        _reference(),
        crop="sunflower",
        season_start=date(2026, 4, 1),
    )

    assert result["available"] is False
    assert result["period_is_season"] is False
    assert "не достигает" in result["status"]


def test_dry_spell_is_not_compared_across_missing_precipitation() -> None:
    current = _current(days=10, precipitation=0.0)
    current.loc[4, "precip_sum"] = float("nan")
    result = calc_season_climate_reference(
        current,
        _reference(),
        crop="sunflower",
        season_start=date(2026, 4, 1),
    )

    assert result["metrics"]["precip_sum_mm"]["available"] is True
    assert result["metrics"]["dry_days"]["available"] is False
    assert result["metrics"]["max_dry_spell_days"]["available"] is False


def test_cross_year_window_stays_inside_reference_period() -> None:
    result = calc_season_climate_reference(
        _current(start="2025-10-01", days=200),
        _reference(),
        crop="sunflower",
        season_start=date(2025, 10, 1),
    )

    # The 2020 anchor would extend into 2021 and is excluded.
    assert result["metrics"]["mean_temperature_c"]["reference_years"] == 29


def test_february_29_anchor_is_not_silently_shifted() -> None:
    result = calc_season_climate_reference(
        _current(start="2024-02-29", days=7),
        _reference(),
        crop="sunflower",
        season_start=date(2024, 2, 29),
    )

    # Only exact leap-day anchors are eligible; this is below the minimum.
    assert result["available"] is False
    assert result["metrics"]["mean_temperature_c"]["reference_years"] == 8
