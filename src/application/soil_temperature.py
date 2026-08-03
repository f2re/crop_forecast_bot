from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from src.api.open_meteo_soil import OpenMeteoSoilTemperatureProvider
from src.application.ports.soil_temperature import SoilTemperatureProvider

_COMPLETED_KINDS = frozenset({"observation", "reanalysis", "operational_past"})
_FORECAST_KINDS = frozenset({"current_forecast", "forecast"})


@dataclass(frozen=True, slots=True)
class SoilTemperatureDay:
    local_date: date
    mean_c: float
    minimum_c: float
    maximum_c: float
    source: str


@dataclass(frozen=True, slots=True)
class SoilTemperatureReport:
    latest_completed: SoilTemperatureDay | None
    recent_mean_c: float | None
    recent_change_c: float | None
    recent_days: int
    forecast: tuple[SoilTemperatureDay, ...]
    timezone: str
    source: str
    model: str
    depth_label: str
    retrieved_at: datetime
    spatial_resolution_km: float | None
    coverage_start: date | None
    coverage_end: date | None
    notes: tuple[str, ...]


def _normalise_daily(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"local_date", "t_min", "t_max", "t_mean"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "Не хватает столбцов температуры почвы: "
            + ", ".join(sorted(missing))
        )
    optional = {"data_kind", "data_source"}.intersection(frame.columns)
    result = frame[list(required | optional)].copy()
    result["local_date"] = pd.to_datetime(
        result["local_date"],
        errors="coerce",
    ).dt.date
    for column in ("t_min", "t_max", "t_mean"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=["local_date", "t_min", "t_max", "t_mean"])
    result = result[result["t_min"] <= result["t_max"]]
    return result.sort_values("local_date").drop_duplicates(
        "local_date",
        keep="last",
    )


def _day_from_row(row) -> SoilTemperatureDay:
    return SoilTemperatureDay(
        local_date=row.local_date,
        mean_c=round(float(row.t_mean), 1),
        minimum_c=round(float(row.t_min), 1),
        maximum_c=round(float(row.t_max), 1),
        source=str(getattr(row, "data_source", "модельный ряд")),
    )


async def generate_soil_temperature_report(
    latitude: float,
    longitude: float,
    *,
    provider: SoilTemperatureProvider | None = None,
    forecast_days: int = 7,
) -> SoilTemperatureReport:
    if not 1 <= forecast_days <= 15:
        raise ValueError("Горизонт температуры почвы должен быть от 1 до 15 суток")

    resolved_provider = provider or OpenMeteoSoilTemperatureProvider()
    data = await resolved_provider.fetch(latitude, longitude)
    daily = _normalise_daily(data.daily)

    if "data_kind" in daily.columns:
        completed = daily[daily["data_kind"].isin(_COMPLETED_KINDS)].copy()
        future = daily[daily["data_kind"].isin(_FORECAST_KINDS)].copy()
    else:
        completed = daily.iloc[0:0].copy()
        future = daily.copy()

    latest = None
    if not completed.empty:
        latest = _day_from_row(completed.iloc[-1])

    recent = completed.tail(3)
    recent_mean = None
    recent_change = None
    if not recent.empty:
        recent_mean = round(float(recent["t_mean"].mean()), 1)
        if len(recent) >= 2:
            recent_change = round(
                float(recent.iloc[-1]["t_mean"] - recent.iloc[0]["t_mean"]),
                1,
            )

    forecast = tuple(
        _day_from_row(row)
        for row in future.sort_values("local_date").head(forecast_days).itertuples(
            index=False
        )
    )
    return SoilTemperatureReport(
        latest_completed=latest,
        recent_mean_c=recent_mean,
        recent_change_c=recent_change,
        recent_days=int(len(recent)),
        forecast=forecast,
        timezone=data.meta.timezone,
        source=data.meta.source,
        model=data.meta.model,
        depth_label=data.meta.depth_label,
        retrieved_at=data.meta.retrieved_at,
        spatial_resolution_km=data.meta.spatial_resolution_km,
        coverage_start=data.coverage.actual_start,
        coverage_end=data.coverage.actual_end,
        notes=data.coverage.notes,
    )
