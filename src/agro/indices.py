"""Scientifically bounded agrometeorological indicators.

Implemented quantities
----------------------
* Growing degree days (GDD), daily-average method: ``max(0, Tmean - Tbase)``.
  An upper cutoff is applied only when a crop definition explicitly provides it.
* Selyaninov hydrothermal coefficient (HTC/GTC): ``10 * sum(P) / sum(Tmean)``
  over completed warm days with ``Tmean > 10°C``.
* Completed-period precipitation minus provider reference ET0. This is a
  screening difference, not a root-zone water balance or an irrigation dose.
* Forecast daily minimum-temperature screening at 2 m. This is not a crop
  damage model and not a plant/surface-temperature estimate.

The module never predicts yield, profitability or phenological stage.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd

from src.agro.crop_catalog import CROPS, get_crop, get_crop_phases, normalise_crop_key

_COMPLETED_KINDS = frozenset({"observation", "reanalysis", "operational_past"})
_FORECAST_KINDS = frozenset({"current_forecast", "forecast"})

# Operational policy thresholds. They are not crop-damage thresholds.
FROST_WATCH_T_C = 2.0
FROST_FREEZE_T_C = 0.0
FROST_STATUS_RISK = "risk_detected"
FROST_STATUS_NO_RISK = "no_risk_in_valid_forecast"
FROST_STATUS_INSUFFICIENT = "insufficient_forecast_data"

GDD_BASE: dict[str, float] = {
    crop_key: float(crop["t_base"]) for crop_key, crop in CROPS.items()
}
GDD_PHASE_LABELS: dict[str, tuple[str, ...]] = {
    crop_key: tuple(crop["phases"]) for crop_key, crop in CROPS.items()
}


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _as_utc(value: pd.Timestamp | str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _prepare_daily(df_daily: pd.DataFrame, columns: set[str]) -> pd.DataFrame:
    missing = columns.difference(df_daily.columns)
    if missing:
        raise ValueError(f"Missing weather columns: {', '.join(sorted(missing))}")

    optional = {"data_kind", "data_source", "local_date"}.intersection(
        df_daily.columns
    )
    frame = df_daily[list(columns | optional)].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["date"])

    if "local_date" in frame.columns:
        local_day = pd.to_datetime(frame["local_date"], errors="coerce")
        frame["_day"] = local_day.dt.normalize()
        frame = frame.dropna(subset=["_day"])
    else:
        frame["_day"] = frame["date"].dt.tz_localize(None).dt.normalize()

    frame = frame.sort_values(["_day", "date"])
    return frame.drop_duplicates("_day", keep="last")


def _completed(frame: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if "data_kind" in frame.columns:
        return frame[frame["data_kind"].isin(_COMPLETED_KINDS)].copy()
    return frame[frame["date"] < as_of.normalize()].copy()


def _forecast(frame: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if "data_kind" in frame.columns:
        return frame[frame["data_kind"].isin(_FORECAST_KINDS)].copy()
    return frame[frame["date"] >= as_of.normalize()].copy()


def _window_stats(
    frame: pd.DataFrame,
    *,
    expected_days: int,
) -> tuple[int, int, float | None]:
    valid_days = int(frame["_day"].nunique())
    missing_days = max(0, expected_days - valid_days)
    missing_fraction = (
        round(missing_days / expected_days, 3) if expected_days > 0 else None
    )
    return valid_days, missing_days, missing_fraction


def _source_counts(frame: pd.DataFrame) -> dict[str, int]:
    if frame.empty or "data_kind" not in frame.columns:
        return {}
    return {
        str(key): int(value)
        for key, value in frame["data_kind"].value_counts().to_dict().items()
    }


def calc_htc(
    df_daily: pd.DataFrame,
    window_days: int = 30,
    min_valid_warm_days: int = 20,
    max_missing_fraction: float = 0.10,
    *,
    as_of: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Calculate Selyaninov HTC over completed days only.

    The coefficient is withheld when the requested window has too many missing
    days or too few completed warm days. No universal crop recommendation is
    derived from the coefficient.
    """
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    if min_valid_warm_days <= 0:
        raise ValueError("min_valid_warm_days must be positive")
    if not 0 <= max_missing_fraction <= 1:
        raise ValueError("max_missing_fraction must be between 0 and 1")

    now = _as_utc(as_of or _now_utc())
    frame = _prepare_daily(df_daily, {"date", "t_mean", "precip_sum"})
    completed = _completed(frame, now)
    if completed.empty:
        return {
            "htc": None,
            "sum_precip_mm": None,
            "sum_t_above10": None,
            "window_days": window_days,
            "expected_days": window_days,
            "valid_days": 0,
            "available_days": 0,
            "missing_days": window_days,
            "missing_fraction": 1.0,
            "min_valid_days": min_valid_warm_days,
            "period_start": None,
            "period_end": None,
            "source_counts": {},
            "units": "dimensionless",
            "interpretation": "нет завершённых суток для расчёта",
            "method_reference": (
                "ГТК Селянинова: 10·ΣP/ΣTср по завершённым суткам "
                "с Tср > 10°C"
            ),
        }

    period_end = completed["_day"].max()
    period_start = period_end - pd.Timedelta(days=window_days - 1)
    raw_window = completed[
        (completed["_day"] >= period_start)
        & (completed["_day"] <= period_end)
    ]
    window = raw_window.dropna(subset=["t_mean", "precip_sum"])
    valid_days, missing_days, missing_fraction = _window_stats(
        window,
        expected_days=window_days,
    )
    warm = window[window["t_mean"] > 10.0]
    warm_days = int(warm["_day"].nunique())
    sum_precip = float(warm["precip_sum"].clip(lower=0).sum())
    sum_temperature = float(warm["t_mean"].sum())

    value: float | None = None
    if missing_fraction is not None and missing_fraction > max_missing_fraction:
        interpretation = (
            f"не рассчитан: пропущено {missing_days} из {window_days} суток "
            f"({missing_fraction * 100:.1f}%)"
        )
    elif warm_days < min_valid_warm_days:
        interpretation = (
            f"не рассчитан: валидных тёплых суток {warm_days}, "
            f"требуется не менее {min_valid_warm_days}"
        )
    elif sum_temperature <= 0:
        interpretation = "не рассчитан: сумма температур тёплого периода равна нулю"
    else:
        value = round(10.0 * sum_precip / sum_temperature, 3)
        interpretation = (
            "коэффициент рассчитан; интерпретация зависит от культуры, "
            "региона и выбранного периода"
        )

    return {
        "htc": value,
        "sum_precip_mm": round(sum_precip, 1),
        "sum_t_above10": round(sum_temperature, 1),
        "window_days": window_days,
        "expected_days": window_days,
        "valid_days": valid_days,
        "available_days": warm_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "min_valid_days": min_valid_warm_days,
        "period_start": period_start.date().isoformat(),
        "period_end": period_end.date().isoformat(),
        "source_counts": _source_counts(window),
        "units": "dimensionless",
        "interpretation": interpretation,
        "method_reference": (
            "ГТК Селянинова: 10·ΣP/ΣTср по завершённым суткам "
            "с Tср > 10°C"
        ),
    }


