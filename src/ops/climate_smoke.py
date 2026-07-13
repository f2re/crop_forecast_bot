"""Read-only live acceptance contract for homogeneous ERA5-Land data."""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from src.agro.climate_reference import calc_season_climate_reference
from src.api.open_meteo import (
    OpenMeteoError,
    OpenMeteoProvider,
    close_open_meteo_resources,
)
from src.api.open_meteo_climate import (
    CLIMATE_MODEL,
    OpenMeteoClimateError,
    OpenMeteoClimateProvider,
)
from src.domain.climate import ClimateReferenceData
from src.domain.season import parse_season_date

_REQUIRED_COLUMNS = {
    "date",
    "local_date",
    "t_mean",
    "precip_sum",
    "et0_sum",
    "data_kind",
    "data_source",
}
_REQUIRED_METRICS = {
    "mean_temperature_c",
    "precip_sum_mm",
    "et0_sum_mm",
    "gdd_c_day",
}


@dataclass(frozen=True, slots=True)
class ClimateSmokeResult:
    latitude: float
    longitude: float
    timezone: str
    model: str
    source: str
    reference_start: str
    reference_end: str
    comparison_start: str
    comparison_end: str
    retrieved_at: str
    reference_cache_ttl_seconds: int
    current_cache_ttl_seconds: int
    spatial_resolution_km: float | None
    reference_rows: int
    current_rows: int
    window_days: int
    minimum_reference_years: int
    available_metrics: tuple[str, ...]


def _prepare_frame(frame: pd.DataFrame, *, label: str) -> pd.DataFrame:
    missing_columns = _REQUIRED_COLUMNS.difference(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"{label} dataset is missing columns: {missing}")
    if frame.empty:
        raise ValueError(f"{label} dataset is empty")

    prepared = frame.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], utc=True, errors="coerce")
    if prepared["date"].isna().any():
        raise ValueError(f"{label} dataset contains invalid timestamps")
    if prepared["local_date"].isna().any():
        raise ValueError(f"{label} dataset contains missing local dates")

    kinds = {str(value) for value in prepared["data_kind"].dropna().unique()}
    if kinds != {"reanalysis"}:
        raise ValueError(f"{label} dataset is not homogeneous reanalysis: {kinds}")
    sources = {str(value) for value in prepared["data_source"].dropna().unique()}
    if not sources or not all("ERA5-Land" in value for value in sources):
        raise ValueError(f"{label} dataset does not identify ERA5-Land provenance")
    return prepared


def validate_climate_data(
    data: ClimateReferenceData,
    *,
    season_start: date,
    crop: str,
) -> ClimateSmokeResult:
    """Validate the live homogeneous ERA5-Land contract and calculations."""
    try:
        ZoneInfo(data.meta.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Climate timezone is invalid: {data.meta.timezone}") from exc

    if data.meta.model != CLIMATE_MODEL:
        raise ValueError(
            f"Climate model must be {CLIMATE_MODEL}, got {data.meta.model!r}"
        )
    if data.meta.retrieved_at.utcoffset() is None:
        raise ValueError("Climate retrieval timestamp is timezone-naive")
    if data.meta.reference_cache_ttl_seconds <= 0:
        raise ValueError("Reference cache TTL must be positive")
    if data.meta.current_cache_ttl_seconds <= 0:
        raise ValueError("Current cache TTL must be positive")

    reference = _prepare_frame(data.reference_daily, label="Reference")
    current = _prepare_frame(data.current_daily, label="Current-season")

    reference_start = min(reference["local_date"])
    reference_end = max(reference["local_date"])
    current_start = min(current["local_date"])
    current_end = max(current["local_date"])
    if reference_start != data.meta.reference_start:
        raise ValueError("Reference data does not start at metadata reference_start")
    if reference_end != data.meta.reference_end:
        raise ValueError("Reference data does not end at metadata reference_end")
    if current_start != season_start or current_start != data.meta.comparison_start:
        raise ValueError("Current ERA5-Land data does not reach the season start")
    if current_end != data.meta.comparison_end:
        raise ValueError("Current ERA5-Land end date differs from metadata")

    local_yesterday = datetime.now(ZoneInfo(data.meta.timezone)).date() - timedelta(days=1)
    if current_end > local_yesterday:
        raise ValueError("Current ERA5-Land data contains an unfinished local day")
    if current[["t_mean", "precip_sum", "et0_sum"]].isna().all(axis=1).any():
        raise ValueError("Current ERA5-Land data contains a fully empty retained row")

    comparison = calc_season_climate_reference(
        current,
        reference,
        crop=crop,
        season_start=season_start,
        reference_start=data.meta.reference_start,
        reference_end=data.meta.reference_end,
    )
    if not comparison["available"]:
        raise ValueError(f"Climate comparison is unavailable: {comparison['status']}")

    available_metrics = tuple(
        sorted(
            name
            for name, metric in comparison["metrics"].items()
            if metric.get("available")
        )
    )
    missing_metrics = _REQUIRED_METRICS.difference(available_metrics)
    if missing_metrics:
        missing = ", ".join(sorted(missing_metrics))
        raise ValueError(f"Climate comparison is missing required metrics: {missing}")

    minimum_reference_years = min(
        int(comparison["metrics"][name]["reference_years"])
        for name in _REQUIRED_METRICS
    )
    if minimum_reference_years < int(comparison["min_reference_years"]):
        raise ValueError("Climate comparison used too few reference years")

    return ClimateSmokeResult(
        latitude=data.meta.latitude,
        longitude=data.meta.longitude,
        timezone=data.meta.timezone,
        model=data.meta.model,
        source=data.meta.source,
        reference_start=data.meta.reference_start.isoformat(),
        reference_end=data.meta.reference_end.isoformat(),
        comparison_start=data.meta.comparison_start.isoformat(),
        comparison_end=data.meta.comparison_end.isoformat(),
        retrieved_at=data.meta.retrieved_at.isoformat(),
        reference_cache_ttl_seconds=data.meta.reference_cache_ttl_seconds,
        current_cache_ttl_seconds=data.meta.current_cache_ttl_seconds,
        spatial_resolution_km=data.meta.spatial_resolution_km,
        reference_rows=len(reference),
        current_rows=len(current),
        window_days=int(comparison["window_days"]),
        minimum_reference_years=minimum_reference_years,
        available_metrics=available_metrics,
    )


async def run_smoke(
    latitude: float,
    longitude: float,
    season_start: date,
    crop: str,
) -> ClimateSmokeResult:
    weather_provider = OpenMeteoProvider()
    climate_provider = OpenMeteoClimateProvider()
    try:
        # Resolve the same IANA timezone that production obtains from the
        # operational provider. The climate adapter intentionally rejects the
        # ambiguous "auto" pseudo-timezone.
        weather = await weather_provider.fetch(latitude, longitude, season_start=None)
        data = await climate_provider.fetch_reference(
            latitude,
            longitude,
            timezone=weather.meta.timezone,
            season_start=season_start,
        )
        return validate_climate_data(data, season_start=season_start, crop=crop)
    finally:
        await close_open_meteo_resources()


def _parse_date(value: str) -> date:
    return parse_season_date(value, today=date.today())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only homogeneous ERA5-Land climate contract smoke test"
    )
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--season-start", required=True)
    parser.add_argument("--crop", default="wheat")
    args = parser.parse_args()

    try:
        result = asyncio.run(
            run_smoke(
                args.latitude,
                args.longitude,
                _parse_date(args.season_start),
                args.crop,
            )
        )
    except (OpenMeteoError, OpenMeteoClimateError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps({"ok": True, **asdict(result)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
