"""Open-Meteo weather adapter with explicit provenance and fail-closed validation.

The adapter uses two real provider endpoints:

* Forecast API for the current day, short operational past and future forecast.
* Historical Weather API for an explicitly requested season extension.

Rows are labelled as ``reanalysis``, ``operational_past`` or ``forecast``.
The current local calendar day is treated as provisional forecast data, never as
a completed observation. Provider failures are explicit and no synthetic values
are generated.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import requests_cache
from retry_requests import retry

from config.settings import get_settings
from src.application.ports.weather import WeatherProvider, WeatherProviderError
from src.domain.weather import AgroWeatherData, WeatherCoverage, WeatherMeta

logger = logging.getLogger(__name__)

PAST_DAYS = 14
FORECAST_DAYS = 7
MAX_SEASON_HISTORY_DAYS = 730
MAX_GRID_DISTANCE_KM = 50.0
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_MAX_CONCURRENT_REQUESTS = 4
_REQUEST_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
_HISTORY_SOURCE = "Open-Meteo Historical Weather API (reanalysis Best Match)"
_FORECAST_SOURCE = "Open-Meteo Forecast API (Best Match weather models)"


class OpenMeteoError(WeatherProviderError):
    """Open-Meteo could not return a scientifically usable dataset."""


class _TimeoutCachedSession(requests_cache.CachedSession):
    """Cached requests session with a mandatory connect/read timeout."""

    def request(self, method: str, url: str, *args: Any, **kwargs: Any):
        kwargs.setdefault("timeout", (5, 45))
        return super().request(method, url, *args, **kwargs)


def _timezone_name(raw_value: Any) -> str:
    value = str(raw_value or "UTC")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        logger.warning("Provider returned unknown timezone %r; using UTC", value)
        return "UTC"
    return value


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    radius_km = 6371.0088
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


@lru_cache(maxsize=1)
def _get_http_session():
    cache_path = get_settings().open_meteo_cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cached = _TimeoutCachedSession(str(cache_path), expire_after=3600)
    return retry(
        cached,
        retries=4,
        backoff_factor=0.5,
        status_to_retry=(429, 500, 502, 503, 504),
    )


def close_open_meteo_session() -> None:
    """Close the process-wide requests session during application shutdown."""

    if _get_http_session.cache_info().currsize:
        _get_http_session().close()
        _get_http_session.cache_clear()


def _request_json(
    url: str,
    *,
    params: dict[str, Any],
    expire_after: int,
) -> dict[str, Any]:
    response = _get_http_session().get(
        url,
        params=params,
        expire_after=expire_after,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise OpenMeteoError("Provider returned a non-object JSON response")
    if payload.get("error"):
        raise OpenMeteoError(str(payload.get("reason") or "Open-Meteo API error"))
    return payload


class OpenMeteoProvider(WeatherProvider):
    async def fetch(
        self,
        latitude: float,
        longitude: float,
        *,
        season_start: date | None = None,
    ) -> AgroWeatherData:
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
            except (ValueError, OpenMeteoError):
                raise
            except Exception as exc:
                logger.exception(
                    "Open-Meteo request failed for %.5f, %.5f",
                    latitude,
                    longitude,
                )
                raise OpenMeteoError(str(exc)) from exc


_DEFAULT_PROVIDER = OpenMeteoProvider()


async def fetch_agro_data(
    lat: float,
    lon: float,
    *,
    season_start: date | None = None,
) -> AgroWeatherData:
    """Compatibility wrapper around the typed provider adapter."""

    return await _DEFAULT_PROVIDER.fetch(lat, lon, season_start=season_start)


def _fetch_sync(
    lat: float,
    lon: float,
    season_start: date | None,
) -> AgroWeatherData:
    forecast = _fetch_forecast_sync(lat, lon)
    daily = forecast.daily.copy()
    notes: list[str] = list(forecast.coverage.notes)
    history_source: str | None = None

    timezone_name = forecast.meta.timezone
    zone = ZoneInfo(timezone_name)
    forecast_start_local = min(daily["local_date"])
    today_local = pd.Timestamp.now(tz=zone).date()

    if season_start is not None and season_start < forecast_start_local:
        earliest_allowed = today_local - timedelta(days=MAX_SEASON_HISTORY_DAYS)
        history_start = max(season_start, earliest_allowed)
        history_end = forecast_start_local - timedelta(days=1)
        if history_start > season_start:
            notes.append(
                "начало сезона старше поддерживаемого окна; "
                f"реанализ ограничен {MAX_SEASON_HISTORY_DAYS} сутками"
            )
        if history_start <= history_end:
            try:
                history = _fetch_history_sync(
                    lat,
                    lon,
                    history_start,
                    history_end,
                    timezone_name,
                )
                daily = _merge_daily(history, daily, timezone_name)
                history_source = _HISTORY_SOURCE
            except Exception as exc:
                logger.warning(
                    "Season history unavailable for %.5f, %.5f: %s",
                    lat,
                    lon,
                    exc,
                )
                notes.append(
                    "сезонный реанализ недоступен; использовано короткое "
                    "оперативное окно"
                )

    actual_start = min(daily["local_date"]) if not daily.empty else None
    actual_end = max(daily["local_date"]) if not daily.empty else None
    season_complete = bool(
        season_start is not None
        and actual_start is not None
        and actual_start <= season_start
    )
    if season_start is not None and not season_complete:
        notes.append(
            "ряд не покрывает дату начала сезона; ГДД будут показаны "
            "только за доступный период"
        )

    completed_days = int(
        daily["data_kind"].isin(
            {"observation", "reanalysis", "operational_past"}
        ).sum()
    )
    forecast_days = int((daily["data_kind"] == "forecast").sum())
    return AgroWeatherData(
        meta=forecast.meta,
        daily=daily,
        hourly=forecast.hourly,
        past_days=PAST_DAYS,
        forecast_days=FORECAST_DAYS,
        coverage=WeatherCoverage(
            requested_season_start=season_start,
            actual_start=actual_start,
            actual_end=actual_end,
            season_coverage_complete=season_complete,
            history_source=history_source,
            notes=tuple(dict.fromkeys(notes)),
            completed_days=completed_days,
            forecast_days=forecast_days,
        ),
    )


def _forecast_params(lat: float, lon: float) -> dict[str, Any]:
    return {
        "latitude": lat,
        "longitude": lon,
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "hourly": ",".join(
            [
                "temperature_2m",
                "precipitation",
                "et0_fao_evapotranspiration",
                "soil_moisture_0_to_1cm",
            ]
        ),
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "temperature_2m_mean",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
                "wind_speed_10m_max",
            ]
        ),
        "timezone": "auto",
        "cell_selection": "land",
    }


def _fetch_forecast_sync(lat: float, lon: float) -> AgroWeatherData:
    payload = _request_json(
        FORECAST_URL,
        params=_forecast_params(lat, lon),
        expire_after=3600,
    )
    return _parse_forecast_payload(
        payload,
        requested_latitude=lat,
        requested_longitude=lon,
    )


def _values(block: dict[str, Any], name: str, length: int) -> list[Any]:
    values = block.get(name)
    if values is None:
        return [float("nan")] * length
    if not isinstance(values, list) or len(values) != length:
        raise OpenMeteoError(f"Variable {name} has an invalid length")
    return values


def _parse_local_times(
    values: list[Any],
    timezone_name: str,
) -> pd.DatetimeIndex:
    if not values:
        return pd.DatetimeIndex([], tz="UTC")
    local = pd.DatetimeIndex(pd.to_datetime(values, errors="coerce"))
    if local.isna().any():
        raise OpenMeteoError("Provider returned invalid timestamps")
    if local.tz is None:
        local = local.tz_localize(
            ZoneInfo(timezone_name),
            ambiguous=False,
            nonexistent="shift_forward",
        )
    return local.tz_convert("UTC")


def _parse_forecast_payload(
    payload: dict[str, Any],
    *,
    requested_latitude: float,
    requested_longitude: float,
) -> AgroWeatherData:
    timezone_name = _timezone_name(payload.get("timezone"))
    zone = ZoneInfo(timezone_name)
    daily = payload.get("daily")
    if not isinstance(daily, dict) or not daily.get("time"):
        raise OpenMeteoError("Forecast response does not contain daily data")

    local_day_values = pd.to_datetime(daily["time"], errors="coerce")
    if pd.isna(local_day_values).any():
        raise OpenMeteoError("Forecast response contains invalid daily dates")
    local_days = [timestamp.date() for timestamp in local_day_values]
    dates_utc = _parse_local_times(daily["time"], timezone_name)
    length = len(dates_utc)
    frame_daily = pd.DataFrame(
        {
            "date": dates_utc,
            "local_date": local_days,
            "t_max": _values(daily, "temperature_2m_max", length),
            "t_min": _values(daily, "temperature_2m_min", length),
            "t_mean": _values(daily, "temperature_2m_mean", length),
            "precip_sum": _values(daily, "precipitation_sum", length),
            "et0_sum": _values(
                daily,
                "et0_fao_evapotranspiration",
                length,
            ),
            "wind_max": _values(daily, "wind_speed_10m_max", length),
        }
    )
    today_local = pd.Timestamp.now(tz=zone).date()
    frame_daily["data_kind"] = [
        "operational_past" if day < today_local else "forecast"
        for day in frame_daily["local_date"]
    ]
    frame_daily["data_source"] = _FORECAST_SOURCE

    hourly = payload.get("hourly")
    if isinstance(hourly, dict) and hourly.get("time"):
        hourly_dates = _parse_local_times(hourly["time"], timezone_name)
        hourly_length = len(hourly_dates)
        frame_hourly = pd.DataFrame(
            {
                "date": hourly_dates,
                "temperature_2m": _values(
                    hourly,
                    "temperature_2m",
                    hourly_length,
                ),
                "precipitation": _values(
                    hourly,
                    "precipitation",
                    hourly_length,
                ),
                "et0": _values(
                    hourly,
                    "et0_fao_evapotranspiration",
                    hourly_length,
                ),
                "soil_moisture_0_1": _values(
                    hourly,
                    "soil_moisture_0_to_1cm",
                    hourly_length,
                ),
            }
        )
    else:
        frame_hourly = pd.DataFrame()

    if frame_daily[["t_max", "t_min"]].dropna().empty:
        raise OpenMeteoError("Forecast contains no valid daily temperature data")
    if (pd.to_numeric(frame_daily["precip_sum"], errors="coerce") < 0).any():
        raise OpenMeteoError("Forecast contains negative precipitation")
    if (pd.to_numeric(frame_daily["et0_sum"], errors="coerce") < 0).any():
        raise OpenMeteoError("Forecast contains negative ET0")

    provider_latitude = _finite_float(payload.get("latitude"))
    provider_longitude = _finite_float(payload.get("longitude"))
    if provider_latitude is None or provider_longitude is None:
        raise OpenMeteoError("Provider did not return grid coordinates")
    grid_distance = _haversine_km(
        requested_latitude,
        requested_longitude,
        provider_latitude,
        provider_longitude,
    )
    if grid_distance > MAX_GRID_DISTANCE_KM:
        raise OpenMeteoError(
            "Nearest land grid cell is too far from the requested field: "
            f"{grid_distance:.1f} km"
        )
    elevation = _finite_float(payload.get("elevation"))
    utc_offset = int(payload.get("utc_offset_seconds") or 0)
    meta = WeatherMeta(
        latitude=provider_latitude,
        longitude=provider_longitude,
        elevation_m=elevation,
        utc_offset_seconds=utc_offset,
        timezone=timezone_name,
        source=_FORECAST_SOURCE,
        requested_latitude=requested_latitude,
        requested_longitude=requested_longitude,
        grid_distance_km=round(grid_distance, 3),
        model="best_match",
    )
    notes = (
        f"расстояние от координат поля до узла модели: {grid_distance:.1f} км",
    )
    coverage = WeatherCoverage(
        actual_start=min(local_days),
        actual_end=max(local_days),
        notes=notes,
        completed_days=int(
            (frame_daily["data_kind"] == "operational_past").sum()
        ),
        forecast_days=int((frame_daily["data_kind"] == "forecast").sum()),
    )
    return AgroWeatherData(
        meta=meta,
        daily=frame_daily.sort_values("date").reset_index(drop=True),
        hourly=frame_hourly,
        past_days=PAST_DAYS,
        forecast_days=FORECAST_DAYS,
        coverage=coverage,
    )


def _fetch_history_sync(
    lat: float,
    lon: float,
    start_date: date,
    end_date: date,
    timezone_name: str,
) -> pd.DataFrame:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "temperature_2m_mean",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
                "wind_speed_10m_max",
            ]
        ),
        "timezone": timezone_name,
        "cell_selection": "land",
    }
    payload = _request_json(
        ARCHIVE_URL,
        params=params,
        expire_after=24 * 60 * 60,
    )
    return _parse_history_payload(payload, timezone_name=timezone_name)


def _parse_history_payload(
    payload: dict[str, Any],
    *,
    timezone_name: str,
) -> pd.DataFrame:
    if payload.get("error"):
        raise OpenMeteoError(str(payload.get("reason") or "Historical API error"))
    daily = payload.get("daily")
    if not isinstance(daily, dict) or not daily.get("time"):
        raise OpenMeteoError("Historical response does not contain daily data")

    resolved_timezone = _timezone_name(payload.get("timezone") or timezone_name)
    local_values = pd.to_datetime(daily["time"], errors="coerce")
    if pd.isna(local_values).any():
        raise OpenMeteoError("Historical response contains invalid dates")
    local_days = [timestamp.date() for timestamp in local_values]
    dates_utc = _parse_local_times(daily["time"], resolved_timezone)
    length = len(dates_utc)
    frame = pd.DataFrame(
        {
            "date": dates_utc,
            "local_date": local_days,
            "t_max": _values(daily, "temperature_2m_max", length),
            "t_min": _values(daily, "temperature_2m_min", length),
            "t_mean": _values(daily, "temperature_2m_mean", length),
            "precip_sum": _values(daily, "precipitation_sum", length),
            "et0_sum": _values(
                daily,
                "et0_fao_evapotranspiration",
                length,
            ),
            "wind_max": _values(daily, "wind_speed_10m_max", length),
            "data_kind": ["reanalysis"] * length,
            "data_source": [_HISTORY_SOURCE] * length,
        }
    )
    if frame[["t_max", "t_min"]].dropna().empty:
        raise OpenMeteoError("Historical response contains no valid temperature data")
    if (pd.to_numeric(frame["precip_sum"], errors="coerce") < 0).any():
        raise OpenMeteoError("Historical response contains negative precipitation")
    if (pd.to_numeric(frame["et0_sum"], errors="coerce") < 0).any():
        raise OpenMeteoError("Historical response contains negative ET0")
    return frame.sort_values("date").reset_index(drop=True)


def _merge_daily(
    history: pd.DataFrame,
    operational: pd.DataFrame,
    timezone_name: str,
) -> pd.DataFrame:
    if history.empty:
        return operational.copy()
    zone = ZoneInfo(timezone_name)
    left = history.copy()
    right = operational.copy()
    left["_priority"] = 0
    right["_priority"] = 1
    combined = pd.concat([left, right], ignore_index=True, sort=False)
    combined["date"] = pd.to_datetime(combined["date"], utc=True)
    if "local_date" not in combined.columns:
        combined["local_date"] = (
            combined["date"].dt.tz_convert(zone).dt.date
        )
    else:
        missing = combined["local_date"].isna()
        combined.loc[missing, "local_date"] = (
            combined.loc[missing, "date"].dt.tz_convert(zone).dt.date
        )
    combined = combined.sort_values(["local_date", "_priority"])
    combined = combined.drop_duplicates("local_date", keep="last")
    return (
        combined.drop(columns="_priority")
        .sort_values("date")
        .reset_index(drop=True)
    )
