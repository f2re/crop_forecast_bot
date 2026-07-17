import pandas as pd

from src.agro.indices import (
    FROST_STATUS_INSUFFICIENT,
    FROST_STATUS_NO_RISK,
    FROST_STATUS_RISK,
    calc_et0_balance,
    calc_frost_risk,
    calc_gdd,
    calc_htc,
)


def test_htc_requires_explicit_season_start() -> None:
    as_of = pd.Timestamp("2026-07-10T12:00:00Z")
    dates = pd.date_range(end="2026-07-09", periods=30, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_mean": [15.0] * 30,
            "precip_sum": [1.0] * 30,
            "data_kind": ["operational_past"] * 30,
        }
    )
    result = calc_htc(frame, as_of=as_of)
    assert result["htc"] is None
    assert result["period_is_season"] is False
    assert result["period_start"] is None
    assert "не задана дата" in result["interpretation"]


def test_htc_is_not_reported_for_short_warm_season() -> None:
    as_of = pd.Timestamp("2026-07-10T12:00:00Z")
    dates = pd.date_range(end="2026-07-09", periods=14, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_mean": [15.0] * 14,
            "precip_sum": [1.0] * 14,
            "data_kind": ["operational_past"] * 14,
        }
    )
    result = calc_htc(
        frame,
        season_start=pd.Timestamp("2026-06-26", tz="Europe/Moscow"),
        as_of=as_of,
    )
    assert result["htc"] is None
    assert result["available_days"] == 14
    assert result["source_counts"] == {"operational_past": 14}


def test_htc_excludes_forecast_precipitation() -> None:
    as_of = pd.Timestamp("2026-07-31T12:00:00Z")
    past_dates = pd.date_range("2026-07-01", periods=30, freq="D", tz="UTC")
    future_date = pd.Timestamp("2026-07-31T00:00:00Z")
    frame = pd.DataFrame(
        {
            "date": list(past_dates) + [future_date],
            "local_date": list(past_dates.date) + [future_date.date()],
            "t_mean": [20.0] * 31,
            "precip_sum": [2.0] * 30 + [1000.0],
            "data_kind": ["reanalysis"] * 30 + ["forecast"],
        }
    )
    result = calc_htc(
        frame,
        season_start=pd.Timestamp("2026-07-01", tz="Europe/Moscow"),
        as_of=as_of,
    )
    assert result["htc"] == 1.0
    assert result["sum_precip_mm"] == 60.0
    assert result["period_start"] == "2026-07-01"
    assert result["period_end"] == "2026-07-30"
    assert result["period_is_season"] is True
    assert "forecast" not in result["source_counts"]


def test_htc_fails_closed_on_calendar_gap() -> None:
    as_of = pd.Timestamp("2026-07-31T12:00:00Z")
    dates = pd.date_range("2026-07-01", periods=30, freq="D", tz="UTC").delete(14)
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_mean": [20.0] * len(dates),
            "precip_sum": [2.0] * len(dates),
            "data_kind": ["reanalysis"] * len(dates),
        }
    )
    result = calc_htc(
        frame,
        season_start=pd.Timestamp("2026-07-01", tz="Europe/Moscow"),
        as_of=as_of,
    )
    assert result["htc"] is None
    assert result["missing_days"] == 1
    assert result["missing_fraction"] == 0.033
    assert "пропущено 1" in result["interpretation"]


def test_htc_fails_closed_on_negative_precipitation() -> None:
    as_of = pd.Timestamp("2026-07-31T12:00:00Z")
    dates = pd.date_range("2026-07-01", periods=30, freq="D", tz="UTC")
    precipitation = [2.0] * 30
    precipitation[10] = -1.0
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_mean": [20.0] * 30,
            "precip_sum": precipitation,
            "data_kind": ["reanalysis"] * 30,
        }
    )
    result = calc_htc(
        frame,
        season_start=pd.Timestamp("2026-07-01", tz="Europe/Moscow"),
        as_of=as_of,
    )
    assert result["htc"] is None
    assert result["missing_days"] == 1


def test_gdd_does_not_infer_phenology_without_season_start() -> None:
    as_of = pd.Timestamp("2026-07-10T12:00:00Z")
    dates = pd.date_range(end="2026-07-09", periods=14, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_max": [25.0] * 14,
            "t_min": [15.0] * 14,
            "data_kind": ["operational_past"] * 14,
        }
    )
    result = calc_gdd(frame, crop="corn", as_of=as_of)
    assert result["gdd_past"] == 140.0
    assert result["period_is_season"] is False
    assert result["current_phase"] is None


def test_gdd_uses_catalog_base_and_separates_forecast() -> None:
    as_of = pd.Timestamp("2026-07-10T12:00:00Z")
    past_dates = pd.date_range("2026-06-11", periods=29, freq="D", tz="UTC")
    future_dates = pd.date_range("2026-07-10", periods=2, freq="D", tz="UTC")
    dates = past_dates.append(future_dates)
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_max": [24.0] * len(dates),
            "t_min": [14.0] * len(dates),
            "data_kind": ["reanalysis"] * 28
            + ["operational_past"]
            + ["forecast"] * 2,
        }
    )
    season_start = pd.Timestamp("2026-06-11T00:00:00", tz="Europe/Moscow")
    result = calc_gdd(
        frame,
        crop="sunflower",
        season_start=season_start,
        as_of=as_of,
    )
    assert result["t_base"] == 6.0
    assert result["period_is_season"] is True
    assert result["gdd_past"] == 377.0
    assert result["gdd_forecast_7d"] == 26.0
    assert result["valid_days"] == 29
    assert result["missing_fraction"] == 0.0
    assert result["contribution_by_kind"] == {
        "operational_past": 13.0,
        "reanalysis": 364.0,
    }
    assert result["current_phase"] is None


