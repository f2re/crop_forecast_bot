from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass(frozen=True, slots=True)
class WeatherMeta:
    """Provider grid metadata and its relation to the requested field."""

    latitude: float
    longitude: float
    elevation_m: float | None
    utc_offset_seconds: int
    timezone: str
    source: str
    requested_latitude: float | None = None
    requested_longitude: float | None = None
    grid_distance_km: float | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class WeatherCoverage:
    """Describe which parts of the combined weather series are available."""

    requested_season_start: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    season_coverage_complete: bool = False
    history_source: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
    completed_days: int = 0
    forecast_days: int = 0


@dataclass(slots=True)
class AgroWeatherData:
    meta: WeatherMeta
    daily: pd.DataFrame
    hourly: pd.DataFrame
    past_days: int
    forecast_days: int
    coverage: WeatherCoverage
