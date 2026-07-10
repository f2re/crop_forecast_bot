"""Scientifically bounded agrometeorological indicators.

Implemented quantities
----------------------
* GDD: daily-average method described by McMaster & Wilhelm (1997),
  ``max(0, min(Tmean, Tupper) - Tbase)`` in °C·day. ``Tupper`` is applied only
  when explicitly configured for the crop.
* Selyaninov hydrothermal coefficient (HTC/GTC):
  ``10 * sum(P) / sum(Tmean)`` for completed days with ``Tmean > 10°C``.
* Water-screening difference: completed-period precipitation minus provider
  reference ET0. It is not a root-zone water balance or an irrigation dose.
* Frost watch: configurable operational screening of forecast 2 m air Tmin.
  It is not a crop-damage model and not plant/surface temperature.

No function in this module predicts yield, profitability or phenology.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd

from src.agro.crop_catalog import CROPS, get_crop, get_crop_phases, normalise_crop_key

_COMPLETED_KINDS = frozenset({"observation", "reanalysis", "operational_past"})
_FORECAST_KINDS = frozenset({"current_forecast", "forecast"})

# Operational policy thresholds, not crop damage thresholds.
FROST_WATCH_T_C = 2.0
FROST_FREEZE_T_C = 0.0

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
    optional = {"data_kind", "data_source"}.intersection(df_daily.columns)
    frame = df_daily[list(columns | optional)].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["date"])
    frame = frame.sort_values("date")
    frame["_day"] = frame["date"].dt.normalize()
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


def calc_htc(
    df_daily: pd.DataFrame,
    window_days: int = 30,
    min_valid_warm_days: int = 20,
    max_missing_fraction: float = 0.10,
    *,
    as_of: pd.Timestamp | None = None,
) -> dict:
    """Calculate Selyaninov HTC over completed days only.

    The result is withheld when the requested window has too many missing days
    or too few completed warm days. No universal crop recommendation is derived
    from the coefficient.
    """
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    if not 0 <= max_missing_fraction <= 1:
        raise ValueError("max_missing_fraction must be between 0 and 1")

    now = _as_utc(as_of or _now_utc())
    frame = _prepare_daily(df_daily, {"date", "t_mean", "precip_sum"})
    completed = _completed(frame, now)
    if completed.empty:
        return {
            "htc": None,
            "sum_precip_mm": 0.0,
            "sum_t_above10": 0.0,
            "window_days": window_days,
            "expected_days": window_days,
            "valid_days": 0,
            "available_days": 0,
            "missing_days": window_days,
            "missing_fraction": 1.0,
            "min_valid_days": min_valid_warm_days,
            "period_start": None,
            "period_end": None,
            "interpretation": "нет завершённых суток для расчёта",
            "method_note": "ГТК Селянинова по завершённым суткам с Tср > 10°C",
        }

    period_end = completed["_day"].max()
    period_start = period_end - pd.Timedelta(days=window_days - 1)
    window = completed[
        (completed["_day"] >= period_start) & (completed["_day"] <= period_end)
    ].dropna(subset=["t_mean", "precip_sum"])
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
            "коэффициент рассчитан; его агрономическая интерпретация зависит "
            "от культуры, региона и выбранного периода"
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
        "interpretation": interpretation,
        "method_note": "ГТК Селянинова по завершённым суткам с Tср > 10°C",
    }


def calc_gdd(
    df_daily: pd.DataFrame,
    crop: str,
    season_start: pd.Timestamp | None = None,
    *,
    max_missing_fraction: float = 0.10,
    as_of: pd.Timestamp | None = None,
) -> dict:
    """Calculate completed-period and forecast GDD without phase inference."""
    crop_key = normalise_crop_key(crop)
    definition = get_crop(crop_key)
    t_base = float(definition["t_base"])
    t_upper = definition["t_upper"]
    now = _as_utc(as_of or _now_utc())
    frame = _prepare_daily(df_daily, {"date", "t_max", "t_min"}).dropna(
        subset=["t_max", "t_min"]
    )

    normalized_start = _as_utc(season_start) if season_start is not None else None
    if normalized_start is not None:
        frame = frame[frame["date"] >= normalized_start - pd.Timedelta(hours=36)]

    daily_mean = (frame["t_max"] + frame["t_min"]) / 2.0
    if t_upper is not None:
        daily_mean = daily_mean.clip(upper=float(t_upper))
    frame["gdd_day"] = (daily_mean - t_base).clip(lower=0)

    past = _completed(frame, now)
    future = _forecast(frame, now).sort_values("date").head(7)
    past_gdd = round(float(past["gdd_day"].sum()), 1)
    forecast_gdd = round(float(future["gdd_day"].sum()), 1)

    period_start = None if past.empty else past["_day"].min()
    period_end = None if past.empty else past["_day"].max()
    start_reached = bool(
        normalized_start is not None
        and period_start is not None
        and period_start <= normalized_start.normalize() + pd.Timedelta(days=1)
    )
    expected_start = normalized_start.normalize() if start_reached else period_start
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
        and missing_fraction is not None
        and missing_fraction <= max_missing_fraction
    )

    source_counts: dict[str, int] = {}
    if "data_kind" in past.columns:
        source_counts = {
            str(key): int(value)
            for key, value in past["data_kind"].value_counts().to_dict().items()
        }

    if normalized_start is None:
        period_note = "дата начала сезона не задана; показана сумма за доступный период"
    elif not start_reached:
        period_note = "ряд не достигает даты начала сезона; сезонная сумма не заявляется"
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
            None if normalized_start is None else normalized_start.date().isoformat()
        ),
        "valid_days": valid_days,
        "expected_days": expected_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "source_counts": source_counts,
        "phase_labels": get_crop_phases(crop_key),
        "period_note": period_note,
        "phenology_note": (
            "фенофаза автоматически не определяется; отображается только "
            "наблюдение пользователя"
        ),
        "method_note": (
            "GDD = max(0, min(Tср, Tupper) − Tbase); Tupper применяется "
            "только при явной настройке"
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
) -> dict:
    """Screen forecast daily 2 m air Tmin; do not infer crop damage."""
    if freeze_threshold_c > watch_threshold_c:
        raise ValueError("freeze threshold cannot exceed watch threshold")
    now = _as_utc(as_of or _now_utc())
    frame = _prepare_daily(df_daily, {"date", "t_min"}).dropna(subset=["t_min"])
    future = _forecast(frame, now).sort_values("date")
    offset = timedelta(seconds=utc_offset_seconds)
    alerts: list[dict] = []

    for _, row in future.iterrows():
        t_min = float(row["t_min"])
        if t_min > watch_threshold_c:
            continue
        local_day = row["date"] + offset
        lead_days = max(0, int((row["_day"] - now.normalize()).days))
        level = "freeze" if t_min <= freeze_threshold_c else "watch"
        alerts.append(
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "date_local": local_day.strftime("%d.%m.%Y"),
                "event_date": local_day.strftime("%Y-%m-%d"),
                "t_min": round(t_min, 1),
                "min_temp": round(t_min, 1),
                "lead_days": lead_days,
                "lead_hours": lead_days * 24,
                "level": level,
                "crop_key": crop,
                "phase": phase,
                "elevation_m": elevation_m,
                "action": (
                    "сверить локальный прогноз, измерения на поле, фактическую "
                    "фазу и условия микрорельефа"
                ),
            }
        )

    horizon_days = int(future["_day"].nunique())
    return {
        "alerts": alerts,
        "frost_free_days_7d": max(0, horizon_days - len(alerts)),
        "forecast_contains_48h": horizon_days >= 2,
        "watch_threshold_c": watch_threshold_c,
        "freeze_threshold_c": freeze_threshold_c,
        "method_note": (
            "оперативный скрининг прогнозной Tmin воздуха на высоте 2 м; "
            "2°C — консервативный порог внимания, 0°C — порог замерзания воды; "
            "это не температура растений и не порог повреждения культуры"
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
) -> dict:
    """Return completed-period ``P - provider ET0`` as a screening quantity."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    now = _as_utc(as_of or _now_utc())
    frame = _prepare_daily(df_daily, {"date", "precip_sum", "et0_sum"})
    completed = _completed(frame, now)
    if completed.empty:
        return {
            "precip_sum_mm": None,
            "et0_sum_mm": None,
            "balance_mm": None,
            "status": "нет завершённых суток",
            "window_days": window_days,
            "valid_days": 0,
            "missing_days": window_days,
            "missing_fraction": 1.0,
            "period_start": None,
            "period_end": None,
            "et0_source": "provider et0_fao_evapotranspiration",
            "method_note": "P−ET0 не является водным балансом корнеобитаемого слоя",
        }

    period_end = completed["_day"].max()
    period_start = period_end - pd.Timedelta(days=window_days - 1)
    window = completed[
        (completed["_day"] >= period_start) & (completed["_day"] <= period_end)
    ].dropna(subset=["precip_sum", "et0_sum"])
    valid_days, missing_days, missing_fraction = _window_stats(
        window,
        expected_days=window_days,
    )
    if missing_fraction is not None and missing_fraction > max_missing_fraction:
        precip = et0 = balance = None
        status = (
            f"не рассчитано: пропущено {missing_days} из {window_days} суток"
        )
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
        "precip_sum_mm": precip,
        "et0_sum_mm": et0,
        "balance_mm": balance,
        "status": status,
        "window_days": window_days,
        "valid_days": valid_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "period_start": period_start.date().isoformat(),
        "period_end": period_end.date().isoformat(),
        "et0_source": "provider et0_fao_evapotranspiration",
        "method_note": (
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
) -> dict:
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
    indices: dict,
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
        lines.append(
            f"ГТК за {htc['window_days']} завершённых суток: {htc['htc']:.3f}; "
            f"пропуски {htc.get('missing_fraction', 0) * 100:.1f}%"
        )

    gdd = indices.get("gdd", {})
    scope = "с начала сезона" if gdd.get("period_is_season") else "за доступный период"
    lines.append(
        f"ГДД {scope}: {gdd.get('gdd_past', 0):.1f} °C·сут; "
        f"Tbase={gdd.get('t_base')}°C; {gdd.get('period_note', '')}"
    )

    alerts = indices.get("frost", {}).get("alerts", [])
    if alerts:
        first = alerts[0]
        lines.append(
            f"Температурный скрининг: Tmin 2 м {first['t_min']}°C, "
            f"день {first['date_local']}"
        )
    else:
        lines.append("Температурный скрининг: событий по заданной политике нет")

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
