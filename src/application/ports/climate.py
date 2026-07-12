from __future__ import annotations

from typing import Protocol

from src.domain.climate import ClimateReferenceData


class ClimateProviderError(RuntimeError):
    """A climate provider could not supply a valid reference series."""


class ClimateProvider(Protocol):
    async def fetch_reference(
        self,
        latitude: float,
        longitude: float,
        *,
        timezone: str,
    ) -> ClimateReferenceData:
        """Return a fixed, homogeneous multi-year reanalysis reference."""
