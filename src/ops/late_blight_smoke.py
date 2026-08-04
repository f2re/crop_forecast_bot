from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from src.api.open_meteo_late_blight import OpenMeteoLateBlightProvider
from src.application.ports.late_blight import LateBlightWeatherProviderError
from src.domain.late_blight import calculate_hutton_outlook
from src.domain.season import local_today

_REQUIRED_COLUMNS = {
    "date",
    "temperature_2m",
    "relative_humidity_2m",
}
_MOISTURE_CONTEXT_COLUMNS = {
    "dew_point_2m",
    "precipitation",
    "weather_code",
    "visibility",
    "is_day",
}


@dataclass(frozen=True, slots=True)
class LateBlightSmokeResult:
    latitude: float
    longitude: float
    timezone: str
    source: str
    model: str
    retrieved_at: str
    cache_ttl_seconds: int
    rows: int
    first_timestamp: str
    last_timestamp: str
    complete_local_days: int
    qualifying_local_days: int
    hutton_periods: int
    dew_point_hours: int
    precipitation_hours: int
    weather_code_hours: int
    visibility_hours: int
    is_day_hours: int
    night_moisture_periods: int


def _valid_numeric_hours(frame: pd.DataFrame, column: str) -> int:
    return int(pd.to_numeric(frame[column], errors="coerce").notna().sum())


def validate_late_blight_weather(data) -> LateBlightSmokeResult:
    missing = (_REQUIRED_COLUMNS | _MOISTURE_CONTEXT_COLUMNS).difference(
        data.hourly.columns
    )
    if missing:
        raise ValueError(
            "Late-blight hourly dataset is missing columns: "
            + ", ".join(sorted(missing))
        )
    if data.hourly.empty:
        raise ValueError("Late-blight hourly dataset is empty")
    try:
        ZoneInfo(data.meta.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Late-blight provider timezone is invalid: {data.meta.timezone}"
        ) from exc
    if not data.meta.source or not data.meta.model:
        raise ValueError("Late-blight provider provenance is incomplete")
    if data.meta.retrieved_at.utcoffset() is None:
        raise ValueError("Late-blight retrieval timestamp is timezone-naive")
    if data.meta.cache_ttl_seconds <= 0:
        raise ValueError("Late-blight cache TTL must be positive")

    frame = data.hourly.copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    if frame["date"].isna().any():
        raise ValueError("Late-blight provider returned invalid timestamps")
    if frame["date"].duplicated().any():
        raise ValueError("Late-blight provider returned duplicate timestamps")
    ordered = frame.sort_values("date")
    gaps = ordered["date"].diff().dropna()
    if not gaps.empty and not (gaps == pd.Timedelta(hours=1)).all():
        raise ValueError("Late-blight provider hourly axis contains a gap")

    valid_hours = {
        column: _valid_numeric_hours(frame, column)
        for column in _REQUIRED_COLUMNS | _MOISTURE_CONTEXT_COLUMNS
        if column != "date"
    }
    if valid_hours["temperature_2m"] < 48:
        raise ValueError("Late-blight provider returned fewer than 48 temperature hours")
    if valid_hours["relative_humidity_2m"] < 48:
        raise ValueError("Late-blight provider returned fewer than 48 humidity hours")
    missing_context = sorted(
        column
        for column in _MOISTURE_CONTEXT_COLUMNS
        if valid_hours[column] < 48
    )
    if missing_context:
        raise ValueError(
            "Late-blight provider lost nocturnal moisture inputs: "
            + ", ".join(missing_context)
        )

    humidity = pd.to_numeric(frame["relative_humidity_2m"], errors="coerce")
    if not humidity.dropna().between(0.0, 100.0).all():
        raise ValueError("Late-blight provider returned humidity outside 0..100")
    is_day = pd.to_numeric(frame["is_day"], errors="coerce").dropna()
    if not is_day.isin((0.0, 1.0)).all():
        raise ValueError("Late-blight provider returned invalid is_day values")
    precipitation = pd.to_numeric(frame["precipitation"], errors="coerce")
    if (precipitation.dropna() < 0.0).any():
        raise ValueError("Late-blight provider returned negative precipitation")
    visibility = pd.to_numeric(frame["visibility"], errors="coerce")
    if (visibility.dropna() < 0.0).any():
        raise ValueError("Late-blight provider returned negative visibility")

    outlook = calculate_hutton_outlook(
        data,
        today=local_today(data.meta.timezone),
    )
    complete_days = sum(day.complete for day in outlook.days)
    if complete_days < 2:
        raise ValueError("Late-blight provider returned fewer than two complete days")
    if not outlook.night_moisture:
        raise ValueError("Late-blight provider returned no day/night moisture periods")

    return LateBlightSmokeResult(
        latitude=data.meta.latitude,
        longitude=data.meta.longitude,
        timezone=data.meta.timezone,
        source=data.meta.source,
        model=data.meta.model,
        retrieved_at=data.meta.retrieved_at.isoformat(),
        cache_ttl_seconds=data.meta.cache_ttl_seconds,
        rows=len(frame),
        first_timestamp=ordered["date"].iloc[0].isoformat(),
        last_timestamp=ordered["date"].iloc[-1].isoformat(),
        complete_local_days=complete_days,
        qualifying_local_days=sum(day.qualifies for day in outlook.days),
        hutton_periods=len(outlook.periods),
        dew_point_hours=valid_hours["dew_point_2m"],
        precipitation_hours=valid_hours["precipitation"],
        weather_code_hours=valid_hours["weather_code"],
        visibility_hours=valid_hours["visibility"],
        is_day_hours=valid_hours["is_day"],
        night_moisture_periods=len(outlook.night_moisture),
    )


async def run_smoke(latitude: float, longitude: float) -> LateBlightSmokeResult:
    data = await OpenMeteoLateBlightProvider().fetch(latitude, longitude)
    return validate_late_blight_weather(data)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Open-Meteo Hutton and night-moisture contract smoke"
    )
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    args = parser.parse_args()

    try:
        result = asyncio.run(run_smoke(args.latitude, args.longitude))
    except (LateBlightWeatherProviderError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {"ok": True, **asdict(result)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
