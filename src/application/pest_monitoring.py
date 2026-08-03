from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

from src.agro.pest_phenology import calculate_pest_outlook
from src.api.open_meteo import OpenMeteoProvider
from src.application.ports.weather import WeatherProvider
from src.domain.pests import PestOutlook
from src.domain.season import local_today


@dataclass(frozen=True, slots=True)
class PestMonitorRequest:
    monitor_id: int | None
    pest_key: str
    biofix_date: date


@dataclass(frozen=True, slots=True)
class PestMonitorResult:
    request: PestMonitorRequest
    outlook: PestOutlook
    timezone: str
    source: str
    retrieved_at: datetime | None


async def evaluate_pest_monitors(
    latitude: float,
    longitude: float,
    requests: Sequence[PestMonitorRequest],
    *,
    provider: WeatherProvider | None = None,
    today: date | None = None,
    forecast_horizon_days: int = 7,
) -> tuple[PestMonitorResult, ...]:
    """Evaluate one or more crop-pest monitors with one weather request.

    This service only estimates temperature-dependent development after an
    explicit user observation. It does not infer pest presence, abundance,
    economic damage or a need for treatment.
    """

    if not requests:
        return ()
    if forecast_horizon_days < 0:
        raise ValueError("Горизонт прогноза не может быть отрицательным.")

    earliest_biofix = min(request.biofix_date for request in requests)
    weather_provider = provider or OpenMeteoProvider()
    weather = await weather_provider.fetch(
        latitude,
        longitude,
        season_start=earliest_biofix,
    )
    calculation_day = today or local_today(weather.meta.timezone)

    return tuple(
        PestMonitorResult(
            request=request,
            outlook=calculate_pest_outlook(
                weather.daily,
                request.pest_key,
                biofix_date=request.biofix_date,
                today=calculation_day,
                forecast_horizon_days=forecast_horizon_days,
            ),
            timezone=weather.meta.timezone,
            source=weather.meta.source,
            retrieved_at=weather.meta.retrieved_at,
        )
        for request in requests
    )
