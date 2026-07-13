"""Read-only live acceptance contract for operational Open-Meteo data."""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
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
_COMPLETED_KINDS = frozenset({"observation", "reanalysis", "operational_past"})
_FORECAST_KINDS = frozenset({"current_forecast", "forecast"})
_ALLOWED_KINDS = _COMPLETED_KINDS | _FORECAST_KINDS


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
    current_local_date: str
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


def _as_aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Smoke validation timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def validate_weather_data(
    data: AgroWeatherData,
    *,
    expected_season_start: date | None = None,
    as_of: datetime | None = None,
) -> ProviderSmokeResult:
    """Validate the live provider contract without inventing missing values.

    Besides the DTO shape, this verifies the most important temporal invariant:
    every completed row is before the current local calendar day and the
    current local day is present only in the forecast partition. When a season
    start is requested, the live acceptance contract also requires complete,
    gap-free historical coverage back to that date.
    """
    missing_columns = _REQUIRED_DAILY_COLUMNS.difference(data.daily.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Provider daily dataset is missing columns: {missing}")
    if data.daily.empty:
        raise ValueError("Provider daily dataset is empty")

    try:
        zone = ZoneInfo(data.meta.timezone)
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
    local_dates = pd.to_datetime(frame["local_date"], errors="coerce")
    if local_dates.isna().any():
        raise ValueError("Provider dataset contains missing or invalid local dates")
    frame["_local_date"] = local_dates.dt.date
    if frame["_local_date"].duplicated().any():
        duplicates = sorted(
            value.isoformat()
            for value in frame.loc[
                frame["_local_date"].duplicated(keep=False), "_local_date"
            ].unique()
        )
        raise ValueError(
            "Provider dataset contains duplicate local dates: " + ", ".join(duplicates)
        )

    frame_start = min(frame["_local_date"])
    frame_end = max(frame["_local_date"])
    expected_row_count = (frame_end - frame_start).days + 1
    if len(frame) != expected_row_count:
        raise ValueError("Provider daily dataset contains a local-calendar gap")

    kinds = {str(value) for value in frame["data_kind"].dropna().unique()}
    unsupported = kinds.difference(_ALLOWED_KINDS)
    if unsupported:
        values = ", ".join(sorted(unsupported))
        raise ValueError(f"Provider dataset contains unsupported data kinds: {values}")

    data_sources = tuple(
        sorted({str(value) for value in frame["data_source"].dropna().unique()})
    )
    if not data_sources:
        raise ValueError("Provider dataset contains no data-source provenance")

    temperature_rows = frame[["t_max", "t_min"]].dropna()
    if temperature_rows.empty:
        raise ValueError("Provider dataset contains no valid temperature rows")

    forecast_mask = frame["data_kind"].isin(_FORECAST_KINDS)
    completed_mask = frame["data_kind"].isin(_COMPLETED_KINDS)
    forecast_rows = int(forecast_mask.sum())
    completed_rows = int(completed_mask.sum())
    if forecast_rows == 0:
        raise ValueError("Provider dataset contains no forecast rows")

    current_local_date = _as_aware_utc(as_of).astimezone(zone).date()
    current_rows = frame[frame["_local_date"] == current_local_date]
    if current_rows.empty:
        raise ValueError(
            "Provider dataset does not contain the current local calendar day"
        )
    if not current_rows["data_kind"].isin(_FORECAST_KINDS).all():
        raise ValueError("Current local calendar day is not classified as forecast")
    if (frame.loc[completed_mask, "_local_date"] >= current_local_date).any():
        raise ValueError("Completed partition contains current or future local dates")
    if (frame.loc[forecast_mask, "_local_date"] < current_local_date).any():
        raise ValueError("Forecast partition contains a completed past local date")

    coverage = data.coverage
    if coverage.actual_start != frame_start or coverage.actual_end != frame_end:
        raise ValueError("Coverage metadata does not match the returned local-date range")
    if expected_season_start is not None:
        if coverage.requested_season_start != expected_season_start:
            raise ValueError(
                "Coverage metadata does not preserve the requested season start"
            )
        if not coverage.season_coverage_complete:
            raise ValueError("Provider did not return complete requested season coverage")
        if frame_start > expected_season_start:
            raise ValueError("Provider series does not reach the requested season start")
        if not coverage.history_source:
            raise ValueError("Requested season coverage has no historical provenance")
        if completed_rows == 0:
            raise ValueError("Requested season coverage contains no completed rows")

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
        current_local_date=current_local_date.isoformat(),
        actual_start=frame_start.isoformat(),
        actual_end=frame_end.isoformat(),
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
        data_sources=data_sources,
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
        return validate_weather_data(
            data,
            expected_season_start=season_start,
        )
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
