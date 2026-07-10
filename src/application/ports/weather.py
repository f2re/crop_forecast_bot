from __future__ import annotations

from datetime import date
from typing import Protocol

from src.domain.weather import AgroWeatherData


class WeatherProviderError(RuntimeError):
    """An external weather provider could not supply a valid dataset."""


class WeatherProvider(Protocol):
    async def fetch(
        self,
        latitude: float,
        longitude: float,
        *,
        season_start: date | None = None,
    ) -> AgroWeatherData:
        """Return operational weather, optionally extended to a season start."""
