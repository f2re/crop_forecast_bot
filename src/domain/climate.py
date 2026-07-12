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
    retrieved_at: datetime
    cache_ttl_seconds: int
    spatial_resolution_km: float | None = None


@dataclass(slots=True)
class ClimateReferenceData:
    meta: ClimateReferenceMeta
    daily: pd.DataFrame
