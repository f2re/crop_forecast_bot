"""Homogeneous ERA5-Land current-season and 1991-2020 reference series."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from src.api.open_meteo import (
    ARCHIVE_URL,
    _REQUEST_SEMAPHORE,
    _get_http_session,
    _parse_history_payload,
    _timezone_name,
)
from src.application.ports.climate import ClimateProvider, ClimateProviderError
from src.domain.climate import ClimateReferenceData, ClimateReferenceMeta

logger = logging.getLogger(__name__)

REFERENCE_START = date(1991, 1, 1)
REFERENCE_END = date(2020, 12, 31)
CLIMATE_MODEL = "era5_land"
CLIMATE_SOURCE = "ERA5-Land via Open-Meteo Historical Weather API"
REFERENCE_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
CURRENT_CACHE_TTL_SECONDS = 6 * 60 * 60
CLIMATE_SPATIAL_RESOLUTION_KM = 11.0
_DAILY_VARIABLES = (
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "et0_fao_evapotranspiration",
)
_CORE_COLUMNS = ("t_mean", "precip_sum", "et0_sum")


class OpenMeteoClimateError(ClimateProviderError):
    """Open-Meteo could not return homogeneous ERA5-Land series."""


class OpenMeteoClimateProvider(ClimateProvider):
    async def fetch_reference(
        self,
        latitude: float,
        longitude: float,
        *,
        timezone: str,
        season_start: date,
    ) -> ClimateReferenceData:
        if not -90 <= latitude <= 90:
            raise ValueError(f"Latitude outside [-90, 90]: {latitude}")
        if not -180 <= longitude <= 180:
            raise ValueError(f"Longitude outside [-180, 180]: {longitude}")
        try:
            zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {timezone}") from exc

        comparison_end = datetime.now(zone).date() - timedelta(days=1)
        if season_start > comparison_end:
            raise OpenMeteoClimateError(
                "No completed local day is available after the season start"
            )

        async with _REQUEST_SEMAPHORE:
            try:
                return await asyncio.to_thread(
                    _fetch_climate_reference_sync,
                    latitude,
                    longitude,
                    timezone,
                    season_start,
                    comparison_end,
                )
            except (ValueError, OpenMeteoClimateError):
                raise
            except Exception as exc:
                logger.exception(
                    "ERA5-Land climate comparison failed for %.5f, %.5f",
                    latitude,
                    longitude,
                )
                raise OpenMeteoClimateError(str(exc)) from exc


def _request_history(
    latitude: float,
    longitude: float,
    timezone_name: str,
    *,
    start_date: date,
    end_date: date,
    cache_ttl_seconds: int,
) -> tuple[dict, pd.DataFrame]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(_DAILY_VARIABLES),
        "timezone": timezone_name,
        "models": CLIMATE_MODEL,
        "cell_selection": "land",
    }
    response = _get_http_session().get(
        ARCHIVE_URL,
        params=params,
        timeout=(5, 90),
        expire_after=cache_ttl_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    frame = _parse_history_payload(payload, timezone_name=timezone_name)
    frame["data_source"] = CLIMATE_SOURCE
    return payload, frame


def _fetch_climate_reference_sync(
    latitude: float,
    longitude: float,
    timezone_name: str,
    season_start: date,
    comparison_end: date,
) -> ClimateReferenceData:
    retrieved_at = datetime.now(timezone.utc)
    reference_payload, reference_frame = _request_history(
        latitude,
        longitude,
        timezone_name,
        start_date=REFERENCE_START,
        end_date=REFERENCE_END,
        cache_ttl_seconds=REFERENCE_CACHE_TTL_SECONDS,
    )
    current_payload, current_frame = _request_history(
        latitude,
        longitude,
        timezone_name,
        start_date=season_start,
        end_date=comparison_end,
        cache_ttl_seconds=CURRENT_CACHE_TTL_SECONDS,
    )

    reference_start = (
        min(reference_frame["local_date"]) if not reference_frame.empty else None
    )
    reference_end = (
        max(reference_frame["local_date"]) if not reference_frame.empty else None
    )
    if reference_start != REFERENCE_START or reference_end != REFERENCE_END:
        raise OpenMeteoClimateError(
            "ERA5-Land reference does not cover the complete 1991-2020 period"
        )

    # ERA5-Land is published with latency. Open-Meteo may return dated rows whose
    # requested variables are all null near the end of the interval. Remove only
    # those fully unavailable rows; partial rows stay visible to downstream QC.
    current_frame = current_frame.dropna(subset=list(_CORE_COLUMNS), how="all").copy()
    if current_frame.empty:
        raise OpenMeteoClimateError("ERA5-Land current-season series is unavailable")
    current_start = min(current_frame["local_date"])
    current_end = max(current_frame["local_date"])
    if current_start != season_start:
        raise OpenMeteoClimateError(
            "ERA5-Land current-season series does not reach the season start"
        )

    resolved_timezone = _timezone_name(
        reference_payload.get("timezone") or timezone_name
    )
    current_timezone = _timezone_name(current_payload.get("timezone") or timezone_name)
    if current_timezone != resolved_timezone:
        raise OpenMeteoClimateError("ERA5-Land responses use inconsistent timezones")

    raw_elevation = reference_payload.get("elevation")
    if raw_elevation is None:
        raise OpenMeteoClimateError("ERA5-Land response does not contain elevation")

    return ClimateReferenceData(
        meta=ClimateReferenceMeta(
            latitude=float(reference_payload.get("latitude", latitude)),
            longitude=float(reference_payload.get("longitude", longitude)),
            elevation_m=float(raw_elevation),
            timezone=resolved_timezone,
            source=CLIMATE_SOURCE,
            model=CLIMATE_MODEL,
            reference_start=REFERENCE_START,
            reference_end=REFERENCE_END,
            comparison_start=current_start,
            comparison_end=current_end,
            retrieved_at=retrieved_at,
            reference_cache_ttl_seconds=REFERENCE_CACHE_TTL_SECONDS,
            current_cache_ttl_seconds=CURRENT_CACHE_TTL_SECONDS,
            spatial_resolution_km=CLIMATE_SPATIAL_RESOLUTION_KM,
        ),
        reference_daily=reference_frame,
        current_daily=current_frame.reset_index(drop=True),
    )
