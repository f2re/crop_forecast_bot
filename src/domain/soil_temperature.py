from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd


@dataclass(frozen=True, slots=True)
class SoilTemperatureMeta:
    latitude: float
    longitude: float
    elevation_m: float
    timezone: str
    source: str
    model: str
    depth_label: str
    retrieved_at: datetime
    cache_ttl_seconds: int
    spatial_resolution_km: float | None = None


@dataclass(frozen=True, slots=True)
class SoilTemperatureCoverage:
    requested_start: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    history_source: str | None = None
    start_covered: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class SoilTemperatureData:
    """Daily temperature of a model soil layer.

    ``daily`` uses the same temperature column names as the pest calculation
    core (``t_min``, ``t_max``, ``t_mean``), but metadata explicitly identifies
    the driver as a soil layer. Values are model-grid estimates, not sensor
    measurements at the field.
    """

    meta: SoilTemperatureMeta
    daily: pd.DataFrame
    forecast_days: int
    coverage: SoilTemperatureCoverage
