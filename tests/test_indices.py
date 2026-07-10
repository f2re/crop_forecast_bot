import pandas as pd

from src.agro.indices import calc_frost_risk, calc_gdd, calc_htc


def test_htc_is_not_reported_for_short_warm_window() -> None:
    now = pd.Timestamp.now(tz="UTC").normalize()
    frame = pd.DataFrame(
        {
            "date": pd.date_range(end=now, periods=14, freq="D", tz="UTC"),
            "t_mean": [15.0] * 14,
            "precip_sum": [1.0] * 14,
        }
    )
    result = calc_htc(frame)
    assert result["htc"] is None
    assert result["available_days"] == 14


def test_gdd_does_not_infer_phenology_without_season_start() -> None:
    now = pd.Timestamp.now(tz="UTC").normalize()
    frame = pd.DataFrame(
        {
            "date": pd.date_range(end=now, periods=14, freq="D", tz="UTC"),
            "t_max": [25.0] * 14,
            "t_min": [15.0] * 14,
        }
    )
    result = calc_gdd(frame, crop="corn")
    assert result["gdd_past"] > 0
    assert result["period_is_season"] is False
    assert result["current_phase"] is None


def test_gdd_uses_catalog_base_and_reports_complete_season() -> None:
    now = pd.Timestamp.now(tz="UTC").normalize()
    start = now - pd.Timedelta(days=29)
    frame = pd.DataFrame(
        {
            "date": pd.date_range(start=start, end=now, freq="D", tz="UTC"),
            "t_max": [24.0] * 30,
            "t_min": [14.0] * 30,
            "data_kind": ["reanalysis"] * 29 + ["operational_past"],
        }
    )
    result = calc_gdd(frame, crop="sunflower", season_start=start)
    assert result["t_base"] == 6.0
    assert result["period_is_season"] is True
    assert result["valid_days"] == 30
    assert result["missing_fraction"] == 0.0
    assert result["current_phase"] is None
    assert "валидации" in result["phenology_note"]


def test_frost_result_matches_scheduler_contract_and_local_offset() -> None:
    now = pd.Timestamp.now(tz="UTC").normalize()
    frame = pd.DataFrame(
        {
            "date": [now + pd.Timedelta(days=1), now + pd.Timedelta(days=2)],
            "t_min": [-1.5, 5.0],
        }
    )
    result = calc_frost_risk(
        frame,
        utc_offset_seconds=3 * 3600,
        crop="wheat",
        phase="Кущение",
        elevation_m=120.0,
    )
    assert len(result["alerts"]) == 1
    event = result["alerts"][0]
    assert event["event_date"]
    assert event["min_temp"] == -1.5
    assert event["level"] == "critical"
    assert event["phase"] == "Кущение"
    assert event["elevation_m"] == 120.0
    assert "03:00" in event["date_local"]
