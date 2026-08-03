from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

from src.agro.pest_phenology import calculate_pest_outlook
from src.api.open_meteo import OpenMeteoProvider
from src.api.open_meteo_soil import OpenMeteoSoilTemperatureProvider
from src.application.ports.soil_temperature import SoilTemperatureProvider
from src.application.ports.weather import WeatherProvider
from src.domain.pests import PestOutlook, get_pest_model
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
    soil_provider: SoilTemperatureProvider | None = None,
    today: date | None = None,
    forecast_horizon_days: int = 7,
) -> tuple[PestMonitorResult, ...]:
    """Evaluate crop-pest monitors using the driver declared by each model.

    Air-driven models share one ordinary weather request. Soil-driven models
    share one 0–7 cm soil-temperature request. The service estimates only
    temperature-dependent development; it does not infer presence, abundance,
    damage or a treatment requirement.
    """

    if not requests:
        return ()
    if forecast_horizon_days < 0:
        raise ValueError("Горизонт прогноза не может быть отрицательным.")

    indexed = list(enumerate(requests))
    air_requests = [
        (index, request)
        for index, request in indexed
        if get_pest_model(request.pest_key).temperature_driver == "air_2m"
    ]
    soil_requests = [
        (index, request)
        for index, request in indexed
        if get_pest_model(request.pest_key).temperature_driver == "soil_0_to_7cm"
    ]
    results: dict[int, PestMonitorResult] = {}

    if air_requests:
        earliest = min(request.biofix_date for _, request in air_requests)
        weather_provider = provider or OpenMeteoProvider()
        weather = await weather_provider.fetch(
            latitude,
            longitude,
            season_start=earliest,
        )
        calculation_day = today or local_today(weather.meta.timezone)
        for index, request in air_requests:
            results[index] = PestMonitorResult(
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

    if soil_requests:
        earliest = min(request.biofix_date for _, request in soil_requests)
        resolved_soil_provider = (
            soil_provider or OpenMeteoSoilTemperatureProvider()
        )
        soil = await resolved_soil_provider.fetch(
            latitude,
            longitude,
            season_start=earliest,
        )
        calculation_day = today or local_today(soil.meta.timezone)
        for index, request in soil_requests:
            results[index] = PestMonitorResult(
                request=request,
                outlook=calculate_pest_outlook(
                    soil.daily,
                    request.pest_key,
                    biofix_date=request.biofix_date,
                    today=calculation_day,
                    forecast_horizon_days=forecast_horizon_days,
                ),
                timezone=soil.meta.timezone,
                source=soil.meta.source,
                retrieved_at=soil.meta.retrieved_at,
            )

    return tuple(results[index] for index in range(len(requests)))