def test_gdd_strictly_excludes_local_days_before_sowing() -> None:
    as_of = pd.Timestamp("2026-06-14T12:00:00Z")
    dates = pd.date_range("2026-06-09", periods=5, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_max": [25.0] * 5,
            "t_min": [15.0] * 5,
            "data_kind": ["operational_past"] * 5,
        }
    )

    result = calc_gdd(
        frame,
        crop="corn",
        season_start=pd.Timestamp("2026-06-11T00:00:00", tz="Europe/Moscow"),
        as_of=as_of,
    )

    assert result["period_start"] == "2026-06-11"
    assert result["gdd_past"] == 30.0
    assert result["valid_days"] == 3
    assert result["period_is_season"] is True


def test_gdd_does_not_claim_season_when_start_day_is_missing() -> None:
    as_of = pd.Timestamp("2026-06-15T12:00:00Z")
    dates = pd.date_range("2026-06-12", periods=3, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_max": [25.0] * 3,
            "t_min": [15.0] * 3,
            "data_kind": ["operational_past"] * 3,
        }
    )

    result = calc_gdd(
        frame,
        crop="corn",
        season_start=pd.Timestamp("2026-06-11T00:00:00", tz="Europe/Moscow"),
        as_of=as_of,
    )

    assert result["coverage_start_reached"] is False
    assert result["period_is_season"] is False
    assert result["expected_days"] == 4
    assert result["missing_days"] == 1


def test_gdd_returns_unavailable_instead_of_false_zero() -> None:
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-07-11T00:00:00Z")],
            "local_date": [pd.Timestamp("2026-07-11").date()],
            "t_max": [25.0],
            "t_min": [15.0],
            "data_kind": ["forecast"],
        }
    )
    result = calc_gdd(
        frame,
        crop="corn",
        as_of=pd.Timestamp("2026-07-10T12:00:00Z"),
    )
    assert result["gdd_past"] is None
    assert result["gdd_forecast_7d"] == 10.0


def test_frost_result_matches_scheduler_contract() -> None:
    frame = pd.DataFrame(
        {
            "date": [
                pd.Timestamp("2026-07-11T00:00:00Z"),
                pd.Timestamp("2026-07-12T00:00:00Z"),
            ],
            "local_date": [
                pd.Timestamp("2026-07-11").date(),
                pd.Timestamp("2026-07-12").date(),
            ],
            "t_min": [-1.5, 5.0],
            "data_kind": ["forecast", "forecast"],
            "data_source": ["forecast-api", "forecast-api"],
        }
    )
    result = calc_frost_risk(
        frame,
        utc_offset_seconds=3 * 3600,
        crop="wheat",
        phase="Кущение",
        elevation_m=120.0,
        as_of=pd.Timestamp("2026-07-10T12:00:00Z"),
    )
    assert result["status"] == FROST_STATUS_RISK
    assert result["available"] is True
    assert result["valid_forecast_days"] == 2
    assert len(result["alerts"]) == 1
    event = result["alerts"][0]
    assert event["event_date"] == "2026-07-11"
    assert event["date_local"] == "11.07.2026"
    assert event["min_temp"] == -1.5
    assert event["level"] == "critical"
    assert event["lead_days"] == 1
    assert event["phase"] == "Кущение"
    assert event["elevation_m"] == 120.0


def test_frost_screening_reports_insufficient_data_without_forecast() -> None:
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-07-09T00:00:00Z")],
            "local_date": [pd.Timestamp("2026-07-09").date()],
            "t_min": [-8.0],
            "data_kind": ["reanalysis"],
        }
    )
    result = calc_frost_risk(
        frame,
        as_of=pd.Timestamp("2026-07-10T12:00:00Z"),
    )
    assert result["alerts"] == []
    assert result["available"] is False
    assert result["status"] == FROST_STATUS_INSUFFICIENT
    assert result["forecast_days"] == 0


def test_frost_screening_reports_missing_forecast_tmin() -> None:
    dates = pd.date_range("2026-07-11", periods=2, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_min": [float("nan"), float("nan")],
            "data_kind": ["forecast", "forecast"],
        }
    )
    result = calc_frost_risk(
        frame,
        as_of=pd.Timestamp("2026-07-10T12:00:00Z"),
    )
    assert result["status"] == FROST_STATUS_INSUFFICIENT
    assert result["forecast_days"] == 2
    assert result["valid_forecast_days"] == 0
    assert result["missing_forecast_days"] == 2


def test_frost_screening_distinguishes_valid_no_risk() -> None:
    dates = pd.date_range("2026-07-11", periods=2, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_min": [5.0, 6.0],
            "data_kind": ["forecast", "forecast"],
        }
    )
    result = calc_frost_risk(
        frame,
        as_of=pd.Timestamp("2026-07-10T12:00:00Z"),
    )
    assert result["available"] is True
    assert result["status"] == FROST_STATUS_NO_RISK
    assert result["alerts"] == []


def test_et0_balance_does_not_turn_missing_data_into_zero() -> None:
    dates = pd.date_range("2026-07-03", periods=7, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "precip_sum": [float("nan")] * 7,
            "et0_sum": [float("nan")] * 7,
            "data_kind": ["operational_past"] * 7,
        }
    )
    result = calc_et0_balance(
        frame,
        as_of=pd.Timestamp("2026-07-10T12:00:00Z"),
    )
    assert result["available"] is False
    assert result["precip_sum_mm"] is None
    assert result["et0_sum_mm"] is None
    assert result["balance_mm"] is None
