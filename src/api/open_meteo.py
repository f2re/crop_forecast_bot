"""
Клиент Open-Meteo для получения агрометеорологических данных.

Без API-ключа, с кэшированием (1ч) и авто-retry (5x).

Параметры запроса:
  past_days=14    — для ГДД и ГТК за текущую декаду
  forecast_days=7 — горизонт для алертов заморозков (KPI проекта ≥ 48ч)

Переменные hourly:
  temperature_2m            — T (°C) для ГДД и заморозков
  precipitation             — осадки (мм/ч)
  et0_fao_evapotranspiration — ЕТ0 по Penman-Monteith FAO-56 (мм/ч)
  soil_moisture_0_to_1cm    — влажность верхнего слоя почвы (м³/м³)

Переменные daily (агрегаты — быстрее для индексов):
  temperature_2m_max/min/mean, precipitation_sum,
  et0_fao_evapotranspiration, wind_speed_10m_max
"""
import logging

import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry

logger = logging.getLogger(__name__)

PAST_DAYS     = 14
FORECAST_DAYS = 7
OM_URL        = "https://api.open-meteo.com/v1/forecast"

# Глобальная сессия с кэшем и retry — инициализируется один раз
_cache_session = requests_cache.CachedSession(".openmeteo_cache", expire_after=3600)
_retry_session = retry(_cache_session, retries=5, backoff_factor=0.2)
_client        = openmeteo_requests.Client(session=_retry_session)


def fetch_agro_data(lat: float, lon: float) -> dict:
    """
    Запрашивает почасовые и суточные агрометеорологические данные.

    Args:
        lat: широта (decimal degrees)
        lon: долгота (decimal degrees)

    Returns:
        {
          'meta':   {'lat', 'lon', 'elevation', 'utc_offset'},
          'hourly': pd.DataFrame — колонки date/temperature_2m/precipitation/et0/soil_moisture_0_1,
          'daily':  pd.DataFrame — колонки date/t_max/t_min/t_mean/precip_sum/et0_sum/wind_max,
        }

    Raises:
        Exception: при недоступности API (сеть, таймаут).
    """
    params = {
        "latitude":     lat,
        "longitude":    lon,
        "past_days":    PAST_DAYS,
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

    responses = _client.weather_api(OM_URL, params=params)
    response  = responses[0]

    logger.info(
        f"🌐 Open-Meteo OK: {response.Latitude():.3f}°N {response.Longitude():.3f}°E "
        f"elev={response.Elevation():.0f}m UTC+{response.UtcOffsetSeconds() // 3600}h"
    )

    # ── Hourly ────────────────────────────────────────────────────────────────
    hourly = response.Hourly()
    dates_h = pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left",
    )
    df_hourly = pd.DataFrame({
        "date":              dates_h,
        "temperature_2m":    hourly.Variables(0).ValuesAsNumpy(),
        "precipitation":     hourly.Variables(1).ValuesAsNumpy(),
        "et0":               hourly.Variables(2).ValuesAsNumpy(),
        "soil_moisture_0_1": hourly.Variables(3).ValuesAsNumpy(),
    })

    # ── Daily ─────────────────────────────────────────────────────────────────
    daily = response.Daily()
    dates_d = pd.date_range(
        start=pd.to_datetime(daily.Time(), unit="s", utc=True),
        end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=daily.Interval()),
        inclusive="left",
    )
    df_daily = pd.DataFrame({
        "date":       dates_d,
        "t_max":      daily.Variables(0).ValuesAsNumpy(),
        "t_min":      daily.Variables(1).ValuesAsNumpy(),
        "t_mean":     daily.Variables(2).ValuesAsNumpy(),
        "precip_sum": daily.Variables(3).ValuesAsNumpy(),
        "et0_sum":    daily.Variables(4).ValuesAsNumpy(),
        "wind_max":   daily.Variables(5).ValuesAsNumpy(),
    })

    return {
        "meta": {
            "lat":        response.Latitude(),
            "lon":        response.Longitude(),
            "elevation":  response.Elevation(),
            "utc_offset": response.UtcOffsetSeconds(),
        },
        "hourly": df_hourly,
        "daily":  df_daily,
    }