def calc_gdd(
    df_daily: pd.DataFrame,
    crop: str,
    season_start: pd.Timestamp | None = None,
    *,
    max_missing_fraction: float = 0.10,
    as_of: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Calculate completed-period and forecast GDD without phase inference.

    When a season start is supplied, rows are filtered by the local calendar
    day stored in ``local_date``. This prevents UTC offsets from pulling one or
    more pre-sowing days into the seasonal sum.
    """
    if not 0 <= max_missing_fraction <= 1:
        raise ValueError("max_missing_fraction must be between 0 and 1")

    crop_key = normalise_crop_key(crop)
    definition = get_crop(crop_key)
    t_base = float(definition["t_base"])
    t_upper = definition["t_upper"]
    now = _as_utc(as_of or _now_utc())
    frame = _prepare_daily(df_daily, {"date", "t_max", "t_min"}).dropna(
        subset=["t_max", "t_min"]
    )

    season_start_day: pd.Timestamp | None = None
    if season_start is not None:
        season_start_day = pd.Timestamp(pd.Timestamp(season_start).date())
        frame = frame[frame["_day"] >= season_start_day].copy()

    daily_mean = (frame["t_max"] + frame["t_min"]) / 2.0
    if t_upper is not None:
        daily_mean = daily_mean.clip(upper=float(t_upper))
    frame["gdd_day"] = (daily_mean - t_base).clip(lower=0)

    past = _completed(frame, now)
    future = _forecast(frame, now).sort_values("_day").head(7)
    past_gdd = None if past.empty else round(float(past["gdd_day"].sum()), 1)
    forecast_gdd = (
        None if future.empty else round(float(future["gdd_day"].sum()), 1)
    )

    period_start = None if past.empty else past["_day"].min()
    period_end = None if past.empty else past["_day"].max()
    start_reached = bool(
        season_start_day is not None
        and period_start is not None
        and period_start <= season_start_day
    )
    expected_start = season_start_day if season_start_day is not None else period_start
    if expected_start is None or period_end is None:
        expected_days = 0
    else:
        expected_days = max(0, (period_end - expected_start).days + 1)
    valid_days, missing_days, missing_fraction = _window_stats(
        past,
        expected_days=expected_days,
    )
    period_is_season = bool(
        start_reached
        and valid_days > 0
        and missing_fraction is not None
        and missing_fraction <= max_missing_fraction
    )

    contribution_by_kind: dict[str, float] = {}
    if not past.empty and "data_kind" in past.columns:
        contribution_by_kind = {
            str(kind): round(float(group["gdd_day"].sum()), 1)
            for kind, group in past.groupby("data_kind")
        }

    if season_start_day is None:
        period_note = "дата начала сезона не задана; сумма относится к доступному периоду"
    elif not start_reached:
        period_note = (
            "нет валидной строки на локальную дату начала сезона; "
            "сезонная сумма не заявляется"
        )
    elif not period_is_season:
        period_note = (
            "ряд достигает даты сезона, но доля пропусков превышает допустимый "
            f"порог {max_missing_fraction * 100:.0f}%"
        )
    else:
        period_note = "дата начала сезона покрыта, доля пропусков допустима"

    return {
        "crop": crop_key,
        "t_base": t_base,
        "t_upper": t_upper,
        "gdd_past": past_gdd,
        "gdd_forecast_7d": forecast_gdd,
        "current_phase": None,
        "next_phase": None,
        "period_is_season": period_is_season,
        "coverage_start_reached": start_reached,
        "period_start": None if period_start is None else period_start.date().isoformat(),
        "period_end": None if period_end is None else period_end.date().isoformat(),
        "season_start": (
            None if season_start_day is None else season_start_day.date().isoformat()
        ),
        "valid_days": valid_days,
        "expected_days": expected_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "source_counts": _source_counts(past),
        "contribution_by_kind": contribution_by_kind,
        "forecast_days": int(future["_day"].nunique()),
        "phase_labels": get_crop_phases(crop_key),
        "period_note": period_note,
        "phenology_note": (
            "фенофаза автоматически не определяется; отображается только "
            "наблюдение пользователя"
        ),
        "units": "°C·сут",
        "method_reference": (
            "McMaster & Wilhelm (1997), daily-average GDD: "
            "max(0, min(Tср, Tupper) − Tbase)"
        ),
        "t_base_note": (
            "операционный параметр каталога; требуется валидация по сорту и региону"
        ),
    }


def calc_frost_risk(
    df_daily: pd.DataFrame,
    utc_offset_seconds: int = 0,
    *,
    crop: str | None = None,
    phase: str | None = None,
    elevation_m: float | None = None,
    watch_threshold_c: float = FROST_WATCH_T_C,
    freeze_threshold_c: float = FROST_FREEZE_T_C,
    as_of: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Screen forecast daily 2 m air Tmin; do not infer crop damage.

    A missing forecast or missing forecast Tmin is represented as an explicit
    insufficient-data status. It is never interpreted as a frost-free result.
    """
    if freeze_threshold_c > watch_threshold_c:
        raise ValueError("freeze threshold cannot exceed watch threshold")

    now = _as_utc(as_of or _now_utc())
    frame = _prepare_daily(df_daily, {"date", "t_min"})
    future_all = _forecast(frame, now).sort_values("_day")
    future = future_all.dropna(subset=["t_min"]).copy()
    offset = timedelta(seconds=utc_offset_seconds)
    local_today = pd.Timestamp((now + offset).date())
    alerts: list[dict[str, Any]] = []

    for _, row in future.iterrows():
        t_min = float(row["t_min"])
        if t_min > watch_threshold_c:
            continue
        event_day = pd.Timestamp(row["_day"])
        lead_days = max(0, int((event_day - local_today).days))
        level = "critical" if t_min <= freeze_threshold_c else "warning"
        alerts.append(
            {
                "date": event_day.date().isoformat(),
                "date_local": event_day.strftime("%d.%m.%Y"),
                "event_date": event_day.date().isoformat(),
                "t_min": round(t_min, 1),
                "min_temp": round(t_min, 1),
                "lead_days": lead_days,
                # Compatibility field; daily data do not provide event hour.
                "lead_hours": lead_days * 24,
                "level": level,
                "crop_key": crop,
                "phase": phase,
                "elevation_m": elevation_m,
                "data_source": row.get("data_source"),
                "action": (
                    "сверить локальный прогноз, измерения на поле, фактическую "
                    "фазу и условия микрорельефа"
                ),
            }
        )

    forecast_days = int(future_all["_day"].nunique())
    valid_forecast_days = int(future["_day"].nunique())
    missing_forecast_days = max(0, forecast_days - valid_forecast_days)
    missing_fraction = (
        round(missing_forecast_days / forecast_days, 3)
        if forecast_days > 0
        else None
    )
    if valid_forecast_days == 0:
        status = FROST_STATUS_INSUFFICIENT
        status_note = (
            "прогнозные строки отсутствуют"
            if forecast_days == 0
            else "в прогнозных строках отсутствует Tmin воздуха"
        )
    elif alerts:
        status = FROST_STATUS_RISK
        status_note = "в валидном прогнозе есть события ниже порога внимания"
    else:
        status = FROST_STATUS_NO_RISK
        status_note = "в валидных прогнозных сутках события ниже порога не выявлены"

    return {
        "available": valid_forecast_days > 0,
        "status": status,
        "status_note": status_note,
        "alerts": alerts,
        "frost_free_days_7d": max(0, valid_forecast_days - len(alerts)),
        "forecast_contains_48h": valid_forecast_days >= 2,
        "forecast_days": forecast_days,
        "valid_forecast_days": valid_forecast_days,
        "missing_forecast_days": missing_forecast_days,
        "missing_fraction": missing_fraction,
        "watch_threshold_c": watch_threshold_c,
        "freeze_threshold_c": freeze_threshold_c,
        "source_counts": _source_counts(future),
        "all_forecast_source_counts": _source_counts(future_all),
        "units": "°C (Tmin воздуха на высоте 2 м)",
        "method_reference": (
            "оперативный скрининг прогнозной суточной Tmin воздуха 2 м; "
            "2°C — порог внимания, 0°C — порог замерзания воды; это не "
            "температура растений и не порог повреждения культуры"
        ),
        "context": {
            "crop": crop,
            "phase": phase,
            "elevation_m": elevation_m,
        },
    }


def calc_et0_balance(
    df_daily: pd.DataFrame,
    window_days: int = 7,
    *,
    max_missing_fraction: float = 0.20,
    as_of: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Return completed-period ``P - provider ET0`` as a screening quantity."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    if not 0 <= max_missing_fraction <= 1:
        raise ValueError("max_missing_fraction must be between 0 and 1")

    now = _as_utc(as_of or _now_utc())
    frame = _prepare_daily(df_daily, {"date", "precip_sum", "et0_sum"})
    completed = _completed(frame, now)
    if completed.empty:
        return {
            "available": False,
            "precip_sum_mm": None,
            "et0_sum_mm": None,
            "balance_mm": None,
            "status": "нет завершённых суток",
            "window_days": window_days,
            "expected_days": window_days,
            "valid_days": 0,
            "missing_days": window_days,
            "missing_fraction": 1.0,
            "period_start": None,
            "period_end": None,
            "source_counts": {},
            "units": "мм",
            "et0_source": "provider et0_fao_evapotranspiration",
            "method_reference": (
                "простая разность P−ET0 по завершённым суткам; не учитывает "
                "Kc, запасы влаги, сток, инфильтрацию и глубину корней"
            ),
        }

    period_end = completed["_day"].max()
    period_start = period_end - pd.Timedelta(days=window_days - 1)
    raw_window = completed[
        (completed["_day"] >= period_start)
        & (completed["_day"] <= period_end)
    ]
    window = raw_window.dropna(subset=["precip_sum", "et0_sum"])
    valid_days, missing_days, missing_fraction = _window_stats(
        window,
        expected_days=window_days,
    )

    available = bool(
        valid_days > 0
        and missing_fraction is not None
        and missing_fraction <= max_missing_fraction
    )
    precip: float | None = None
    et0: float | None = None
    balance: float | None = None
    if not available:
        status = f"не рассчитано: валидных суток {valid_days} из {window_days}"
    else:
        precip = round(float(window["precip_sum"].clip(lower=0).sum()), 1)
        et0 = round(float(window["et0_sum"].clip(lower=0).sum()), 1)
        balance = round(precip - et0, 1)
        if balance > 0:
            status = "сумма осадков выше суммы ET₀ за выбранное окно"
        elif balance < 0:
            status = "сумма осадков ниже суммы ET₀ за выбранное окно"
        else:
            status = "суммы осадков и ET₀ равны за выбранное окно"

    return {
        "available": available,
        "precip_sum_mm": precip,
        "et0_sum_mm": et0,
        "balance_mm": balance,
        "status": status,
        "window_days": window_days,
        "expected_days": window_days,
        "valid_days": valid_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "period_start": period_start.date().isoformat(),
        "period_end": period_end.date().isoformat(),
        "source_counts": _source_counts(window),
        "units": "мм",
        "et0_source": "provider et0_fao_evapotranspiration",
        "method_reference": (
            "простая разность P−ET0 по завершённым суткам; не учитывает Kc, "
            "запасы влаги, сток, инфильтрацию и глубину корней"
        ),
    }


def compute_all_indices(
    df_daily: pd.DataFrame,
    crop: str,
    *,
    utc_offset_seconds: int = 0,
    season_start: pd.Timestamp | None = None,
    phase: str | None = None,
    elevation_m: float | None = None,
    as_of: pd.Timestamp | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        "htc": calc_htc(df_daily, as_of=as_of),
        "gdd": calc_gdd(df_daily, crop, season_start=season_start, as_of=as_of),
        "frost": calc_frost_risk(
            df_daily,
            utc_offset_seconds=utc_offset_seconds,
            crop=crop,
            phase=phase,
            elevation_m=elevation_m,
            as_of=as_of,
        ),
        "et0_bal": calc_et0_balance(df_daily, as_of=as_of),
    }


def format_indices_for_rag(
    indices: dict[str, dict[str, Any]],
    crop: str,
    crop_phase: str | None = None,
) -> str:
    lines = ["=== ПРОВЕРЯЕМЫЕ АГРОМЕТЕОДАННЫЕ ===", f"Культура: {crop}"]
    if crop_phase:
        lines.append(f"Фаза (наблюдение пользователя): {crop_phase}")
    else:
        lines.append("Фаза: не задана пользователем")

    htc = indices.get("htc", {})
    if htc.get("htc") is None:
        lines.append(f"ГТК: не рассчитан — {htc.get('interpretation', 'нет данных')}")
    else:
        missing_fraction = htc.get("missing_fraction") or 0.0
        lines.append(
            f"ГТК за {htc['window_days']} завершённых суток: {htc['htc']:.3f}; "
            f"пропуски {missing_fraction * 100:.1f}%"
        )

    gdd = indices.get("gdd", {})
    gdd_past = gdd.get("gdd_past")
    if gdd_past is None:
        lines.append("ГДД: не рассчитаны — нет завершённых валидных суток")
    else:
        scope = "с начала сезона" if gdd.get("period_is_season") else "за доступный период"
        lines.append(
            f"ГДД {scope}: {gdd_past:.1f} °C·сут; "
            f"Tbase={gdd.get('t_base')}°C; {gdd.get('period_note', '')}"
        )

    frost = indices.get("frost", {})
    alerts = frost.get("alerts", [])
    if frost.get("status") == FROST_STATUS_INSUFFICIENT:
        lines.append(
            "Температурный скрининг: не выполнен — "
            f"{frost.get('status_note', 'недостаточно прогнозных данных')}"
        )
    elif alerts:
        first = alerts[0]
        lines.append(
            f"Температурный скрининг: Tmin 2 м {first['t_min']}°C, "
            f"дата {first['date_local']}"
        )
    else:
        lines.append(
            "Температурный скрининг: в валидных прогнозных сутках "
            "событий по заданной политике нет"
        )

    water = indices.get("et0_bal", {})
    if water.get("balance_mm") is None:
        lines.append(f"P−ET0: не рассчитано — {water.get('status', 'нет данных')}")
    else:
        lines.append(
            f"P−ET0 за {water['window_days']} завершённых суток: "
            f"{water['balance_mm']:+.1f} мм; не является дозой полива"
        )
    lines.append("=== КОНЕЦ ПРОВЕРЯЕМЫХ ДАННЫХ ===")
    return "\n".join(lines)
