from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import requests_cache
from retry_requests import retry

from config.settings import get_settings
from src.application.ports.late_blight import (
    LateBlightWeatherProvider,
    LateBlightWeatherProviderError,
)
from src.domain.late_blight import LateBlightWeatherData, LateBlightWeatherMeta

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PAST_DAYS = 3
FORECAST_DAYS = 7
CACHE_TTL_SECONDS = 60 * 60
_MAX_CONCURRENT_REQUESTS = 4
_REQUEST_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

_REQUIRED_HOURLY = (
    "temperature_2m",
    "relative_humidity_2m",
)
_OPTIONAL_MOISTURE_HOURLY = (
    "dew_point_2m",
    "precipitation",
    "weather_code",
    "visibility",
    "is_day",
)


def build_late_blight_request_params(
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    """Request the Hutton inputs plus non-triggering moisture diagnostics.

    Temperature and relative humidity are the only hard inputs used by the
    Hutton decision. Dew point, precipitation, fog/visibility and day/night are
    supporting context: they explain possible nocturnal condensation but never
    create a late-blight alert by themselves.
    """

    return {
        "latitude": latitude,
        "longitude": longitude,
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "hourly": ",".join((*_REQUIRED_HOURLY, *_OPTIONAL_MOISTURE_HOURLY)),
        "timezone": "auto",
        "timeformat": "unixtime",
        "cell_selection": "land",
    }


def _timezone_name(raw_value: Any) -> str:
    value = str(raw_value or "UTC")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise LateBlightWeatherProviderError(
            f"Поставщик вернул неизвестный часовой пояс: {value}"
        ) from exc
    return value


def _timestamps(values: list[Any]) -> pd.DatetimeIndex:
    if not values:
        return pd.DatetimeIndex([])
    if all(isinstance(value, (int, float)) for value in values):
        return pd.DatetimeIndex(pd.to_datetime(values, unit="s", utc=True))
    return pd.DatetimeIndex(pd.to_datetime(values, utc=True, errors="coerce"))


def _hourly_values(
    hourly: dict[str, Any],
    name: str,
    expected_length: int,
    *,
    required: bool,
) -> list[Any]:
    raw = hourly.get(name)
    if raw is None:
        if required:
            raise LateBlightWeatherProviderError(
                f"Open-Meteo не вернул обязательный ряд {name}"
            )
        return [None] * expected_length
    values = list(raw)
    if len(values) != expected_length:
        raise LateBlightWeatherProviderError(
            f"Почасовой ряд {name} имеет длину {len(values)}, "
            f"ожидалось {expected_length}"
        )
    return values


def parse_late_blight_payload(
    payload: dict[str, Any],
    *,
    retrieved_at: datetime,
) -> LateBlightWeatherData:
    if payload.get("error"):
        raise LateBlightWeatherProviderError(
            str(payload.get("reason") or "Open-Meteo вернул ошибку")
        )
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise LateBlightWeatherProviderError(
            "Open-Meteo не вернул почасовой блок"
        )

    times = list(hourly.get("time") or ())
    if not times:
        raise LateBlightWeatherProviderError("Почасовая временная ось пуста")
    length = len(times)
    temperature = _hourly_values(
        hourly,
        "temperature_2m",
        length,
        required=True,
    )
    humidity = _hourly_values(
        hourly,
        "relative_humidity_2m",
        length,
        required=True,
    )

    dates = _timestamps(times)
    if len(dates) != length or dates.isna().any():
        raise LateBlightWeatherProviderError(
            "Open-Meteo вернул повреждённую временную ось"
        )
    timezone_name = _timezone_name(payload.get("timezone"))
    frame = pd.DataFrame(
        {
            "date": dates,
            "temperature_2m": temperature,
            "relative_humidity_2m": humidity,
            "dew_point_2m": _hourly_values(
                hourly,
                "dew_point_2m",
                length,
                required=False,
            ),
            "precipitation": _hourly_values(
                hourly,
                "precipitation",
                length,
                required=False,
            ),
            "weather_code": _hourly_values(
                hourly,
                "weather_code",
                length,
                required=False,
            ),
            "visibility": _hourly_values(
                hourly,
                "visibility",
                length,
                required=False,
            ),
            "is_day": _hourly_values(
                hourly,
                "is_day",
                length,
                required=False,
            ),
        }
    )
    return LateBlightWeatherData(
        meta=LateBlightWeatherMeta(
            latitude=float(payload.get("latitude", 0.0)),
            longitude=float(payload.get("longitude", 0.0)),
            elevation_m=(
                None
                if payload.get("elevation") is None
                else float(payload["elevation"])
            ),
            timezone=timezone_name,
            source="Open-Meteo Forecast API",
            model="best_match",
            retrieved_at=retrieved_at,
            cache_ttl_seconds=CACHE_TTL_SECONDS,
        ),
        hourly=frame,
    )


def _fetch_sync(latitude: float, longitude: float) -> LateBlightWeatherData:
    base_cache_path = get_settings().open_meteo_cache_path
    base_cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path = base_cache_path.parent / f"{base_cache_path.name}-late-blight"
    session = requests_cache.CachedSession(
        str(cache_path),
        expire_after=CACHE_TTL_SECONDS,
    )
    client = retry(
        session,
        retries=4,
        backoff_factor=0.5,
        status_to_retry=(429, 500, 502, 503, 504),
    )
    try:
        response = client.get(
            FORECAST_URL,
            params=build_late_blight_request_params(latitude, longitude),
            timeout=(5, 45),
        )
        response.raise_for_status()
        payload = response.json()
    except LateBlightWeatherProviderError:
        raise
    except Exception as exc:
        raise LateBlightWeatherProviderError(str(exc)) from exc
    finally:
        session.close()

    if not isinstance(payload, dict):
        raise LateBlightWeatherProviderError(
            "Open-Meteo вернул неожиданный формат ответа"
        )
    return parse_late_blight_payload(
        payload,
        retrieved_at=datetime.now(timezone.utc),
    )


class OpenMeteoLateBlightProvider(LateBlightWeatherProvider):
    async def fetch(
        self,
        latitude: float,
        longitude: float,
    ) -> LateBlightWeatherData:
        if not -90 <= latitude <= 90:
            raise ValueError(f"Latitude outside [-90, 90]: {latitude}")
        if not -180 <= longitude <= 180:
            raise ValueError(f"Longitude outside [-180, 180]: {longitude}")
        async with _REQUEST_SEMAPHORE:
            return await asyncio.to_thread(_fetch_sync, latitude, longitude)
