from __future__ import annotations

from datetime import date

from src.api.open_meteo_late_blight import OpenMeteoLateBlightProvider
from src.application.ports.late_blight import LateBlightWeatherProvider
from src.domain.late_blight import LateBlightOutlook, calculate_hutton_outlook
from src.domain.season import local_today


async def generate_potato_late_blight_screening(
    latitude: float,
    longitude: float,
    *,
    provider: LateBlightWeatherProvider | None = None,
    today: date | None = None,
) -> LateBlightOutlook:
    """Return a potato-only Hutton weather suitability screen.

    This service intentionally does not infer pathogen presence, infection,
    severity, yield loss or a treatment requirement.
    """

    resolved_provider = provider or OpenMeteoLateBlightProvider()
    weather = await resolved_provider.fetch(latitude, longitude)
    calculation_day = today or local_today(weather.meta.timezone)
    return calculate_hutton_outlook(weather, today=calculation_day)
