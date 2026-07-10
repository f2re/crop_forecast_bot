from datetime import date

import pandas as pd
import pytest

from src.domain.weather import AgroWeatherData, WeatherCoverage, WeatherMeta
from src.ops.provider_smoke import validate_weather_data


def _data(frame: pd.DataFrame) -> AgroWeatherData:
    return AgroWeatherData(
        meta=WeatherMeta(
            latitude=55.75,
            longitude=37.62,
            elevation_m=150.0,
            utc_offset_seconds=3 * 3600,
            timezone="Europe/Moscow",
            source="Open-Meteo Forecast API",
        ),
        daily=frame,
        hourly=pd.DataFrame(),
        past_days=14,
        forecast_days=7,
        coverage=WeatherCoverage(
            requested_season_start=date(2026, 4, 15),
            actual_start=date(2026, 4, 15),
            actual_end=date(2026, 7, 17),
            season_coverage_complete=True,
            history_source="Open-Meteo Historical Weather API",
        ),
    )


def test_provider_smoke_accepts_partitioned_real_contract() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-09T21:00:00Z", "2026-07-10T21:00:00Z"]),
            "local_date": [date(2026, 7, 10), date(2026, 7, 11)],
            "t_max": [24.0, 25.0],
            "t_min": [14.0, 15.0],
            "t_mean": [19.0, 20.0],
            "precip_sum": [1.0, 0.0],
            "et0_sum": [3.0, 3.2],
            "data_kind": ["operational_past", "forecast"],
            "data_source": ["forecast-api", "forecast-api"],
        }
    )
    result = validate_weather_data(_data(frame))
    assert result.completed_rows == 1
    assert result.forecast_rows == 1
    assert result.season_coverage_complete is True


def test_provider_smoke_rejects_dataset_without_forecast() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-09T21:00:00Z"]),
            "local_date": [date(2026, 7, 10)],
            "t_max": [24.0],
            "t_min": [14.0],
            "t_mean": [19.0],
            "precip_sum": [1.0],
            "et0_sum": [3.0],
            "data_kind": ["reanalysis"],
            "data_source": ["history"],
        }
    )
    with pytest.raises(ValueError, match="no forecast rows"):
        validate_weather_data(_data(frame))
