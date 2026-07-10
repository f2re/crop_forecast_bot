from datetime import date

import pandas as pd
import pytest

from src.application.agro_report import generate_agro_report
from src.domain.weather import AgroWeatherData, WeatherCoverage, WeatherMeta


class FakeWeatherProvider:
    def __init__(self, data: AgroWeatherData) -> None:
        self.data = data
        self.requested_start = None

    async def fetch(self, latitude, longitude, *, season_start=None):
        self.requested_start = season_start
        return self.data


def _weather_data(daily: pd.DataFrame, *, start: date) -> AgroWeatherData:
    return AgroWeatherData(
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
        past_days=14,
        forecast_days=7,
        coverage=WeatherCoverage(
            requested_season_start=start,
            actual_start=start,
            actual_end=max(daily["local_date"]),
            season_coverage_complete=True,
            history_source=(
                "Open-Meteo Historical Weather API (reanalysis Best Match)"
            ),
        ),
    )


@pytest.mark.asyncio
async def test_report_separates_reanalysis_and_forecast_and_uses_season() -> None:
    now = pd.Timestamp.now(tz="UTC").normalize()
    start = now - pd.Timedelta(days=29)
    dates = pd.date_range(start=start, end=now + pd.Timedelta(days=2), freq="D", tz="UTC")
    daily = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_max": [24.0] * len(dates),
            "t_min": [14.0] * len(dates),
            "t_mean": [19.0] * len(dates),
            "precip_sum": [1.0] * len(dates),
            "et0_sum": [3.0] * len(dates),
            "wind_max": [10.0] * len(dates),
            "data_kind": ["reanalysis"] * 28
            + ["operational_past"]
            + ["forecast"] * 3,
            "data_source": ["history"] * 28 + ["forecast-api"] * 4,
        }
    )
    data = _weather_data(daily, start=start.date())
    provider = FakeWeatherProvider(data)

    report = await generate_agro_report(
        55.75,
        37.62,
        "sunflower",
        season_start_date=start.date(),
        phenological_phase="Бутонизация",
        field_name="Поле №1",
        provider=provider,
    )

    assert provider.requested_start == start.date()
    assert "Поле №1" in report.text
    assert "ГДД с начала сезона" in report.text
    assert "Бутонизация" in report.text
    assert "реанализ" in report.text.lower()
    assert "прогнозный прирост" in report.text.lower()
    assert report.timezone == "UTC"
    assert report.coverage.season_coverage_complete is True


@pytest.mark.asyncio
async def test_report_does_not_render_missing_et0_as_zero() -> None:
    now = pd.Timestamp.now(tz="UTC").normalize()
    dates = pd.date_range(end=now - pd.Timedelta(days=1), periods=7, freq="D", tz="UTC")
    daily = pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_max": [20.0] * 7,
            "t_min": [10.0] * 7,
            "t_mean": [15.0] * 7,
            "precip_sum": [float("nan")] * 7,
            "et0_sum": [float("nan")] * 7,
            "wind_max": [5.0] * 7,
            "data_kind": ["operational_past"] * 7,
            "data_source": ["forecast-api"] * 7,
        }
    )
    start = dates.min().date()
    provider = FakeWeatherProvider(_weather_data(daily, start=start))

    report = await generate_agro_report(
        55.75,
        37.62,
        "wheat",
        season_start_date=start,
        field_name="<Северное>",
        provider=provider,
    )

    assert "не рассчитаны" in report.text
    assert "+0.0 мм" not in report.text
    assert "&lt;Северное&gt;" in report.text
