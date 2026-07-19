from datetime import date, datetime, timezone

import pandas as pd
import pytest

from src.application.agro_report import generate_agro_report
from src.application.ports.climate import ClimateProviderError
from src.domain.climate import ClimateReferenceData, ClimateReferenceMeta
from src.domain.weather import AgroWeatherData, WeatherCoverage, WeatherMeta


class FakeWeatherProvider:
    def __init__(self, data: AgroWeatherData) -> None:
        self.data = data

    async def fetch(self, latitude, longitude, *, season_start=None):
        return self.data


class FakeClimateProvider:
    def __init__(self, data: ClimateReferenceData) -> None:
        self.data = data
        self.requested_timezone: str | None = None
        self.requested_season_start: date | None = None

    async def fetch_reference(
        self,
        latitude,
        longitude,
        *,
        timezone,
        season_start,
    ):
        self.requested_timezone = timezone
        self.requested_season_start = season_start
        return self.data


class FailingClimateProvider:
    async def fetch_reference(
        self,
        latitude,
        longitude,
        *,
        timezone,
        season_start,
    ):
        raise ClimateProviderError("provider unavailable")


def _weather() -> AgroWeatherData:
    completed = pd.date_range("2026-04-01", periods=10, freq="D", tz="UTC")
    forecast = pd.date_range("2026-04-11", periods=3, freq="D", tz="UTC")
    dates = completed.append(forecast)
    return AgroWeatherData(
        meta=WeatherMeta(
            latitude=55.75,
            longitude=37.62,
            elevation_m=150.0,
            utc_offset_seconds=0,
            timezone="UTC",
            source="Open-Meteo Forecast API",
            model="best_match",
            retrieved_at=datetime(2026, 4, 11, tzinfo=timezone.utc),
            cache_ttl_seconds=3600,
        ),
        daily=pd.DataFrame(
            {
                "date": dates,
                "local_date": list(dates.date),
                # Operational values intentionally differ from ERA5. The
                # climate section must use the homogeneous climate provider.
                "t_max": [35.0] * 10 + [36.0] * 3,
                "t_min": [25.0] * 10 + [26.0] * 3,
                "t_mean": [30.0] * 10 + [31.0] * 3,
                "precip_sum": [2.0] * 10 + [50.0] * 3,
                "et0_sum": [3.0] * 13,
                "wind_max": [8.0] * 13,
                "data_kind": ["reanalysis"] * 9
                + ["operational_past"]
                + ["forecast"] * 3,
                "data_source": ["history"] * 10 + ["forecast"] * 3,
            }
        ),
        hourly=pd.DataFrame(),
        past_days=10,
        forecast_days=3,
        coverage=WeatherCoverage(
            requested_season_start=date(2026, 4, 1),
            actual_start=date(2026, 4, 1),
            actual_end=date(2026, 4, 13),
            season_coverage_complete=True,
            history_source="Open-Meteo Historical Weather API",
        ),
    )


def _climate() -> ClimateReferenceData:
    reference_frames: list[pd.DataFrame] = []
    for year in range(1991, 2021):
        dates = pd.date_range(f"{year}-04-01", periods=10, freq="D", tz="UTC")
        offset = year - 1991
        reference_frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "local_date": list(dates.date),
                    "t_max": [18.0 + offset * 0.2] * 10,
                    "t_min": [8.0 + offset * 0.2] * 10,
                    "t_mean": [13.0 + offset * 0.2] * 10,
                    "precip_sum": [1.0 + offset * 0.02] * 10,
                    "et0_sum": [2.0 + offset * 0.01] * 10,
                    "wind_max": [7.0] * 10,
                    "data_kind": ["reanalysis"] * 10,
                    "data_source": ["ERA5"] * 10,
                }
            )
        )
    current_dates = pd.date_range("2026-04-01", periods=10, freq="D", tz="UTC")
    current = pd.DataFrame(
        {
            "date": current_dates,
            "local_date": list(current_dates.date),
            "t_max": [25.0] * 10,
            "t_min": [15.0] * 10,
            "t_mean": [20.0] * 10,
            "precip_sum": [2.0] * 10,
            "et0_sum": [3.0] * 10,
            "wind_max": [7.0] * 10,
            "data_kind": ["reanalysis"] * 10,
            "data_source": ["ERA5"] * 10,
        }
    )
    return ClimateReferenceData(
        meta=ClimateReferenceMeta(
            latitude=55.7,
            longitude=37.6,
            elevation_m=170.0,
            timezone="UTC",
            source="ERA5 via Open-Meteo Historical Weather API",
            model="era5",
            reference_start=date(1991, 1, 1),
            reference_end=date(2020, 12, 31),
            comparison_start=date(2026, 4, 1),
            comparison_end=date(2026, 4, 10),
            retrieved_at=datetime(2026, 4, 11, tzinfo=timezone.utc),
            reference_cache_ttl_seconds=30 * 24 * 60 * 60,
            current_cache_ttl_seconds=6 * 60 * 60,
            spatial_resolution_km=25.0,
        ),
        reference_daily=pd.concat(reference_frames, ignore_index=True),
        current_daily=current,
    )


@pytest.mark.asyncio
async def test_report_contains_homogeneous_empirical_climate_reference() -> None:
    climate_provider = FakeClimateProvider(_climate())
    report = await generate_agro_report(
        55.75,
        37.62,
        "sunflower",
        season_start_date=date(2026, 4, 1),
        provider=FakeWeatherProvider(_weather()),
        climate_provider=climate_provider,
    )

    assert climate_provider.requested_timezone == "UTC"
    assert climate_provider.requested_season_start == date(2026, 4, 1)
    assert "Сезон ERA5 относительно базы 1991–2020" in report.text
    assert "Средняя температура: 20.0°C" in report.text
    assert "Средняя температура: 30.0°C" not in report.text
    assert "эмпирический процентиль" in report.text
    assert "осадки" in report.text
    assert "не вероятность" in report.text
    assert "не полевая станция, не SPI/SPEI" in report.text
    assert "01.04.2026 — 10.04.2026" in report.text
    assert "текущий сезон и база 1991–2020 из одной модели ERA5" in report.text
    assert "ERA5 via Open-Meteo Historical Weather API" in report.source
    assert len(report.text) <= 4096


@pytest.mark.asyncio
async def test_climate_outage_degrades_report_without_losing_operational_data() -> None:
    report = await generate_agro_report(
        55.75,
        37.62,
        "sunflower",
        season_start_date=date(2026, 4, 1),
        provider=FakeWeatherProvider(_weather()),
        climate_provider=FailingClimateProvider(),
    )

    assert "ГДД с начала сезона" in report.text
    assert "однородный ряд ERA5 временно недоступен" in report.text
    assert "ERA5 via Open-Meteo Historical Weather API" not in report.source


@pytest.mark.asyncio
async def test_custom_weather_provider_does_not_trigger_default_climate_network() -> None:
    report = await generate_agro_report(
        55.75,
        37.62,
        "sunflower",
        season_start_date=date(2026, 4, 1),
        provider=FakeWeatherProvider(_weather()),
    )

    assert "Сезон ERA5 относительно базы" not in report.text
