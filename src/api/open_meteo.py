"""Open-Meteo provider for operational agrometeorological data.

The public contract is deliberately small and asynchronous: callers receive one
``AgroWeatherData`` DTO or an explicit ``OpenMeteoError``. Synchronous vendor
code is isolated in a bounded worker thread and never blocks the bot event loop.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache

import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry

from config.settings import get_settings

logger = logging.getLogger(__name__)

PAST_DAYS = 14
FORECAST_DAYS = 7
OM_URL = "https://api.open-meteo.com/v1/forecast"
_MAX_CONCURRENT_REQUESTS = 4
_REQUEST_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)


class OpenMeteoError(RuntimeError):
    """The provider could not return a valid operational dataset."""


@dataclass(frozen=True, slots=True)
class WeatherMeta:
    latitude: float
    longitude: float
    elevation_m: float
    utc_offset_seconds: int
    timezone: str
    source: str = "Open-Meteo Forecast API"


@dataclass(slots=True)
class AgroWeatherData:
    meta: WeatherMeta
    daily: pd.DataFrame
    hourly: pd.DataFrame
    past_days: int = PAST_DAYS
    forecast_days: int = FORECAST_DAYS


@lru_cache(maxsize=1)
def _get_client() -> openmeteo_requests.Client:
    cache_path = get_settings().open_meteo_cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_session = requests_cache.CachedSession(
        str(cache_path),
        expire_after=3600,
    )
    retry_session = retry(
        cache_session,
        retries=4,
        backoff_factor=0.5,
        status_to_retry=(429, 500, 502, 503, 504),
    )
    return openmeteo_requests.Client(session=retry_session)


async def fetch_agro_data(lat: float, lon: float) -> AgroWeatherData:
    """Fetch a typed operational dataset without blocking the event loop."""
    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude outside [-90, 90]: {lat}")
    if not -180 <= lon <= 180:
        raise ValueError(f"Longitude outside [-180, 180]: {lon}")

    async with _REQUEST_SEMAPHORE:
        try:
            return await asyncio.to_thread(_fetch_sync, lat, lon)
        except (ValueError, OpenMeteoError):
            raise
        except Exception as exc:
            logger.exception("Open-Meteo request failed for %.5f, %.5f", lat, lon)
            raise OpenMeteoError(str(exc)) from exc


def _fetch_sync(lat: float, lon: float) -> AgroWeatherData:
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

    responses = _get_client().weather_api(OM_URL, params=params)
    if not responses:
        raise OpenMeteoError("Provider returned an empty response list")
    response = responses[0]

    hourly = response.Hourly()
    daily = response.Daily()
    if hourly is None or daily is None:
        raise OpenMeteoError("Provider response does not contain hourly/daily blocks")

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

    required_daily = {"date", "t_max", "t_min", "t_mean", "precip_sum", "et0_sum"}
    if df_daily.empty or not required_daily.issubset(df_daily.columns):
        raise OpenMeteoError("Daily dataset is empty or incomplete")

    meta = WeatherMeta(
        latitude=float(response.Latitude()),
        longitude=float(response.Longitude()),
        elevation_m=float(response.Elevation()),
        utc_offset_seconds=int(response.UtcOffsetSeconds()),
        timezone=str(response.Timezone() or "auto"),
    )
    logger.info(
        "Open-Meteo OK: %.3f %.3f, elevation %.0f m, %s",
        meta.latitude,
        meta.longitude,
        meta.elevation_m,
        meta.timezone,
    )
    return AgroWeatherData(meta=meta, daily=df_daily, hourly=df_hourly)
