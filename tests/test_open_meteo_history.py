import pandas as pd
import pytest

from src.api.open_meteo import (
    OpenMeteoError,
    _merge_daily,
    _parse_history_payload,
)


def test_parse_history_payload_preserves_source_and_local_day() -> None:
    payload = {
        "timezone": "Europe/Moscow",
        "daily": {
            "time": ["2026-07-01", "2026-07-02"],
            "temperature_2m_max": [25.0, 26.0],
            "temperature_2m_min": [15.0, 16.0],
            "temperature_2m_mean": [20.0, 21.0],
            "precipitation_sum": [1.0, 0.0],
            "et0_fao_evapotranspiration": [4.0, 4.2],
            "wind_speed_10m_max": [12.0, 10.0],
        },
    }
    frame = _parse_history_payload(payload, timezone_name="UTC")
    assert list(frame["data_kind"].unique()) == ["reanalysis"]
    assert frame.iloc[0]["date"].isoformat() == "2026-06-30T21:00:00+00:00"
    assert frame.iloc[0]["t_mean"] == 20.0


def test_operational_row_wins_when_local_days_overlap() -> None:
    history = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-06-30T21:00:00Z")],
            "t_max": [20.0],
            "t_min": [10.0],
            "t_mean": [15.0],
            "precip_sum": [0.0],
            "et0_sum": [3.0],
            "wind_max": [8.0],
            "data_kind": ["reanalysis"],
            "data_source": ["history"],
        }
    )
    operational = history.copy()
    operational["t_max"] = 30.0
    operational["data_kind"] = "operational_past"
    operational["data_source"] = "forecast-api"

    merged = _merge_daily(history, operational, "Europe/Moscow")
    assert len(merged) == 1
    assert merged.iloc[0]["t_max"] == 30.0
    assert merged.iloc[0]["data_kind"] == "operational_past"


def test_invalid_history_payload_is_rejected() -> None:
    with pytest.raises(OpenMeteoError):
        _parse_history_payload({"daily": {}}, timezone_name="UTC")
