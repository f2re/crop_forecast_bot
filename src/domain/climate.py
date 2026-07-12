from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd


@dataclass(frozen=True, slots=True)
class ClimateReferenceMeta:
    latitude: float
    longitude: float
    elevation_m: float
    timezone: str
    source: str
    model: str
    reference_start: date
    reference_end: date
    comparison_start: date
    comparison_end: date
    retrieved_at: datetime
    reference_cache_ttl_seconds: int
    current_cache_ttl_seconds: int
    spatial_resolution_km: float | None = None


@dataclass(slots=True)
class ClimateReferenceData:
    meta: ClimateReferenceMeta
    reference_daily: pd.DataFrame
    current_daily: pd.DataFrame
