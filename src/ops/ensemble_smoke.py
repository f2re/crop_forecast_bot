"""Read-only live acceptance contract for the Open-Meteo GFS ensemble adapter."""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from src.agro.ensemble_risks import MIN_VALID_MEMBERS, calc_ensemble_risks
from src.api.open_meteo_ensemble import (
    OpenMeteoEnsembleError,
    OpenMeteoEnsembleProvider,
    close_open_meteo_ensemble_resources,
)
from src.domain.risk import EnsembleForecastData

_REQUIRED_COLUMNS = {
    "local_date",
    "member_id",
    "t_min_c",
    "t_max_c",
    "precip_mm",
    "wind_gust_ms",
    "cape_j_kg",
}
_NON_NEGATIVE_COLUMNS = ("precip_mm", "wind_gust_ms", "cape_j_kg")
_MIN_FORECAST_DAYS = 10


@dataclass(frozen=True, slots=True)
class EnsembleSmokeResult:
    latitude: float
    longitude: float
    elevation_m: float | None
    timezone: str
    source: str
    model: str
    retrieved_at: str
    cache_ttl_seconds: int | None
    member_count: int
    forecast_days: int
    rows: int
    local_date_start: str
    local_date_end: str
    complete_days: int
    incomplete_days: int
    emitted_risk_events: int


def _as_aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Smoke validation timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def validate_ensemble_data(
    data: EnsembleForecastData,
    *,
    as_of: datetime | None = None,
) -> EnsembleSmokeResult:
    """Validate shape, provenance, member coverage and physical guardrails."""

    missing_columns = _REQUIRED_COLUMNS.difference(data.daily_members.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Ensemble dataset is missing columns: {missing}")
    if data.daily_members.empty:
        raise ValueError("Ensemble dataset is empty")

    try:
        zone = ZoneInfo(data.meta.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Ensemble timezone is invalid: {data.meta.timezone}") from exc
    if not data.meta.source:
        raise ValueError("Ensemble source provenance is missing")
    if not data.meta.model:
        raise ValueError("Ensemble model provenance is missing")
    if data.meta.retrieved_at.tzinfo is None or data.meta.retrieved_at.utcoffset() is None:
        raise ValueError("Ensemble retrieval timestamp is timezone-naive")
    if data.meta.cache_ttl_seconds is not None and data.meta.cache_ttl_seconds <= 0:
        raise ValueError("Ensemble cache TTL must be positive")

    frame = data.daily_members.copy()
    local_dates = pd.to_datetime(frame["local_date"], errors="coerce")
    if local_dates.isna().any():
        raise ValueError("Ensemble dataset contains invalid local dates")
    frame["_local_date"] = local_dates.dt.date
    frame["member_id"] = frame["member_id"].astype("string")
    if frame["member_id"].isna().any() or (frame["member_id"].str.len() == 0).any():
        raise ValueError("Ensemble dataset contains an empty member id")
    if frame.duplicated(["_local_date", "member_id"]).any():
        raise ValueError("Ensemble dataset contains duplicate date/member rows")

    date_start = min(frame["_local_date"])
    date_end = max(frame["_local_date"])
    expected_days = (date_end - date_start).days + 1
    actual_days = int(frame["_local_date"].nunique())
    if actual_days != expected_days:
        raise ValueError("Ensemble dataset contains a local-calendar gap")
    if actual_days < _MIN_FORECAST_DAYS:
        raise ValueError(
            f"Ensemble horizon is too short: {actual_days} days; "
            f"expected at least {_MIN_FORECAST_DAYS}"
        )

    current_local_date = _as_aware_utc(as_of).astimezone(zone).date()
    if date_start > current_local_date:
        raise ValueError("Ensemble dataset does not include the current local date")
    if date_end < current_local_date:
        raise ValueError("Ensemble dataset contains no current or future date")
    if (frame["_local_date"] < current_local_date).any():
        raise ValueError("Ensemble dataset contains a completed past local date")

    numeric_columns = sorted(_REQUIRED_COLUMNS.difference({"local_date", "member_id"}))
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in _NON_NEGATIVE_COLUMNS:
        if (frame[column].dropna() < 0).any():
            raise ValueError(f"Ensemble dataset contains negative {column}")
    if (frame["t_min_c"].dropna() < -100).any() or (
        frame["t_max_c"].dropna() > 70
    ).any():
        raise ValueError("Ensemble temperature is outside the smoke-test range")
    paired_temperature = frame[["t_min_c", "t_max_c"]].dropna()
    if (paired_temperature["t_min_c"] > paired_temperature["t_max_c"]).any():
        raise ValueError("Ensemble Tmin exceeds Tmax")

    unique_members = int(frame["member_id"].nunique())
    if unique_members < MIN_VALID_MEMBERS:
        raise ValueError(
            f"Ensemble has {unique_members} members; "
            f"expected at least {MIN_VALID_MEMBERS}"
        )
    if data.meta.member_count != unique_members:
        raise ValueError("Ensemble member metadata does not match returned rows")
    if data.meta.forecast_days != actual_days:
        raise ValueError("Ensemble horizon metadata does not match returned rows")

    for local_day, group in frame.groupby("_local_date", sort=True):
        for column in numeric_columns:
            valid_members = int(group[column].notna().sum())
            if valid_members < MIN_VALID_MEMBERS:
                raise ValueError(
                    f"Ensemble day {local_day} has only {valid_members} valid "
                    f"members for {column}"
                )

    outlook = calc_ensemble_risks(data, as_of_date=current_local_date)
    if not outlook.available:
        raise ValueError(f"Risk calculation rejected live ensemble: {outlook.status}")
    if outlook.valid_days != actual_days or outlook.incomplete_days != 0:
        raise ValueError("Risk calculation did not accept the complete live horizon")

    return EnsembleSmokeResult(
        latitude=data.meta.latitude,
        longitude=data.meta.longitude,
        elevation_m=data.meta.elevation_m,
        timezone=data.meta.timezone,
        source=data.meta.source,
        model=data.meta.model,
        retrieved_at=data.meta.retrieved_at.astimezone(timezone.utc).isoformat(),
        cache_ttl_seconds=data.meta.cache_ttl_seconds,
        member_count=unique_members,
        forecast_days=actual_days,
        rows=len(frame),
        local_date_start=date_start.isoformat(),
        local_date_end=date_end.isoformat(),
        complete_days=outlook.valid_days,
        incomplete_days=outlook.incomplete_days,
        emitted_risk_events=len(outlook.events),
    )


async def run_smoke(latitude: float, longitude: float) -> EnsembleSmokeResult:
    provider = OpenMeteoEnsembleProvider()
    try:
        data = await provider.fetch(latitude, longitude)
        return validate_ensemble_data(data)
    finally:
        await close_open_meteo_ensemble_resources()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Open-Meteo GFS ensemble contract smoke test"
    )
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    args = parser.parse_args()

    try:
        result = asyncio.run(run_smoke(args.latitude, args.longitude))
    except (OpenMeteoEnsembleError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    payload = {"ok": True, **asdict(result)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
