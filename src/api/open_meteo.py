"""Open-Meteo adapter for operational forecast and bounded season history.

The adapter separates forecast data from historical reanalysis in every daily
row. Historical Weather API data is used only to extend an explicitly requested
active season; failure of that optional extension degrades the report rather
than fabricating a complete seasonal series.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import openmeteo_requests
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
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_MAX_CONCURRENT_REQUESTS = 4
_REQUEST_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
_HISTORY_SOURCE = "Open-Meteo Historical Weather API (reanalysis Best Match)"


class OpenMeteoError(WeatherProviderError):
    """Open-Meteo could not return a valid dataset."""


class _TimeoutCachedSession(requests_cache.CachedSession):
    """Cached requests session with a mandatory connect/read timeout."""

    def request(self, method: str, url: str, *args: Any, **kwargs: Any):
        kwargs.setdefault("timeout", (5, 45))
        return super().request(method, url, *args, **kwargs)


def _classify_local_days(
    local_days: list[date] | pd.Series,
    *,
    today_local: date,
) -> list[str]:
    """Classify complete past local days separately from current/future forecast."""
    return [
        "operational_past" if local_day < today_local else "forecast"
        for local_day in local_days
    ]


def _timezone_name(raw_value: Any) -> str:
    if isinstance(raw_value, (bytes, bytearray)):
        value = raw_value.decode("utf-8", errors="replace")
    else:
        value = str(raw_value or "UTC")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        logger.warning("Provider returned unknown timezone %r; using UTC", value)
        return "UTC"
    return value


@lru_cache(maxsize=1)
def _get_http_session():
    cache_path = get_settings().open_meteo_cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_session = _TimeoutCachedSession(
        str(cache_path),
        expire_after=3600,
    )
    return retry(
        cache_session,
        retries=4,
        backoff_factor=0.5,
        status_to_retry=(429, 500, 502, 503, 504),
    )


@lru_cache(maxsize=1)
def _get_client() -> openmeteo_requests.Client:
    return openmeteo_requests.Client(session=_get_http_session())


def _close_resources_sync() -> None:
    if _get_http_session.cache_info().currsize:
        _get_http_session().close()
    _get_client.cache_clear()
    _get_http_session.cache_clear()


async def close_open_meteo_resources() -> None:
    """Close the cached synchronous HTTP session during application shutdown."""
    await asyncio.to_thread(_close_resources_sync)


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
    daily = forecast.daily
    notes: list[str] = []
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
                "начало сезона старше поддерживаемого оперативного окна; "
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
                    "сезонный реанализ недоступен; использовано короткое окно прогноза"
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
            "ряд не покрывает дату начала сезона; ГДД будут показаны только "
            "за доступный период"
        )

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
        ),
    )


def _fetch_forecast_sync(lat: float, lon: float) -> AgroWeatherData:
    params = {
        "latitude": lat,
        "longitude": lon,
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "hourly": [
            "temperature_2m",
            "precipitation",
            "et0_fao_evapotranspiration",
            "soil_moisture_0_to_1cm",
        ],
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "precipitation_sum",
            "et0_fao_evapotranspiration",
            "wind_speed_10m_max",
        ],
        "timezone": "auto",
    }

    responses = _get_client().weather_api(FORECAST_URL, params=params)
    if not responses:
        raise OpenMeteoError("Provider returned an empty response list")
    response = responses[0]
    hourly = response.Hourly()
    daily = response.Daily()
    if hourly is None or daily is None:
        raise OpenMeteoError("Provider response does not contain hourly/daily blocks")

    timezone_name = _timezone_name(response.Timezone())
    dates_h = pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left",
    )
    df_hourly = pd.DataFrame(
        {
            "date": dates_h,
            "temperature_2m": hourly.Variables(0).ValuesAsNumpy(),
            "precipitation": hourly.Variables(1).ValuesAsNumpy(),
            "et0": hourly.Variables(2).ValuesAsNumpy(),
            "soil_moisture_0_1": hourly.Variables(3).ValuesAsNumpy(),
        }
    )

    dates_d = pd.date_range(
        start=pd.to_datetime(daily.Time(), unit="s", utc=True),
        end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=daily.Interval()),
        inclusive="left",
    )
    df_daily = pd.DataFrame(
        {
            "date": dates_d,
            "t_max": daily.Variables(0).ValuesAsNumpy(),
            "t_min": daily.Variables(1).ValuesAsNumpy(),
            "t_mean": daily.Variables(2).ValuesAsNumpy(),
            "precip_sum": daily.Variables(3).ValuesAsNumpy(),
            "et0_sum": daily.Variables(4).ValuesAsNumpy(),
            "wind_max": daily.Variables(5).ValuesAsNumpy(),
        }
    )
    zone = ZoneInfo(timezone_name)
    df_daily["local_date"] = df_daily["date"].dt.tz_convert(zone).dt.date
    today_local = pd.Timestamp.now(tz=zone).date()
    df_daily["data_kind"] = _classify_local_days(
        df_daily["local_date"].tolist(),
        today_local=today_local,
    )
    df_daily["data_source"] = "Open-Meteo Forecast API"

    required_daily = {"date", "t_max", "t_min", "t_mean", "precip_sum", "et0_sum"}
    if df_daily.empty or not required_daily.issubset(df_daily.columns):
        raise OpenMeteoError("Daily dataset is empty or incomplete")

    meta = WeatherMeta(
        latitude=float(response.Latitude()),
        longitude=float(response.Longitude()),
        elevation_m=float(response.Elevation()),
        utc_offset_seconds=int(response.UtcOffsetSeconds()),
        timezone=timezone_name,
        source="Open-Meteo Forecast API",
    )
    logger.info(
        "Open-Meteo forecast OK: %.3f %.3f, elevation %.0f m, %s",
        meta.latitude,
        meta.longitude,
        meta.elevation_m,
        meta.timezone,
    )
    coverage = WeatherCoverage(
        actual_start=min(df_daily["local_date"]),
        actual_end=max(df_daily["local_date"]),
    )
    return AgroWeatherData(
        meta=meta,
        daily=df_daily,
        hourly=df_hourly,
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
    response = _get_http_session().get(
        ARCHIVE_URL,
        params=params,
        timeout=(5, 45),
        expire_after=24 * 60 * 60,
    )
    response.raise_for_status()
    return _parse_history_payload(response.json(), timezone_name=timezone_name)


def _daily_values(daily: dict[str, Any], name: str, length: int) -> list[Any]:
    values = daily.get(name)
    if values is None:
        return [float("nan")] * length
    if len(values) != length:
        raise OpenMeteoError(f"Historical variable {name} has an invalid length")
    return values


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
    local_dates = pd.DatetimeIndex(pd.to_datetime(daily["time"]))
    if local_dates.tz is None:
        local_dates = local_dates.tz_localize(
            ZoneInfo(resolved_timezone),
            ambiguous=False,
            nonexistent="shift_forward",
        )
    dates_utc = local_dates.tz_convert("UTC")
    length = len(dates_utc)
    t_max = _daily_values(daily, "temperature_2m_max", length)
    t_min = _daily_values(daily, "temperature_2m_min", length)
    t_mean = _daily_values(daily, "temperature_2m_mean", length)
    frame = pd.DataFrame(
        {
            "date": dates_utc,
            "local_date": list(local_dates.date),
            "t_max": t_max,
            "t_min": t_min,
            "t_mean": t_mean,
            "precip_sum": _daily_values(daily, "precipitation_sum", length),
            "et0_sum": _daily_values(
                daily,
                "et0_fao_evapotranspiration",
                length,
            ),
            "wind_max": _daily_values(daily, "wind_speed_10m_max", length),
            "data_kind": ["reanalysis"] * length,
            "data_source": [_HISTORY_SOURCE] * length,
        }
    )
    missing_mean = frame["t_mean"].isna()
    frame.loc[missing_mean, "t_mean"] = (
        frame.loc[missing_mean, "t_max"] + frame.loc[missing_mean, "t_min"]
    ) / 2.0
    if frame[["t_max", "t_min", "t_mean"]].dropna().empty:
        raise OpenMeteoError("Historical response contains no valid temperature data")
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
        combined["local_date"] = combined["date"].dt.tz_convert(zone).dt.date
    else:
        missing_local = combined["local_date"].isna()
        combined.loc[missing_local, "local_date"] = (
            combined.loc[missing_local, "date"].dt.tz_convert(zone).dt.date
        )
    combined = combined.sort_values(["local_date", "_priority"])
    combined = combined.drop_duplicates("local_date", keep="last")
    return (
        combined.drop(columns=["_priority"])
        .sort_values("date")
        .reset_index(drop=True)
    )
