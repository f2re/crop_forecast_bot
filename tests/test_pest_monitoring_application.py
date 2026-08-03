from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from src.application.pest_monitoring import PestMonitorRequest, evaluate_pest_monitors
from src.domain.soil_temperature import (
    SoilTemperatureCoverage,
    SoilTemperatureData,
    SoilTemperatureMeta,
)
from src.domain.weather import AgroWeatherData, WeatherCoverage, WeatherMeta


def _daily(source: str) -> pd.DataFrame:
    rows = []
    for offset in range(4):
        day = date(2026, 1, 1) + timedelta(days=offset)
        rows.append(
            {
                "date": pd.Timestamp(day, tz="UTC"),
                "local_date": day,
                "t_min": 10.0,
                "t_max": 30.0,
                "t_mean": 20.0,
                "data_kind": "reanalysis" if offset < 2 else "forecast",
                "data_source": source,
            }
        )
    return pd.DataFrame(rows)


class _AirProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, latitude, longitude, *, season_start=None):
        self.calls += 1
        assert season_start == date(2026, 1, 1)
        return AgroWeatherData(
            meta=WeatherMeta(
                latitude=latitude,
                longitude=longitude,
                elevation_m=25.0,
                utc_offset_seconds=3 * 3600,
                timezone="Europe/Simferopol",
                source="air source",
                retrieved_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            ),
            daily=_daily("air source"),
            hourly=pd.DataFrame(),
            past_days=2,
            forecast_days=2,
            coverage=WeatherCoverage(
                requested_season_start=season_start,
                actual_start=date(2026, 1, 1),
                actual_end=date(2026, 1, 4),
                season_coverage_complete=True,
            ),
        )


class _SoilProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, latitude, longitude, *, season_start=None):
        self.calls += 1
        assert season_start == date(2026, 1, 1)
        return SoilTemperatureData(
            meta=SoilTemperatureMeta(
                latitude=latitude,
                longitude=longitude,
                elevation_m=25.0,
                timezone="Europe/Simferopol",
                source="soil source",
                model="test",
                depth_label="модельный слой почвы 0–7 см",
                retrieved_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
                cache_ttl_seconds=3600,
            ),
            daily=_daily("soil source"),
            forecast_days=2,
            coverage=SoilTemperatureCoverage(
                requested_start=season_start,
                actual_start=date(2026, 1, 1),
                actual_end=date(2026, 1, 4),
                start_covered=True,
            ),
        )


@pytest.mark.asyncio
async def test_pest_requests_share_one_call_per_temperature_driver() -> None:
    air = _AirProvider()
    soil = _SoilProvider()
    requests = (
        PestMonitorRequest(None, "seedcorn_maggot_soil", date(2026, 1, 1)),
        PestMonitorRequest(None, "black_cutworm", date(2026, 1, 1)),
        PestMonitorRequest(None, "colorado_potato_beetle", date(2026, 1, 1)),
    )

    results = await evaluate_pest_monitors(
        45.75,
        33.875,
        requests,
        provider=air,
        soil_provider=soil,
        today=date(2026, 1, 3),
    )

    assert air.calls == 1
    assert soil.calls == 1
    assert [result.request.pest_key for result in results] == [
        "seedcorn_maggot_soil",
        "black_cutworm",
        "colorado_potato_beetle",
    ]
    assert results[0].source == "soil source"
    assert results[1].source == "air source"
    assert results[2].source == "air source"
