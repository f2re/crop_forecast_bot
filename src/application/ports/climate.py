from __future__ import annotations

from datetime import date
from typing import Protocol

from src.domain.climate import ClimateReferenceData


class ClimateProviderError(RuntimeError):
    """A climate provider could not supply valid homogeneous reanalysis series."""


class ClimateProvider(Protocol):
    async def fetch_reference(
        self,
        latitude: float,
        longitude: float,
        *,
        timezone: str,
        season_start: date,
    ) -> ClimateReferenceData:
        """Return fixed reference and current-season series from one model."""
