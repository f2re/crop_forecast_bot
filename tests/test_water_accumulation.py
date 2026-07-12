import pandas as pd

from src.agro.water import calc_water_accumulation


def test_water_accumulation_uses_completed_season_and_paired_balance() -> None:
    as_of = pd.Timestamp("2026-07-11T12:00:00Z")
    completed = pd.date_range("2026-07-01", periods=10, freq="D", tz="UTC")
    forecast = pd.date_range("2026-07-11", periods=2, freq="D", tz="UTC")
    dates = completed.append(forecast)
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "precip_sum": [0.0, 0.5, 0.0, 2.0, 0.0, 0.0, 0.0, 5.0, 0.0, 0.2]
            + [100.0, 100.0],
            "et0_sum": [2.0] * 12,
            "data_kind": ["reanalysis"] * 9
            + ["operational_past"]
            + ["forecast"] * 2,
        }
    )

    result = calc_water_accumulation(
        frame,
        season_start=pd.Timestamp("2026-07-01T00:00:00", tz="Europe/Moscow"),
        as_of=as_of,
    )

    assert result["period_is_season"] is True
    assert result["period_start"] == "2026-07-01"
    assert result["period_end"] == "2026-07-10"
    assert result["precip_sum_mm"] == 7.7
    assert result["wet_day_precip_sum_mm"] == 7.0
    assert result["et0_sum_mm"] == 20.0
    assert result["p_minus_et0_mm"] == -12.3
    assert result["et0_minus_p_mm"] == 12.3
    assert result["wet_days"] == 2
    assert result["dry_days"] == 8
    assert result["trailing_dry_spell_days"] == 2
    assert result["max_dry_spell_days"] == 3
    assert result["max_wet_spell_days"] == 1
    assert result["max_1day_precip_mm"] == 5.0
    assert result["max_1day_precip_date"] == "2026-07-08"
    assert result["max_5day_precip_mm"] == 7.0
    assert "forecast" not in result["source_counts"]


def test_water_accumulation_keeps_precip_when_et0_is_missing() -> None:
    dates = pd.date_range("2026-07-01", periods=5, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "precip_sum": [0.0, 0.0, 3.0, 0.0, 0.0],
            "et0_sum": [float("nan")] * 5,
            "data_kind": ["operational_past"] * 5,
        }
    )

    result = calc_water_accumulation(
        frame,
        season_start=dates[0],
        as_of=pd.Timestamp("2026-07-06T12:00:00Z"),
    )

    assert result["precip_available"] is True
    assert result["precip_sum_mm"] == 3.0
    assert result["et0_available"] is False
    assert result["et0_sum_mm"] is None
    assert result["paired_available"] is False
    assert result["p_minus_et0_mm"] is None
    assert result["dry_spell_available"] is True


def test_missing_precipitation_day_withholds_spells_but_not_valid_total() -> None:
    dates = pd.date_range("2026-07-01", periods=10, freq="D", tz="UTC")
    precipitation = [0.0] * 10
    precipitation[4] = float("nan")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "precip_sum": precipitation,
            "et0_sum": [2.0] * 10,
            "data_kind": ["reanalysis"] * 10,
        }
    )

    result = calc_water_accumulation(
        frame,
        season_start=dates[0],
        as_of=pd.Timestamp("2026-07-11T12:00:00Z"),
    )

    assert result["precip_available"] is True
    assert result["precip_missing_fraction"] == 0.1
    assert result["dry_spell_available"] is False
    assert result["trailing_dry_spell_days"] is None
    assert result["max_dry_spell_days"] is None
    assert result["max_5day_precip_mm"] is None


def test_excessive_missingness_withholds_accumulated_values() -> None:
    dates = pd.date_range("2026-07-01", periods=10, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "precip_sum": [float("nan"), float("nan")] + [1.0] * 8,
            "et0_sum": [float("nan"), float("nan")] + [2.0] * 8,
            "data_kind": ["reanalysis"] * 10,
        }
    )

    result = calc_water_accumulation(
        frame,
        season_start=dates[0],
        as_of=pd.Timestamp("2026-07-11T12:00:00Z"),
    )

    assert result["precip_available"] is False
    assert result["et0_available"] is False
    assert result["paired_available"] is False
    assert result["precip_sum_mm"] is None
    assert result["et0_sum_mm"] is None
    assert result["p_minus_et0_mm"] is None


def test_negative_water_depths_are_invalid_not_clipped_to_zero() -> None:
    dates = pd.date_range("2026-07-01", periods=5, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "precip_sum": [1.0, -1.0, 1.0, 1.0, 1.0],
            "et0_sum": [2.0, 2.0, -0.5, 2.0, 2.0],
            "data_kind": ["operational_past"] * 5,
        }
    )

    result = calc_water_accumulation(
        frame,
        season_start=dates[0],
        max_missing_fraction=0.25,
        as_of=pd.Timestamp("2026-07-06T12:00:00Z"),
    )

    assert result["negative_precip_days"] == 1
    assert result["negative_et0_days"] == 1
    assert result["precip_sum_mm"] == 4.0
    assert result["et0_sum_mm"] == 8.0
    assert result["paired_days"] == 3
    assert result["p_minus_et0_mm"] is None


def test_local_season_boundary_excludes_prior_days() -> None:
    dates = pd.date_range("2026-06-29", periods=5, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "precip_sum": [100.0, 100.0, 1.0, 2.0, 3.0],
            "et0_sum": [10.0] * 5,
            "data_kind": ["reanalysis"] * 5,
        }
    )

    result = calc_water_accumulation(
        frame,
        season_start=pd.Timestamp("2026-07-01T00:00:00", tz="Europe/Moscow"),
        as_of=pd.Timestamp("2026-07-04T12:00:00Z"),
    )

    assert result["period_start"] == "2026-07-01"
    assert result["precip_sum_mm"] == 6.0
    assert result["et0_sum_mm"] == 30.0


def test_overlapping_forecast_row_does_not_hide_completed_day() -> None:
    frame = pd.DataFrame(
        {
            "date": [
                pd.Timestamp("2026-07-01T00:00:00Z"),
                pd.Timestamp("2026-07-01T12:00:00Z"),
            ],
            "local_date": [
                pd.Timestamp("2026-07-01").date(),
                pd.Timestamp("2026-07-01").date(),
            ],
            "precip_sum": [2.0, 100.0],
            "et0_sum": [3.0, 3.0],
            "data_kind": ["operational_past", "forecast"],
        }
    )

    result = calc_water_accumulation(
        frame,
        season_start=pd.Timestamp("2026-07-01T00:00:00Z"),
        as_of=pd.Timestamp("2026-07-02T12:00:00Z"),
    )

    assert result["precip_sum_mm"] == 2.0
    assert result["et0_sum_mm"] == 3.0
    assert result["source_counts"] == {"operational_past": 1}
