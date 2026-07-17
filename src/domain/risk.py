from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

import pandas as pd

RiskLevel = Literal["watch", "elevated", "high"]
RiskType = Literal["frost", "heat", "heavy_rain", "strong_wind", "convection"]


@dataclass(frozen=True, slots=True)
class EnsembleForecastMeta:
    latitude: float
    longitude: float
    elevation_m: float | None
    timezone: str
    source: str
    model: str
    retrieved_at: datetime
    member_count: int
    forecast_days: int
    spatial_resolution_km: float | None = None
    cache_ttl_seconds: int | None = None


@dataclass(slots=True)
class EnsembleForecastData:
    """One row per local calendar day and ensemble member."""

    meta: EnsembleForecastMeta
    daily_members: pd.DataFrame


@dataclass(frozen=True, slots=True)
class RiskEvent:
    risk_type: RiskType
    event_date: date
    lead_days: int
    level: RiskLevel
    members_exceeding: int
    valid_members: int
    member_fraction: float
    severe_members_exceeding: int
    severe_member_fraction: float
    threshold: float
    severe_threshold: float
    unit: str
    p10: float
    median: float
    p90: float
    model: str
    reliability_note: str
    action: str
    caveat: str


@dataclass(frozen=True, slots=True)
class RiskOutlook:
    available: bool
    status: str
    events: tuple[RiskEvent, ...] = field(default_factory=tuple)
    model: str | None = None
    member_count: int = 0
    valid_days: int = 0
    generated_for_date: date | None = None
    method_reference: str = (
        "сырая доля членов ансамбля k/n, пересёкших операционный порог; "
        "это не откалиброванная вероятность события"
    )
