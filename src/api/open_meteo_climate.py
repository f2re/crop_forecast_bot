"""Fixed ERA5-Land climate reference through the Open-Meteo archive endpoint."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
CLIMATE_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
CLIMATE_SPATIAL_RESOLUTION_KM = 11.0


class OpenMeteoClimateError(ClimateProviderError):
    """Open-Meteo could not return the fixed ERA5-Land reference."""


class OpenMeteoClimateProvider(ClimateProvider):
    async def fetch_reference(
        self,
        latitude: float,
        longitude: float,
        *,
        timezone: str,
    ) -> ClimateReferenceData:
        if not -90 <= latitude <= 90:
            raise ValueError(f"Latitude outside [-90, 90]: {latitude}")
        if not -180 <= longitude <= 180:
            raise ValueError(f"Longitude outside [-180, 180]: {longitude}")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {timezone}") from exc

        async with _REQUEST_SEMAPHORE:
            try:
                return await asyncio.to_thread(
                    _fetch_climate_reference_sync,
                    latitude,
                    longitude,
                    timezone,
                )
            except (ValueError, OpenMeteoClimateError):
                raise
            except Exception as exc:
                logger.exception(
                    "ERA5-Land climate reference failed for %.5f, %.5f",
                    latitude,
                    longitude,
                )
                raise OpenMeteoClimateError(str(exc)) from exc


def _fetch_climate_reference_sync(
    latitude: float,
    longitude: float,
    timezone_name: str,
) -> ClimateReferenceData:
    retrieved_at = datetime.now(timezone.utc)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": REFERENCE_START.isoformat(),
        "end_date": REFERENCE_END.isoformat(),
        "daily": ",".join(
            [
                "temperature_2m_mean",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
            ]
        ),
        "timezone": timezone_name,
        "models": CLIMATE_MODEL,
        "cell_selection": "land",
    }
    response = _get_http_session().get(
        ARCHIVE_URL,
        params=params,
        timeout=(5, 90),
        expire_after=CLIMATE_CACHE_TTL_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    frame = _parse_history_payload(payload, timezone_name=timezone_name)
    frame["data_source"] = CLIMATE_SOURCE

    actual_start = min(frame["local_date"]) if not frame.empty else None
    actual_end = max(frame["local_date"]) if not frame.empty else None
    if actual_start != REFERENCE_START or actual_end != REFERENCE_END:
        raise OpenMeteoClimateError(
            "ERA5-Land reference does not cover the complete 1991-2020 period"
        )

    resolved_timezone = _timezone_name(payload.get("timezone") or timezone_name)
    raw_elevation = payload.get("elevation")
    elevation_m = float(raw_elevation) if raw_elevation is not None else float("nan")
    return ClimateReferenceData(
        meta=ClimateReferenceMeta(
            latitude=float(payload.get("latitude", latitude)),
            longitude=float(payload.get("longitude", longitude)),
            elevation_m=elevation_m,
            timezone=resolved_timezone,
            source=CLIMATE_SOURCE,
            model=CLIMATE_MODEL,
            reference_start=REFERENCE_START,
            reference_end=REFERENCE_END,
            retrieved_at=retrieved_at,
            cache_ttl_seconds=CLIMATE_CACHE_TTL_SECONDS,
            spatial_resolution_km=CLIMATE_SPATIAL_RESOLUTION_KM,
        ),
        daily=frame,
    )
