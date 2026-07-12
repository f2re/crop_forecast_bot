"""Season-to-date climate reference comparison.

The calculation compares a completed current season with same-length windows
from a fixed multi-year reanalysis reference. It uses empirical distributions
and does not fit a parametric drought distribution; therefore it is not SPI or
SPEI and does not represent a station climatological normal.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from src.agro.crop_catalog import get_crop

_COMPLETED_KINDS = frozenset({"observation", "reanalysis", "operational_past"})
_DEFAULT_REFERENCE_START = date(1991, 1, 1)
_DEFAULT_REFERENCE_END = date(2020, 12, 31)
_DEFAULT_MIN_REFERENCE_YEARS = 20
_DEFAULT_MAX_MISSING_FRACTION = 0.10
_DEFAULT_MIN_CURRENT_DAYS = 7
_DEFAULT_MAX_WINDOW_DAYS = 366
_DEFAULT_DRY_DAY_THRESHOLD_MM = 1.0


def _as_day(value: date | datetime | pd.Timestamp) -> pd.Timestamp:
    if isinstance(value, datetime):
        return pd.Timestamp(value.date())
    if isinstance(value, date):
        return pd.Timestamp(value)
    return pd.Timestamp(value.date())


def _prepare_daily(
    frame: pd.DataFrame,
    *,
    completed_only: bool,
) -> pd.DataFrame:
    required = {"date", "t_mean", "precip_sum", "et0_sum"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing climate columns: {', '.join(sorted(missing))}")

    if completed_only and "data_kind" not in frame.columns:
        raise ValueError("Current climate series requires explicit data_kind")

    optional = {"local_date", "data_kind", "data_source"}.intersection(frame.columns)
    prepared = frame[list(required | optional)].copy()
    prepared["date"] = pd.to_datetime(prepared["date"], utc=True, errors="coerce")
    prepared = prepared.dropna(subset=["date"])

    if "local_date" in prepared.columns:
        local_days = pd.to_datetime(prepared["local_date"], errors="coerce")
        prepared["_day"] = local_days.dt.normalize()
    else:
        prepared["_day"] = prepared["date"].dt.tz_localize(None).dt.normalize()
    prepared = prepared.dropna(subset=["_day"])

    for column in ("t_mean", "precip_sum", "et0_sum"):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    prepared.loc[prepared["precip_sum"] < 0, "precip_sum"] = float("nan")
    prepared.loc[prepared["et0_sum"] < 0, "et0_sum"] = float("nan")

    if completed_only and "data_kind" in prepared.columns:
        prepared = prepared[prepared["data_kind"].isin(_COMPLETED_KINDS)].copy()

    # Partition before de-duplication so a forecast row cannot displace a
    # completed row for the same local calendar day.
    return prepared.sort_values(["_day", "date"]).drop_duplicates("_day", keep="last")


def _valid_fraction(series: pd.Series, expected_days: int) -> float:
    if expected_days <= 0:
        return 0.0
    return float(series.notna().sum()) / expected_days


def _longest_run(values: Iterable[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _gdd_sum(series: pd.Series, *, t_base: float, t_upper: float | None) -> float:
    values = series.astype(float)
    if t_upper is not None:
        values = values.clip(upper=t_upper)
    return float((values - t_base).clip(lower=0).sum())


def _empty_metric(unit: str, current: float | int | None = None) -> dict[str, Any]:
    return {
        "available": False,
        "current": current,
        "unit": unit,
        "reference_years": 0,
        "reference_mean": None,
        "reference_median": None,
        "p10": None,
        "p25": None,
        "p75": None,
        "p90": None,
        "anomaly_from_mean": None,
        "anomaly_from_median": None,
        "percent_of_mean": None,
        "empirical_percentile": None,
        "position": "недостаточно данных",
    }


def _position(percentile: float) -> str:
    if percentile < 10:
        return "ниже 10-го процентиля"
    if percentile < 25:
        return "между 10-м и 25-м процентилями"
    if percentile <= 75:
        return "между 25-м и 75-м процентилями"
    if percentile <= 90:
        return "между 75-м и 90-м процентилями"
    return "выше 90-го процентиля"


def _summarise_metric(
    current: float | int | None,
    samples: list[tuple[int, float]],
    *,
    unit: str,
    min_reference_years: int,
) -> dict[str, Any]:
    result = _empty_metric(unit, current)
    if current is None or len(samples) < min_reference_years:
        result["reference_years"] = len(samples)
        return result

    values = pd.Series([value for _, value in samples], dtype="float64")
    current_value = float(current)
    less = int((values < current_value).sum())
    equal = int((values == current_value).sum())
    percentile = 100.0 * (less + 0.5 * equal) / len(values)
    mean = float(values.mean())
    median = float(values.median())
    result.update(
        {
            "available": True,
            "current": round(current_value, 2),
            "reference_years": len(values),
            "reference_year_list": tuple(year for year, _ in samples),
            "reference_mean": round(mean, 2),
            "reference_median": round(median, 2),
            "p10": round(float(values.quantile(0.10)), 2),
            "p25": round(float(values.quantile(0.25)), 2),
            "p75": round(float(values.quantile(0.75)), 2),
            "p90": round(float(values.quantile(0.90)), 2),
            "anomaly_from_mean": round(current_value - mean, 2),
            "anomaly_from_median": round(current_value - median, 2),
            "percent_of_mean": (
                None if abs(mean) < 1e-12 else round(current_value / mean * 100.0, 1)
            ),
            "empirical_percentile": round(percentile, 1),
            "position": _position(percentile),
        }
    )
    return result


def _reference_anchor(year: int, month: int, day: int) -> pd.Timestamp | None:
    try:
        return pd.Timestamp(date(year, month, day))
    except ValueError:
        # A 29 February season has no exact counterpart in non-leap years. Do
        # not shift it silently to another calendar day.
        return None


def _metric_available(
    series: pd.Series,
    expected_days: int,
    max_missing_fraction: float,
) -> bool:
    return _valid_fraction(series, expected_days) >= 1.0 - max_missing_fraction


def calc_season_climate_reference(
    current_daily: pd.DataFrame,
    reference_daily: pd.DataFrame,
    *,
    crop: str,
    season_start: date | datetime | pd.Timestamp,
    reference_start: date = _DEFAULT_REFERENCE_START,
    reference_end: date = _DEFAULT_REFERENCE_END,
    min_reference_years: int = _DEFAULT_MIN_REFERENCE_YEARS,
    max_missing_fraction: float = _DEFAULT_MAX_MISSING_FRACTION,
    min_current_days: int = _DEFAULT_MIN_CURRENT_DAYS,
    max_window_days: int = _DEFAULT_MAX_WINDOW_DAYS,
    dry_day_threshold_mm: float = _DEFAULT_DRY_DAY_THRESHOLD_MM,
) -> dict[str, Any]:
    """Compare a completed season-to-date period with a reanalysis reference.

    Reference samples are same-length windows beginning on the same month/day
    in each reference year. Empirical percentiles do not assume a normal or
    gamma distribution. A metric is published only when both the current period
    and at least ``min_reference_years`` historical windows pass completeness
    checks.
    """
    if min_reference_years < 1:
        raise ValueError("min_reference_years must be positive")
    if not 0 <= max_missing_fraction <= 1:
        raise ValueError("max_missing_fraction must be between 0 and 1")
    if min_current_days < 1:
        raise ValueError("min_current_days must be positive")
    if max_window_days < min_current_days:
        raise ValueError("max_window_days must be at least min_current_days")
    if dry_day_threshold_mm <= 0:
        raise ValueError("dry_day_threshold_mm must be positive")
    if reference_start > reference_end:
        raise ValueError("reference_start must not be after reference_end")

    season_start_day = _as_day(season_start)
    current = _prepare_daily(current_daily, completed_only=True)
    current = current[current["_day"] >= season_start_day].copy()
    reference = _prepare_daily(reference_daily, completed_only=False)
    if "data_kind" in reference.columns:
        reference = reference[reference["data_kind"] == "reanalysis"].copy()
    reference_start_day = pd.Timestamp(reference_start)
    reference_end_day = pd.Timestamp(reference_end)
    reference = reference[
        (reference["_day"] >= reference_start_day)
        & (reference["_day"] <= reference_end_day)
    ].copy()

    base_result: dict[str, Any] = {
        "available": False,
        "period_is_season": False,
        "season_start": season_start_day.date().isoformat(),
        "period_start": None,
        "period_end": None,
        "window_days": 0,
        "calendar_missing_days": 0,
        "calendar_missing_fraction": None,
        "reference_start": reference_start.isoformat(),
        "reference_end": reference_end.isoformat(),
        "reference_kind": "fixed ERA5-Land reanalysis reference distribution",
        "min_reference_years": min_reference_years,
        "max_missing_fraction": max_missing_fraction,
        "dry_day_threshold_mm": dry_day_threshold_mm,
        "metrics": {
            "mean_temperature_c": _empty_metric("°C"),
            "precip_sum_mm": _empty_metric("мм"),
            "et0_sum_mm": _empty_metric("мм"),
            "gdd_c_day": _empty_metric("°C·сут"),
            "dry_days": _empty_metric("сут"),
            "max_dry_spell_days": _empty_metric("сут"),
        },
        "status": "нет завершённого сезонного периода",
        "method_note": (
            "сравнение с окнами той же длины и той же календарной даты старта; "
            "процентиль эмпирический"
        ),
        "limitations": (
            "это сравнение с реанализной сеткой, а не станционная норма; "
            "SPI/SPEI и вероятность ущерба не рассчитываются"
        ),
    }
    if current.empty:
        return base_result

    period_start = pd.Timestamp(current["_day"].min())
    period_end = pd.Timestamp(current["_day"].max())
    window_days = int((period_end - season_start_day).days) + 1
    row_days = int(current["_day"].nunique())
    calendar_missing_days = max(0, window_days - row_days)
    calendar_missing_fraction = (
        calendar_missing_days / window_days if window_days else 1.0
    )
    period_is_season = period_start == season_start_day

    base_result.update(
        {
            "period_is_season": period_is_season,
            "period_start": period_start.date().isoformat(),
            "period_end": period_end.date().isoformat(),
            "window_days": window_days,
            "calendar_missing_days": calendar_missing_days,
            "calendar_missing_fraction": round(calendar_missing_fraction, 3),
        }
    )
    if not period_is_season:
        base_result["status"] = "ряд не достигает локальной даты начала сезона"
        return base_result
    if window_days < min_current_days:
        base_result["status"] = (
            f"для сравнения требуется не менее {min_current_days} завершённых суток"
        )
        return base_result
    if window_days > max_window_days:
        base_result["status"] = (
            f"сравнение ограничено окнами до {max_window_days} суток"
        )
        return base_result
    if calendar_missing_fraction > max_missing_fraction:
        base_result["status"] = "слишком много пропущенных календарных суток"
        return base_result

    crop_definition = get_crop(crop)
    t_base = float(crop_definition["t_base"])
    raw_t_upper = crop_definition.get("t_upper")
    t_upper = None if raw_t_upper is None else float(raw_t_upper)

    current_t = current["t_mean"]
    current_p = current["precip_sum"]
    current_et0 = current["et0_sum"]
    current_values: dict[str, float | int | None] = {
        "mean_temperature_c": (
            float(current_t.mean())
            if _metric_available(current_t, window_days, max_missing_fraction)
            else None
        ),
        "precip_sum_mm": (
            float(current_p.sum())
            if _metric_available(current_p, window_days, max_missing_fraction)
            else None
        ),
        "et0_sum_mm": (
            float(current_et0.sum())
            if _metric_available(current_et0, window_days, max_missing_fraction)
            else None
        ),
        "gdd_c_day": (
            _gdd_sum(current_t.dropna(), t_base=t_base, t_upper=t_upper)
            if _metric_available(current_t, window_days, max_missing_fraction)
            else None
        ),
        "dry_days": None,
        "max_dry_spell_days": None,
    }
    current_precip_continuous = bool(
        calendar_missing_days == 0 and current_p.notna().sum() == window_days
    )
    if current_precip_continuous:
        dry_flags = (
            current.sort_values("_day")["precip_sum"] < dry_day_threshold_mm
        ).tolist()
        current_values["dry_days"] = int(sum(dry_flags))
        current_values["max_dry_spell_days"] = _longest_run(dry_flags)

    samples: dict[str, list[tuple[int, float]]] = {
        key: [] for key in current_values
    }
    for year in range(reference_start.year, reference_end.year + 1):
        anchor = _reference_anchor(year, season_start_day.month, season_start_day.day)
        if anchor is None:
            continue
        sample_end = anchor + timedelta(days=window_days - 1)
        if anchor < reference_start_day or sample_end > reference_end_day:
            continue
        sample = reference[
            (reference["_day"] >= anchor) & (reference["_day"] <= sample_end)
        ].sort_values("_day")
        sample_row_days = int(sample["_day"].nunique())
        sample_calendar_missing = max(0, window_days - sample_row_days)
        if sample_calendar_missing / window_days > max_missing_fraction:
            continue

        t_series = sample["t_mean"]
        p_series = sample["precip_sum"]
        et0_series = sample["et0_sum"]
        if _metric_available(t_series, window_days, max_missing_fraction):
            samples["mean_temperature_c"].append((year, float(t_series.mean())))
            samples["gdd_c_day"].append(
                (year, _gdd_sum(t_series.dropna(), t_base=t_base, t_upper=t_upper))
            )
        if _metric_available(p_series, window_days, max_missing_fraction):
            samples["precip_sum_mm"].append((year, float(p_series.sum())))
        if _metric_available(et0_series, window_days, max_missing_fraction):
            samples["et0_sum_mm"].append((year, float(et0_series.sum())))
        if sample_calendar_missing == 0 and p_series.notna().sum() == window_days:
            dry_flags = (p_series < dry_day_threshold_mm).tolist()
            samples["dry_days"].append((year, float(sum(dry_flags))))
            samples["max_dry_spell_days"].append(
                (year, float(_longest_run(dry_flags)))
            )

    units = {
        "mean_temperature_c": "°C",
        "precip_sum_mm": "мм",
        "et0_sum_mm": "мм",
        "gdd_c_day": "°C·сут",
        "dry_days": "сут",
        "max_dry_spell_days": "сут",
    }
    metrics = {
        key: _summarise_metric(
            current_values[key],
            samples[key],
            unit=units[key],
            min_reference_years=min_reference_years,
        )
        for key in current_values
    }
    base_result["metrics"] = metrics
    base_result["available"] = any(metric["available"] for metric in metrics.values())
    base_result["status"] = (
        "сравнение рассчитано по реанализной базе"
        if base_result["available"]
        else "недостаточно валидных лет реанализной базы"
    )
    base_result["t_base_c"] = t_base
    base_result["t_upper_c"] = t_upper
    return base_result
