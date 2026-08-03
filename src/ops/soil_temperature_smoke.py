"""Read-only live acceptance contract for Open-Meteo soil temperature."""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from src.api.open_meteo_soil import (
    OpenMeteoSoilTemperatureError,
    OpenMeteoSoilTemperatureProvider,
)
from src.domain.season import parse_season_date
from src.domain.soil_temperature import SoilTemperatureData

_REQUIRED_COLUMNS = {
    "date",
    "local_date",
    "t_min",
    "t_max",
    "t_mean",
    "valid_hours",
    "data_kind",
    "data_source",
}
_COMPLETED_KINDS = frozenset({"observation", "reanalysis", "operational_past"})
_FORECAST_KINDS = frozenset({"current_forecast", "forecast"})
_ALLOWED_KINDS = _COMPLETED_KINDS | _FORECAST_KINDS


@dataclass(frozen=True, slots=True)
class SoilTemperatureSmokeResult:
    latitude: float
    longitude: float
    timezone: str
    depth_label: str
    model: str
    source: str
    retrieved_at: str
    current_local_date: str
    requested_start: str | None
    actual_start: str
    actual_end: str
    start_covered: bool
    rows: int
    completed_rows: int
    forecast_rows: int
    minimum_c: float
    maximum_c: float
    data_kinds: tuple[str, ...]
    data_sources: tuple[str, ...]
    notes: tuple[str, ...]


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Smoke validation timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def validate_soil_temperature_data(
    data: SoilTemperatureData,
    *,
    expected_start: date | None = None,
    as_of: datetime | None = None,
) -> SoilTemperatureSmokeResult:
    missing = _REQUIRED_COLUMNS.difference(data.daily.columns)
    if missing:
        raise ValueError(
            "Soil-temperature dataset is missing columns: "
            + ", ".join(sorted(missing))
        )
    if data.daily.empty:
        raise ValueError("Soil-temperature dataset is empty")

    try:
        zone = ZoneInfo(data.meta.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Soil-temperature timezone is invalid: {data.meta.timezone}"
        ) from exc
    if not data.meta.source:
        raise ValueError("Soil-temperature source provenance is missing")
    if not data.meta.model:
        raise ValueError("Soil-temperature model provenance is missing")
    if "0–7" not in data.meta.depth_label and "0-7" not in data.meta.depth_label:
        raise ValueError("Soil-temperature depth label does not identify the 0–7 cm layer")
    if data.meta.retrieved_at.tzinfo is None:
        raise ValueError("Soil-temperature retrieval timestamp is timezone-naive")
    if data.meta.cache_ttl_seconds <= 0:
        raise ValueError("Soil-temperature cache TTL must be positive")

    frame = data.daily.copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    local_dates = pd.to_datetime(frame["local_date"], errors="coerce")
    if frame["date"].isna().any() or local_dates.isna().any():
        raise ValueError("Soil-temperature dataset contains invalid dates")
    frame["_local_date"] = local_dates.dt.date
    if frame["_local_date"].duplicated().any():
        raise ValueError("Soil-temperature dataset contains duplicate local dates")

    for column in ("t_min", "t_max", "t_mean", "valid_hours"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    valid = frame.dropna(subset=["t_min", "t_max", "t_mean", "valid_hours"])
    if valid.empty:
        raise ValueError("Soil-temperature dataset contains no valid complete days")
    if (valid["valid_hours"] < 18).any() or (valid["valid_hours"] > 25).any():
        raise ValueError("Soil-temperature valid-hour count is outside 18–25")
    if (valid["t_min"] > valid["t_mean"]).any() or (
        valid["t_mean"] > valid["t_max"]
    ).any():
        raise ValueError("Soil-temperature min/mean/max ordering is invalid")
    if (valid["t_min"] < -90).any() or (valid["t_max"] > 80).any():
        raise ValueError("Soil-temperature value is outside the acceptance range")

    frame_start = min(frame["_local_date"])
    frame_end = max(frame["_local_date"])
    expected_rows = (frame_end - frame_start).days + 1
    if len(frame) != expected_rows:
        raise ValueError("Soil-temperature dataset contains a local-calendar gap")

    kinds = {str(value) for value in frame["data_kind"].dropna().unique()}
    unsupported = kinds.difference(_ALLOWED_KINDS)
    if unsupported:
        raise ValueError(
            "Soil-temperature dataset contains unsupported data kinds: "
            + ", ".join(sorted(unsupported))
        )
    sources = tuple(
        sorted({str(value) for value in frame["data_source"].dropna().unique()})
    )
    if not sources:
        raise ValueError("Soil-temperature row provenance is missing")

    completed_mask = frame["data_kind"].isin(_COMPLETED_KINDS)
    forecast_mask = frame["data_kind"].isin(_FORECAST_KINDS)
    completed_rows = int(completed_mask.sum())
    forecast_rows = int(forecast_mask.sum())
    if completed_rows == 0:
        raise ValueError("Soil-temperature dataset contains no completed rows")
    if forecast_rows == 0:
        raise ValueError("Soil-temperature dataset contains no forecast rows")

    current_local_date = _aware_utc(as_of).astimezone(zone).date()
    current_rows = frame[frame["_local_date"] == current_local_date]
    if current_rows.empty:
        raise ValueError("Soil-temperature dataset does not contain the current local day")
    if not current_rows["data_kind"].isin(_FORECAST_KINDS).all():
        raise ValueError("Current local soil-temperature day is not forecast")
    if (frame.loc[completed_mask, "_local_date"] >= current_local_date).any():
        raise ValueError("Completed soil-temperature rows include current/future dates")
    if (frame.loc[forecast_mask, "_local_date"] < current_local_date).any():
        raise ValueError("Forecast soil-temperature rows include completed past dates")

    coverage = data.coverage
    if coverage.actual_start != frame_start or coverage.actual_end != frame_end:
        raise ValueError("Soil-temperature coverage metadata does not match the data")
    if expected_start is not None:
        if coverage.requested_start != expected_start:
            raise ValueError("Requested soil-temperature start was not preserved")
        if not coverage.start_covered or frame_start > expected_start:
            raise ValueError("Soil-temperature series does not cover the requested start")
        if not coverage.history_source:
            raise ValueError("Historical soil-temperature provenance is missing")
        if not any("ERA5-Land" in source for source in sources):
            raise ValueError("Historical soil-temperature rows are not marked ERA5-Land")
    if not any("ECMWF" in source for source in sources):
        raise ValueError("Operational soil-temperature rows are not marked ECMWF")

    return SoilTemperatureSmokeResult(
        latitude=data.meta.latitude,
        longitude=data.meta.longitude,
        timezone=data.meta.timezone,
        depth_label=data.meta.depth_label,
        model=data.meta.model,
        source=data.meta.source,
        retrieved_at=data.meta.retrieved_at.astimezone(timezone.utc).isoformat(),
        current_local_date=current_local_date.isoformat(),
        requested_start=(expected_start.isoformat() if expected_start else None),
        actual_start=frame_start.isoformat(),
        actual_end=frame_end.isoformat(),
        start_covered=coverage.start_covered,
        rows=len(frame),
        completed_rows=completed_rows,
        forecast_rows=forecast_rows,
        minimum_c=round(float(valid["t_min"].min()), 2),
        maximum_c=round(float(valid["t_max"].max()), 2),
        data_kinds=tuple(sorted(kinds)),
        data_sources=sources,
        notes=coverage.notes,
    )


async def run_smoke(
    latitude: float,
    longitude: float,
    start: date | None,
) -> SoilTemperatureSmokeResult:
    provider = OpenMeteoSoilTemperatureProvider()
    data = await provider.fetch(latitude, longitude, season_start=start)
    return validate_soil_temperature_data(data, expected_start=start)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return parse_season_date(value, today=date.today())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Open-Meteo soil-temperature contract smoke test"
    )
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument(
        "--start",
        help="Optional required start in YYYY-MM-DD or DD.MM.YYYY format",
    )
    args = parser.parse_args()

    try:
        result = asyncio.run(
            run_smoke(
                args.latitude,
                args.longitude,
                _parse_date(args.start),
            )
        )
    except (OpenMeteoSoilTemperatureError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps({"ok": True, **asdict(result)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
