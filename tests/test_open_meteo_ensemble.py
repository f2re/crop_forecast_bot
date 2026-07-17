from datetime import datetime, timezone

import pytest

from src.api.open_meteo_ensemble import OpenMeteoEnsembleError, parse_ensemble_payload


def _payload() -> dict:
    daily = {"time": ["2026-07-17", "2026-07-18"]}
    variables = {
        "temperature_2m_min": [5.0, 4.0],
        "temperature_2m_max": [25.0, 26.0],
        "precipitation_sum": [1.0, 2.0],
        "wind_gusts_10m_max": [7.0, 8.0],
        "cape_max": [100.0, 200.0],
    }
    for variable, values in variables.items():
        daily[variable] = values
        daily[f"{variable}_member01"] = [value + 1 for value in values]
    return {
        "latitude": 55.75,
        "longitude": 37.62,
        "elevation": 150.0,
        "timezone": "Europe/Moscow",
        "daily": daily,
    }


def test_parse_ensemble_payload_builds_day_member_rows() -> None:
    data = parse_ensemble_payload(
        _payload(),
        retrieved_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )

    assert data.meta.member_count == 2
    assert data.meta.forecast_days == 2
    assert set(data.daily_members["member_id"]) == {"control", "member01"}
    member = data.daily_members[
        (data.daily_members["member_id"] == "member01")
        & (data.daily_members["local_date"].astype(str) == "2026-07-18")
    ].iloc[0]
    assert member["t_min_c"] == 5.0
    assert member["precip_mm"] == 3.0


def test_parse_ensemble_payload_rejects_missing_variable() -> None:
    payload = _payload()
    payload["daily"].pop("cape_max")
    payload["daily"].pop("cape_max_member01")

    with pytest.raises(OpenMeteoEnsembleError, match="cape_max"):
        parse_ensemble_payload(payload)
