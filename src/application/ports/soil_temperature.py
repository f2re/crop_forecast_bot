from __future__ import annotations

from datetime import date
from typing import Protocol

from src.domain.soil_temperature import SoilTemperatureData


class SoilTemperatureProviderError(RuntimeError):
    """A provider could not supply a valid soil-temperature series."""


class SoilTemperatureProvider(Protocol):
    async def fetch(
        self,
        latitude: float,
        longitude: float,
        *,
        season_start: date | None = None,
    ) -> SoilTemperatureData:
        """Return a typed near-surface soil-temperature series."""
