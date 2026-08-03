"""Open-Meteo adapter for near-surface soil temperature.

The operational part uses the ECMWF endpoint and the 0–7 cm soil layer. When a
longer period is requested, ERA5-Land supplies the historical 0–7 cm layer.
Both are model-grid estimates; neither is a thermometer installed in the field.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import requests_cache
from retry_requests import retry

from config.settings import get_settings
from src.api.open_meteo import OpenMeteoError
from src.application.ports.soil_temperature import (
    SoilTemperatureProvider,
    SoilTemperatureProviderError,
)
from src.domain.soil_temperature import (
    SoilTemperatureCoverage,
    SoilTemperatureData,
    SoilTemperatureMeta,
)

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/ecmwf"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_VARIABLE = "soil_temperature_0_to_7cm"
HISTORY_VARIABLE = "soil_temperature_0_to_7cm"
PAST_DAYS = 14
FORECAST_DAYS = 7
MAX_HISTORY_DAYS = 730
_CACHE_TTL_SECONDS = 60 * 60
_HISTORY_CACHE_TTL_SECONDS = 24 * 60 * 60
_MIN_VALID_HOURS = 18
_REQUEST_SEMAPHORE = asyncio.Semaphore(2)
_FORECAST_SOURCE = "Open-Meteo ECMWF IFS, температура почвы 0–7 см"
_HISTORY_SOURCE = "Open-Meteo ERA5-Land, температура почвы 0–7 см"


class OpenMeteoSoilTemperatureError(
    OpenMeteoError,
    SoilTemperatureProviderError,
):
    """Open-Meteo did not return a valid soil-temperature series."""


class _TimeoutCachedSession(requests_cache.CachedSession):
    def request(self, method: str, url: str, *args: Any, **kwargs: Any):
        kwargs.setdefault("timeout", (5, 45))
        return super().request(method, url, *args, **kwargs)


def _cache_path() -> Path:
    base = get_settings().open_meteo_cache_path
    return Path(f"{base}-soil-temperature")


def _session() -> requests_cache.CachedSession:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cached = _TimeoutCachedSession(
        str(path),
        expire_after=_CACHE_TTL_SECONDS,
    )
    return retry(
        cached,
        retries=4,
        backoff_factor=0.5,
        status_to_retry=(429, 500, 502, 503, 504),
    )


def _timezone_name(raw_value: Any) -> str:
    value = str(raw_value or "UTC")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown soil-temperature timezone %r; using UTC", value)
        return "UTC"
    return value


def _get_json(
    session: requests_cache.CachedSession,
    url: str,
    *,
    params: dict[str, Any],
    expire_after: int,
) -> dict[str, Any]:
    response = session.get(
        url,
        params=params,
        timeout=(5, 45),
        expire_after=expire_after,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise OpenMeteoSoilTemperatureError("Provider returned a non-object JSON payload")
    if payload.get("error"):
        raise OpenMeteoSoilTemperatureError(
            str(payload.get("reason") or "Open-Meteo soil-temperature error")
        )
    return payload


def _parse_hourly_payload(
    payload: dict[str, Any],
    *,
    variable: str,
    source: str,
    history: bool,
) -> tuple[pd.DataFrame, str]:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise OpenMeteoSoilTemperatureError("Hourly soil-temperature block is absent")
    raw_times = hourly.get("time")
    raw_values = hourly.get(variable)
    if not isinstance(raw_times, list) or not isinstance(raw_values, list):
        raise OpenMeteoSoilTemperatureError(
            f"Hourly variable {variable} is absent from provider response"
        )
    if len(raw_times) != len(raw_values):
        raise OpenMeteoSoilTemperatureError(
            f"Hourly variable {variable} has an invalid length"
        )

    timezone_name = _timezone_name(payload.get("timezone"))
    zone = ZoneInfo(timezone_name)
    local_times = pd.DatetimeIndex(pd.to_datetime(raw_times, errors="coerce"))
    if local_times.tz is None:
        local_times = local_times.tz_localize(
            zone,
            ambiguous=False,
            nonexistent="shift_forward",
        )
    else:
        local_times = local_times.tz_convert(zone)

    frame = pd.DataFrame(
        {
            "date": local_times.tz_convert("UTC"),
            "local_date": list(local_times.date),
            "temperature": pd.to_numeric(raw_values, errors="coerce"),
        }
    ).dropna(subset=["date"])
    if frame.empty:
        raise OpenMeteoSoilTemperatureError("Soil-temperature time series is empty")

    grouped = (
        frame.groupby("local_date", as_index=False)
        .agg(
            t_min=("temperature", "min"),
            t_max=("temperature", "max"),
            t_mean=("temperature", "mean"),
            valid_hours=("temperature", "count"),
        )
        .sort_values("local_date")
        .reset_index(drop=True)
    )
    incomplete = grouped["valid_hours"] < _MIN_VALID_HOURS
    grouped.loc[incomplete, ["t_min", "t_max", "t_mean"]] = pd.NA
    grouped["date"] = [
        pd.Timestamp(datetime.combine(day, time.min, tzinfo=zone)).tz_convert("UTC")
        for day in grouped["local_date"]
    ]

    today_local = datetime.now(zone).date()
    if history:
        grouped["data_kind"] = "reanalysis"
    else:
        grouped["data_kind"] = [
            (
                "operational_past"
                if day < today_local
                else "current_forecast" if day == today_local else "forecast"
            )
            for day in grouped["local_date"]
        ]
    grouped["data_source"] = source
    return grouped[
        [
            "date",
            "local_date",
            "t_min",
            "t_max",
            "t_mean",
            "valid_hours",
            "data_kind",
            "data_source",
        ]
    ], timezone_name


def _forecast_params(latitude: float, longitude: float) -> dict[str, Any]:
    return {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": FORECAST_VARIABLE,
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "timezone": "auto",
        "cell_selection": "land",
    }


def _history_params(
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
    timezone_name: str,
) -> dict[str, Any]:
    return {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": HISTORY_VARIABLE,
        "models": "era5_land",
        "timezone": timezone_name,
        "cell_selection": "land",
    }


def _merge_daily(history: pd.DataFrame, forecast: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return forecast.copy()
    left = history.copy()
    right = forecast.copy()
    left["_priority"] = 0
    right["_priority"] = 1
    combined = pd.concat([left, right], ignore_index=True, sort=False)
    combined = combined.sort_values(["local_date", "_priority"])
    combined = combined.drop_duplicates("local_date", keep="last")
    return (
        combined.drop(columns=["_priority"])
        .sort_values("local_date")
        .reset_index(drop=True)
    )


def _fetch_sync(
    latitude: float,
    longitude: float,
    season_start: date | None,
) -> SoilTemperatureData:
    retrieved_at = datetime.now(timezone.utc)
    session = _session()
    try:
        forecast_payload = _get_json(
            session,
            FORECAST_URL,
            params=_forecast_params(latitude, longitude),
            expire_after=_CACHE_TTL_SECONDS,
        )
        forecast, timezone_name = _parse_hourly_payload(
            forecast_payload,
            variable=FORECAST_VARIABLE,
            source=_FORECAST_SOURCE,
            history=False,
        )

        zone = ZoneInfo(timezone_name)
        today_local = datetime.now(zone).date()
        if season_start is not None and season_start > today_local:
            raise ValueError("Дата начала температурного ряда находится в будущем")

        notes: list[str] = [
            "значения относятся к модельному слою 0–7 см, а не к датчику на поле"
        ]
        history = forecast.iloc[0:0].copy()
        history_source: str | None = None
        forecast_start = min(forecast["local_date"])
        if season_start is not None and season_start < forecast_start:
            earliest_allowed = today_local - timedelta(days=MAX_HISTORY_DAYS)
            history_start = max(season_start, earliest_allowed)
            history_end = forecast_start - timedelta(days=1)
            if history_start > season_start:
                notes.append(
                    f"история ограничена последними {MAX_HISTORY_DAYS} сутками"
                )
            if history_start <= history_end:
                history_payload = _get_json(
                    session,
                    ARCHIVE_URL,
                    params=_history_params(
                        latitude,
                        longitude,
                        history_start,
                        history_end,
                        timezone_name,
                    ),
                    expire_after=_HISTORY_CACHE_TTL_SECONDS,
                )
                history, history_timezone = _parse_hourly_payload(
                    history_payload,
                    variable=HISTORY_VARIABLE,
                    source=_HISTORY_SOURCE,
                    history=True,
                )
                if history_timezone != timezone_name:
                    raise OpenMeteoSoilTemperatureError(
                        "Forecast and historical soil series use different timezones"
                    )
                history_source = _HISTORY_SOURCE
                notes.append(
                    "историческая часть — ERA5-Land, текущая и будущая — ECMWF IFS"
                )

        daily = _merge_daily(history, forecast)
        actual_start = min(daily["local_date"]) if not daily.empty else None
        actual_end = max(daily["local_date"]) if not daily.empty else None
        start_covered = bool(
            season_start is not None
            and actual_start is not None
            and actual_start <= season_start
        )
        if season_start is not None and not start_covered:
            notes.append("ряд не покрывает запрошенную дату начала")

        valid = daily.dropna(subset=["t_min", "t_max", "t_mean"])
        if valid.empty:
            raise OpenMeteoSoilTemperatureError(
                "Provider returned no complete daily soil-temperature values"
            )

        source = _FORECAST_SOURCE
        model = "ecmwf_ifs_hres"
        if history_source is not None:
            source = f"{_HISTORY_SOURCE} + {_FORECAST_SOURCE}"
            model = "era5_land+ecmwf_ifs_hres"
        meta = SoilTemperatureMeta(
            latitude=float(forecast_payload.get("latitude", latitude)),
            longitude=float(forecast_payload.get("longitude", longitude)),
            elevation_m=float(forecast_payload.get("elevation", 0.0)),
            timezone=timezone_name,
            source=source,
            model=model,
            depth_label="модельный слой почвы 0–7 см",
            retrieved_at=retrieved_at,
            cache_ttl_seconds=_CACHE_TTL_SECONDS,
            spatial_resolution_km=9.0,
        )
        return SoilTemperatureData(
            meta=meta,
            daily=daily,
            forecast_days=FORECAST_DAYS,
            coverage=SoilTemperatureCoverage(
                requested_start=season_start,
                actual_start=actual_start,
                actual_end=actual_end,
                history_source=history_source,
                start_covered=start_covered,
                notes=tuple(dict.fromkeys(notes)),
            ),
        )
    finally:
        session.close()


class OpenMeteoSoilTemperatureProvider(SoilTemperatureProvider):
    async def fetch(
        self,
        latitude: float,
        longitude: float,
        *,
        season_start: date | None = None,
    ) -> SoilTemperatureData:
        if not -90 <= latitude <= 90:
            raise ValueError(f"Latitude outside [-90, 90]: {latitude}")
        if not -180 <= longitude <= 180:
            raise ValueError(f"Longitude outside [-180, 180]: {longitude}")

        async with _REQUEST_SEMAPHORE:
            try:
                return await asyncio.to_thread(
                    _fetch_sync,
                    latitude,
                    longitude,
                    season_start,
                )
            except (ValueError, OpenMeteoSoilTemperatureError):
                raise
            except Exception as exc:
                logger.exception(
                    "Open-Meteo soil-temperature request failed for %.5f, %.5f",
                    latitude,
                    longitude,
                )
                raise OpenMeteoSoilTemperatureError(str(exc)) from exc


_DEFAULT_PROVIDER = OpenMeteoSoilTemperatureProvider()


async def fetch_soil_temperature_data(
    latitude: float,
    longitude: float,
    *,
    season_start: date | None = None,
) -> SoilTemperatureData:
    return await _DEFAULT_PROVIDER.fetch(
        latitude,
        longitude,
        season_start=season_start,
    )
