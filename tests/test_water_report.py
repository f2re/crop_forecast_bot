from datetime import date

import pandas as pd
import pytest

from src.application.agro_report import generate_agro_report
from src.domain.weather import AgroWeatherData, WeatherCoverage, WeatherMeta


class FakeWeatherProvider:
    def __init__(self, data: AgroWeatherData) -> None:
        self.data = data

    async def fetch(self, latitude, longitude, *, season_start=None):
        return self.data


@pytest.mark.asyncio
async def test_generated_report_contains_scientifically_bounded_accumulations() -> None:
    dates = pd.date_range("2026-07-01", periods=12, freq="D", tz="UTC")
    daily = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_max": [24.0] * 12,
            "t_min": [14.0] * 12,
            "t_mean": [19.0] * 12,
            "precip_sum": [
                0.0,
                0.0,
                2.0,
                0.0,
                0.0,
                0.0,
                4.0,
                0.0,
                0.0,
                0.0,
                50.0,
                50.0,
            ],
            "et0_sum": [2.0] * 12,
            "data_kind": ["reanalysis"] * 10 + ["forecast"] * 2,
            "data_source": ["history"] * 10 + ["forecast"] * 2,
        }
    )
    weather = AgroWeatherData(
        meta=WeatherMeta(
            latitude=55.75,
            longitude=37.62,
            elevation_m=150.0,
            utc_offset_seconds=0,
            timezone="UTC",
            source="Open-Meteo Forecast API",
        ),
        daily=daily,
        hourly=pd.DataFrame(),
        past_days=10,
        forecast_days=2,
        coverage=WeatherCoverage(
            requested_season_start=date(2026, 7, 1),
            actual_start=date(2026, 7, 1),
            actual_end=date(2026, 7, 12),
            season_coverage_complete=True,
            history_source="Open-Meteo Historical Weather API",
        ),
    )

    report = await generate_agro_report(
        55.75,
        37.62,
        "sunflower",
        season_start_date=date(2026, 7, 1),
        provider=FakeWeatherProvider(weather),
    )

    assert "Накопленные осадки с начала сезона: 6.0 мм" in report.text
    assert "Накопленная ET₀ провайдера с начала сезона: 20.0 мм" in report.text
    assert "Климатическая разность P−ET₀ с начала сезона: -14.0 мм" in report.text
    assert "Сухая серия на конец ряда: 3 сут.; максимум 3 сут." in report.text
    assert "не запас влаги в корнеобитаемом слое" in report.text
    assert "50.0" not in report.text
