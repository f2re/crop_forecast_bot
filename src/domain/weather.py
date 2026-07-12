from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd


@dataclass(frozen=True, slots=True)
class WeatherMeta:
    latitude: float
    longitude: float
    elevation_m: float
    utc_offset_seconds: int
    timezone: str
    source: str
    model: str | None = None
    model_run: datetime | None = None
    retrieved_at: datetime | None = None
    cache_ttl_seconds: int | None = None
    spatial_resolution_km: float | None = None


@dataclass(frozen=True, slots=True)
class WeatherCoverage:
    """Describe which parts of the combined weather series are available."""

    requested_season_start: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    season_coverage_complete: bool = False
    history_source: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class AgroWeatherData:
    meta: WeatherMeta
    daily: pd.DataFrame
    hourly: pd.DataFrame
    past_days: int
    forecast_days: int
    coverage: WeatherCoverage
