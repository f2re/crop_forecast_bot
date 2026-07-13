"""Read-only live acceptance contract for operational Open-Meteo data."""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import date, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from src.api.open_meteo import (
    OpenMeteoError,
    OpenMeteoProvider,
    close_open_meteo_resources,
)
from src.domain.season import parse_season_date
from src.domain.weather import AgroWeatherData

_REQUIRED_DAILY_COLUMNS = {
    "date",
    "local_date",
    "t_max",
    "t_min",
    "t_mean",
    "precip_sum",
    "et0_sum",
    "data_kind",
    "data_source",
}
_ALLOWED_KINDS = {
    "observation",
    "reanalysis",
    "operational_past",
    "current_forecast",
    "forecast",
}


@dataclass(frozen=True, slots=True)
class ProviderSmokeResult:
    latitude: float
    longitude: float
    timezone: str
    elevation_m: float
    model: str
    model_run: str | None
    retrieved_at: str
    cache_ttl_seconds: int | None
    spatial_resolution_km: float | None
    actual_start: str | None
    actual_end: str | None
    requested_season_start: str | None
    season_coverage_complete: bool
    rows: int
    completed_rows: int
    forecast_rows: int
    data_kinds: tuple[str, ...]
    data_sources: tuple[str, ...]
    notes: tuple[str, ...]


def validate_weather_data(data: AgroWeatherData) -> ProviderSmokeResult:
    """Validate the live provider contract without inventing missing values."""
    missing_columns = _REQUIRED_DAILY_COLUMNS.difference(data.daily.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Provider daily dataset is missing columns: {missing}")
    if data.daily.empty:
        raise ValueError("Provider daily dataset is empty")

    try:
        ZoneInfo(data.meta.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Provider timezone is invalid: {data.meta.timezone}") from exc

    if not data.meta.model:
        raise ValueError("Provider model provenance is missing")
    if data.meta.retrieved_at is None or data.meta.retrieved_at.utcoffset() is None:
        raise ValueError("Provider retrieval timestamp is missing or timezone-naive")
    if data.meta.cache_ttl_seconds is not None and data.meta.cache_ttl_seconds <= 0:
        raise ValueError("Provider cache TTL must be positive")

    frame = data.daily.copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    if frame["date"].isna().any():
        raise ValueError("Provider dataset contains invalid timestamps")
    if frame["local_date"].isna().any():
        raise ValueError("Provider dataset contains missing local dates")

    kinds = {str(value) for value in frame["data_kind"].dropna().unique()}
    unsupported = kinds.difference(_ALLOWED_KINDS)
    if unsupported:
        values = ", ".join(sorted(unsupported))
        raise ValueError(f"Provider dataset contains unsupported data kinds: {values}")

    temperature_rows = frame[["t_max", "t_min"]].dropna()
    if temperature_rows.empty:
        raise ValueError("Provider dataset contains no valid temperature rows")

    forecast_rows = int(frame["data_kind"].isin({"current_forecast", "forecast"}).sum())
    if forecast_rows == 0:
        raise ValueError("Provider dataset contains no forecast rows")
    completed_rows = int(
        frame["data_kind"]
        .isin({"observation", "reanalysis", "operational_past"})
        .sum()
    )

    coverage = data.coverage
    model_run = (
        data.meta.model_run.astimezone(timezone.utc).isoformat()
        if data.meta.model_run is not None
        else None
    )
    return ProviderSmokeResult(
        latitude=data.meta.latitude,
        longitude=data.meta.longitude,
        timezone=data.meta.timezone,
        elevation_m=data.meta.elevation_m,
        model=data.meta.model,
        model_run=model_run,
        retrieved_at=data.meta.retrieved_at.astimezone(timezone.utc).isoformat(),
        cache_ttl_seconds=data.meta.cache_ttl_seconds,
        spatial_resolution_km=data.meta.spatial_resolution_km,
        actual_start=(coverage.actual_start.isoformat() if coverage.actual_start else None),
        actual_end=coverage.actual_end.isoformat() if coverage.actual_end else None,
        requested_season_start=(
            coverage.requested_season_start.isoformat()
            if coverage.requested_season_start
            else None
        ),
        season_coverage_complete=coverage.season_coverage_complete,
        rows=len(frame),
        completed_rows=completed_rows,
        forecast_rows=forecast_rows,
        data_kinds=tuple(sorted(kinds)),
        data_sources=tuple(
            sorted({str(value) for value in frame["data_source"].dropna().unique()})
        ),
        notes=coverage.notes,
    )


async def run_smoke(
    latitude: float,
    longitude: float,
    season_start: date | None,
) -> ProviderSmokeResult:
    provider = OpenMeteoProvider()
    try:
        data = await provider.fetch(latitude, longitude, season_start=season_start)
        return validate_weather_data(data)
    finally:
        await close_open_meteo_resources()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return parse_season_date(value, today=date.today())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Open-Meteo production contract smoke test"
    )
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument(
        "--season-start",
        help="Optional season start in YYYY-MM-DD or DD.MM.YYYY format",
    )
    args = parser.parse_args()

    try:
        result = asyncio.run(
            run_smoke(
                args.latitude,
                args.longitude,
                _parse_date(args.season_start),
            )
        )
    except (OpenMeteoError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    payload = {"ok": True, **asdict(result)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
