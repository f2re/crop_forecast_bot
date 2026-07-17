"""Open-Meteo GFS ensemble adapter for medium-range weather-risk screening.

The adapter exposes individual ensemble members. It does not convert member
fractions into calibrated probabilities and does not diagnose hail.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import requests_cache
from retry_requests import retry

from config.settings import get_settings
from src.application.ports.risk import RiskForecastProvider, RiskForecastProviderError
from src.domain.risk import EnsembleForecastData, EnsembleForecastMeta

logger = logging.getLogger(__name__)

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
ENSEMBLE_MODEL = "gfs_seamless"
ENSEMBLE_FORECAST_DAYS = 16
ENSEMBLE_SOURCE = "NOAA GFS Ensemble via Open-Meteo Ensemble API"
_CACHE_TTL_SECONDS = 3 * 60 * 60
_MAX_CONCURRENT_REQUESTS = 2
_REQUEST_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

_DAILY_VARIABLES = (
    "temperature_2m_min",
    "temperature_2m_max",
    "precipitation_sum",
    "wind_gusts_10m_max",
    "cape_max",
)
_ALIASES = {
    "temperature_2m_min": "t_min_c",
    "temperature_2m_max": "t_max_c",
    "precipitation_sum": "precip_mm",
    "wind_gusts_10m_max": "wind_gust_ms",
    "cape_max": "cape_j_kg",
}
_MEMBER_COLUMN = re.compile(r"^(?P<variable>.+?)(?:_member(?P<member>\d+))?$")


class OpenMeteoEnsembleError(RiskForecastProviderError):
    """Open-Meteo Ensemble API returned no scientifically usable data."""


class _TimeoutCachedSession(requests_cache.CachedSession):
    def request(self, method: str, url: str, *args: Any, **kwargs: Any):
        kwargs.setdefault("timeout", (5, 60))
        return super().request(method, url, *args, **kwargs)


def _ensemble_cache_path() -> Path:
    base = get_settings().open_meteo_cache_path
    return Path(f"{base}-ensemble")


@lru_cache(maxsize=1)
def _get_http_session():
    cache_path = _ensemble_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    session = _TimeoutCachedSession(
        str(cache_path),
        expire_after=_CACHE_TTL_SECONDS,
    )
    return retry(
        session,
        retries=4,
        backoff_factor=0.75,
        status_to_retry=(429, 500, 502, 503, 504),
    )


def _close_resources_sync() -> None:
    if _get_http_session.cache_info().currsize:
        _get_http_session().close()
    _get_http_session.cache_clear()


async def close_open_meteo_ensemble_resources() -> None:
    await asyncio.to_thread(_close_resources_sync)


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _parse_member_column(name: str) -> tuple[str, str] | None:
    match = _MEMBER_COLUMN.match(name)
    if match is None:
        return None
    variable = match.group("variable")
    if variable not in _ALIASES:
        return None
    member_number = match.group("member")
    member_id = "control" if member_number is None else f"member{int(member_number):02d}"
    return variable, member_id


def parse_ensemble_payload(
    payload: dict[str, Any],
    *,
    model: str = ENSEMBLE_MODEL,
    retrieved_at: datetime | None = None,
) -> EnsembleForecastData:
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise OpenMeteoEnsembleError("Provider response has no daily block")

    raw_dates = daily.get("time")
    if not isinstance(raw_dates, list) or not raw_dates:
        raise OpenMeteoEnsembleError("Provider response has no daily time axis")
    dates = pd.to_datetime(raw_dates, errors="coerce")
    if dates.isna().any():
        raise OpenMeteoEnsembleError("Provider returned an invalid local date")

    records: dict[tuple[object, str], dict[str, Any]] = {}
    present_variables: set[str] = set()
    for column, raw_values in daily.items():
        if column == "time":
            continue
        parsed = _parse_member_column(str(column))
        if parsed is None:
            continue
        variable, member_id = parsed
        if not isinstance(raw_values, list) or len(raw_values) != len(dates):
            raise OpenMeteoEnsembleError(
                f"Invalid array length for ensemble variable {column}"
            )
        present_variables.add(variable)
        alias = _ALIASES[variable]
        for local_day, raw_value in zip(dates, raw_values, strict=True):
            key = (local_day.date(), member_id)
            row = records.setdefault(
                key,
                {"local_date": local_day.date(), "member_id": member_id},
            )
            row[alias] = _as_float(raw_value)

    missing_variables = set(_DAILY_VARIABLES).difference(present_variables)
    if missing_variables:
        raise OpenMeteoEnsembleError(
            "Provider omitted variables: " + ", ".join(sorted(missing_variables))
        )
    if not records:
        raise OpenMeteoEnsembleError("Provider returned no ensemble members")

    frame = pd.DataFrame(records.values()).sort_values(["local_date", "member_id"])
    member_count = int(frame["member_id"].nunique())
    if member_count < 2:
        raise OpenMeteoEnsembleError("Provider returned fewer than two ensemble members")

    timezone_name = str(payload.get("timezone") or "UTC")
    elevation = _as_float(payload.get("elevation"))
    meta = EnsembleForecastMeta(
        latitude=float(payload.get("latitude")),
        longitude=float(payload.get("longitude")),
        elevation_m=elevation,
        timezone=timezone_name,
        source=ENSEMBLE_SOURCE,
        model=model,
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
        member_count=member_count,
        forecast_days=int(frame["local_date"].nunique()),
        spatial_resolution_km=None,
        cache_ttl_seconds=_CACHE_TTL_SECONDS,
    )
    return EnsembleForecastData(meta=meta, daily_members=frame.reset_index(drop=True))


class OpenMeteoEnsembleProvider(RiskForecastProvider):
    async def fetch(self, latitude: float, longitude: float) -> EnsembleForecastData:
        if not -90 <= latitude <= 90:
            raise ValueError(f"Latitude outside [-90, 90]: {latitude}")
        if not -180 <= longitude <= 180:
            raise ValueError(f"Longitude outside [-180, 180]: {longitude}")

        async with _REQUEST_SEMAPHORE:
            try:
                return await asyncio.to_thread(_fetch_sync, latitude, longitude)
            except (ValueError, OpenMeteoEnsembleError):
                raise
            except Exception as exc:
                logger.exception(
                    "Open-Meteo ensemble request failed for %.5f, %.5f",
                    latitude,
                    longitude,
                )
                raise OpenMeteoEnsembleError(str(exc)) from exc


def _fetch_sync(latitude: float, longitude: float) -> EnsembleForecastData:
    retrieved_at = datetime.now(timezone.utc)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "models": ENSEMBLE_MODEL,
        "forecast_days": ENSEMBLE_FORECAST_DAYS,
        "daily": ",".join(_DAILY_VARIABLES),
        "timezone": "auto",
        "wind_speed_unit": "ms",
        "cell_selection": "land",
    }
    response = _get_http_session().get(ENSEMBLE_URL, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise OpenMeteoEnsembleError("Provider returned a non-object JSON response")
    data = parse_ensemble_payload(
        payload,
        model=ENSEMBLE_MODEL,
        retrieved_at=retrieved_at,
    )
    logger.info(
        "Open-Meteo ensemble OK: %.3f %.3f, %s members, %s days, model %s",
        data.meta.latitude,
        data.meta.longitude,
        data.meta.member_count,
        data.meta.forecast_days,
        data.meta.model,
    )
    return data
