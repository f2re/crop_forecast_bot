from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from src.api.open_meteo_late_blight import (
    build_late_blight_request_params,
    parse_late_blight_payload,
)
from src.application.ports.late_blight import LateBlightWeatherProviderError


def test_request_separates_hutton_inputs_from_moisture_context() -> None:
    params = build_late_blight_request_params(55.75, 37.62)

    assert params["latitude"] == 55.75
    assert params["longitude"] == 37.62
    assert params["hourly"].split(",") == [
        "temperature_2m",
        "relative_humidity_2m",
        "dew_point_2m",
        "precipitation",
        "weather_code",
        "visibility",
        "is_day",
    ]
    assert params["past_days"] == 3
    assert params["forecast_days"] == 7
    assert params["timezone"] == "auto"
    assert params["timeformat"] == "unixtime"
    assert params["cell_selection"] == "land"
    assert "models" not in params


def test_payload_parser_returns_typed_hourly_series() -> None:
    retrieved_at = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
    payload = {
        "latitude": 55.75,
        "longitude": 37.62,
        "elevation": 152.0,
        "timezone": "Europe/Moscow",
        "hourly": {
            "time": [1785715200, 1785718800],
            "temperature_2m": [12.5, 12.1],
            "relative_humidity_2m": [91.0, 94.0],
            "dew_point_2m": [11.7, 11.5],
            "precipitation": [0.0, 0.2],
            "weather_code": [3, 45],
            "visibility": [10000.0, 700.0],
            "is_day": [0, 0],
        },
    }

    weather = parse_late_blight_payload(payload, retrieved_at=retrieved_at)

    assert weather.meta.timezone == "Europe/Moscow"
    assert weather.meta.source == "Open-Meteo Forecast API"
    assert weather.meta.model == "best_match"
    assert weather.meta.retrieved_at == retrieved_at
    assert list(weather.hourly.columns) == [
        "date",
        "temperature_2m",
        "relative_humidity_2m",
        "dew_point_2m",
        "precipitation",
        "weather_code",
        "visibility",
        "is_day",
    ]
    assert str(weather.hourly["date"].dt.tz) == "UTC"
    assert weather.hourly["relative_humidity_2m"].tolist() == [91.0, 94.0]
    assert weather.hourly["weather_code"].tolist() == [3, 45]


def test_optional_moisture_fields_degrade_without_breaking_hutton() -> None:
    payload = {
        "timezone": "UTC",
        "hourly": {
            "time": [1785715200, 1785718800],
            "temperature_2m": [12.5, 12.1],
            "relative_humidity_2m": [91.0, 94.0],
        },
    }

    weather = parse_late_blight_payload(
        payload,
        retrieved_at=datetime.now(timezone.utc),
    )

    assert weather.hourly["temperature_2m"].tolist() == [12.5, 12.1]
    for column in (
        "dew_point_2m",
        "precipitation",
        "weather_code",
        "visibility",
        "is_day",
    ):
        assert weather.hourly[column].isna().all(), column


def test_payload_parser_rejects_different_variable_lengths() -> None:
    payload = {
        "timezone": "UTC",
        "hourly": {
            "time": [1785715200, 1785718800],
            "temperature_2m": [12.5],
            "relative_humidity_2m": [91.0, 94.0],
        },
    }

    with pytest.raises(LateBlightWeatherProviderError, match="имеет длину"):
        parse_late_blight_payload(
            payload,
            retrieved_at=datetime.now(timezone.utc),
        )


def test_payload_parser_rejects_optional_variable_length_mismatch() -> None:
    payload = {
        "timezone": "UTC",
        "hourly": {
            "time": [1785715200, 1785718800],
            "temperature_2m": [12.5, 12.1],
            "relative_humidity_2m": [91.0, 94.0],
            "visibility": [900.0],
        },
    }

    with pytest.raises(LateBlightWeatherProviderError, match="visibility"):
        parse_late_blight_payload(
            payload,
            retrieved_at=datetime.now(timezone.utc),
        )


def test_payload_parser_preserves_provider_error() -> None:
    with pytest.raises(LateBlightWeatherProviderError, match="invalid latitude"):
        parse_late_blight_payload(
            {"error": True, "reason": "invalid latitude"},
            retrieved_at=datetime.now(timezone.utc),
        )


def test_payload_parser_rejects_unknown_timezone() -> None:
    payload = {
        "timezone": "Mars/Olympus",
        "hourly": {
            "time": [1785715200],
            "temperature_2m": [12.5],
            "relative_humidity_2m": [91.0],
        },
    }

    with pytest.raises(LateBlightWeatherProviderError, match="часовой пояс"):
        parse_late_blight_payload(
            payload,
            retrieved_at=datetime.now(timezone.utc),
        )


def test_parser_timestamps_remain_timezone_aware() -> None:
    payload = {
        "timezone": "UTC",
        "hourly": {
            "time": ["2026-08-03T00:00:00Z"],
            "temperature_2m": [12.5],
            "relative_humidity_2m": [91.0],
        },
    }

    weather = parse_late_blight_payload(
        payload,
        retrieved_at=datetime.now(timezone.utc),
    )

    assert isinstance(weather.hourly.loc[0, "date"], pd.Timestamp)
    assert weather.hourly.loc[0, "date"].tzinfo is not None
