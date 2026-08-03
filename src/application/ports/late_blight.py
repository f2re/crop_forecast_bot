from __future__ import annotations

from typing import Protocol

from src.domain.late_blight import LateBlightWeatherData


class LateBlightWeatherProviderError(RuntimeError):
    """A late-blight weather provider could not return a valid hourly series."""


class LateBlightWeatherProvider(Protocol):
    async def fetch(
        self,
        latitude: float,
        longitude: float,
    ) -> LateBlightWeatherData: ...
