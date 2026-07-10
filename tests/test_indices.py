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


def test_frost_result_matches_scheduler_contract_and_local_offset() -> None:
    now = pd.Timestamp.now(tz="UTC").normalize()
    frame = pd.DataFrame(
        {
            "date": [now + pd.Timedelta(days=1), now + pd.Timedelta(days=2)],
            "t_min": [-1.5, 5.0],
        }
    )
    result = calc_frost_risk(frame, utc_offset_seconds=3 * 3600)
    assert len(result["alerts"]) == 1
    event = result["alerts"][0]
    assert event["event_date"]
    assert event["min_temp"] == -1.5
    assert event["level"] == "critical"
    assert "03:00" in event["date_local"]
