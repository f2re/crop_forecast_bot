from __future__ import annotations

from typing import Protocol

from src.domain.risk import EnsembleForecastData


class RiskForecastProviderError(RuntimeError):
    """An ensemble provider could not return a scientifically usable dataset."""


class RiskForecastProvider(Protocol):
    async def fetch(self, latitude: float, longitude: float) -> EnsembleForecastData:
        """Return one row per local date and ensemble member."""
        ...
