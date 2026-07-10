"""Scientifically bounded agrometeorological indicators.

Sources:
- Selyaninov hydrothermal coefficient: Selyaninov (1937).
- Growing degree days: McMaster & Wilhelm (1997), Agric. For. Meteorol.
- Reference evapotranspiration source: provider ET0 based on FAO-56.

The module does not infer yield. Crop-stage thresholds in the catalogue are not
used as an automatic phenology model until they are validated by crop and region.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pandas as pd

from src.agro.crop_catalog import CROPS, get_crop

logger = logging.getLogger(__name__)

# Compatibility exports, now derived from the single crop catalogue.
GDD_BASE: dict[str, float] = {
    crop_key: float(crop["t_base"]) for crop_key, crop in CROPS.items()
}
GDD_PHENOLOGY: dict[str, dict[str, int]] = {
    crop_key: dict(crop.get("gdd_stages", {})) for crop_key, crop in CROPS.items()
}

FROST_WARNING_T = 2.0
FROST_CRITICAL_T = 0.0


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _require_columns(df: pd.DataFrame, columns: set[str]) -> None:
    missing = columns.difference(df.columns)
    if missing:
        raise ValueError(f"Missing weather columns: {', '.join(sorted(missing))}")


def _as_utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def calc_htc(
    df_daily: pd.DataFrame,
    window_days: int = 30,
    min_valid_days: int = 20,
) -> dict:
    """Calculate Selyaninov HTC from completed past warm days only.

    ``HTC = 10 * sum(P) / sum(Tmean)`` for days with ``Tmean > 10 °C``.
    Forecast precipitation is excluded and the value is suppressed when
    coverage is insufficient.
    """
    from src.agro.data_quality import past_rows, prepare_daily_frame, source_counts

    if window_days <= 0:
        raise ValueError("window_days must be positive")
    if min_valid_days <= 0 or min_valid_days > window_days:
        raise ValueError("min_valid_days must be within window_days")

    frame = prepare_daily_frame(df_daily, {"t_mean", "precip_sum"})
    past = past_rows(frame)
    if past.empty:
        return {
            "htc": None,
            "sum_precip_mm": None,
            "sum_t_above10": None,
            "window_days": window_days,
            "available_days": 0,
            "valid_days": 0,
            "expected_days": window_days,
            "missing_days": window_days,
            "missing_fraction": 1.0,
            "min_valid_days": min_valid_days,
            "interpretation": "нет завершённых прошлых данных",
            "data_sources": {},
            "method_reference": "Selyaninov hydrothermal coefficient",
            "units": "dimensionless",
        }

    end_day = past["date"].dt.normalize().max()
    start_day = end_day - pd.Timedelta(days=window_days - 1)
    window = past[
        (past["date"].dt.normalize() >= start_day)
        & (past["date"].dt.normalize() <= end_day)
    ].copy()
    valid = window.dropna(subset=["t_mean", "precip_sum"]).copy()
    valid_days = int(valid["date"].dt.normalize().nunique())
    missing_days = max(0, window_days - valid_days)
    missing_fraction = round(missing_days / window_days, 4)
    warm = valid[valid["t_mean"] > 10.0].copy()
    warm_days = int(warm["date"].dt.normalize().nunique())
    sum_precip = float(warm["precip_sum"].clip(lower=0).sum())
    sum_t = float(warm["t_mean"].sum())

    if warm_days < min_valid_days:
        value = None
        interpretation = (
            f"недостаточно валидных тёплых суток: {warm_days}; "
            f"требуется не менее {min_valid_days}"
        )
    elif sum_t <= 0:
        value = None
        interpretation = "период с Tср > 10°C не выделен"
    else:
        value = round(10.0 * sum_precip / sum_t, 3)
        if value < 0.5:
            interpretation = "засушливые условия"
        elif value < 1.0:
            interpretation = "недостаточное увлажнение"
        elif value < 1.5:
            interpretation = "умеренное увлажнение"
        else:
            interpretation = "повышенное увлажнение"

    return {
        "htc": value,
        "sum_precip_mm": round(sum_precip, 1),
        "sum_t_above10": round(sum_t, 1),
        "window_days": window_days,
        "available_days": warm_days,
        "valid_days": valid_days,
        "expected_days": window_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "min_valid_days": min_valid_days,
        "interpretation": interpretation,
        "data_sources": source_counts(window),
        "method_reference": "Selyaninov hydrothermal coefficient",
        "units": "dimensionless",
    }


def calc_gdd(
    df_daily: pd.DataFrame,
    crop: str = "wheat",
    season_start: pd.Timestamp | None = None,
    *,
    phase: str | None = None,
    t_upper: float | None = None,
) -> dict:
    """Calculate GDD and keep past sources separate from forecast."""
    from src.agro.crop_catalog import get_crop
    from src.agro.data_quality import past_rows, prepare_daily_frame

    crop_data = get_crop(crop)
    t_base = float(crop_data.get("t_base", 5.0))
    frame = prepare_daily_frame(df_daily, {"t_max", "t_min"})

    normalized_start: pd.Timestamp | None = None
    if season_start is not None:
        normalized_start = pd.Timestamp(season_start)
        if normalized_start.tzinfo is None:
            normalized_start = normalized_start.tz_localize("UTC")
        else:
            normalized_start = normalized_start.tz_convert("UTC")
        normalized_start = normalized_start.normalize()
        frame = frame[frame["date"].dt.normalize() >= normalized_start].copy()

    valid = frame.dropna(subset=["t_max", "t_min"]).copy()
    if t_upper is not None:
        if t_upper <= t_base:
            raise ValueError("t_upper must be greater than Tbase")
        valid["t_max_used"] = valid["t_max"].clip(upper=t_upper)
        valid["t_min_used"] = valid["t_min"].clip(upper=t_upper)
    else:
        valid["t_max_used"] = valid["t_max"]
        valid["t_min_used"] = valid["t_min"]
    valid["gdd_day"] = (
        (valid["t_max_used"] + valid["t_min_used"]) / 2.0 - t_base
    ).clip(lower=0)

    past = past_rows(frame)
    past_kinds = {"observation", "reanalysis", "operational_past"}
    valid_past = valid[valid["data_kind"].isin(past_kinds)].copy()
    valid_forecast = valid[valid["data_kind"] == "forecast"].copy()
    gdd_by_source = {
        str(kind): round(float(group["gdd_day"].sum()), 1)
        for kind, group in valid_past.groupby("data_kind")
    }
    past_gdd = round(float(valid_past["gdd_day"].sum()), 1)
    forecast_gdd = round(float(valid_forecast["gdd_day"].sum()), 1)

    period_is_season = False
    if normalized_start is not None and not past.empty:
        period_is_season = bool(past["date"].dt.normalize().min() <= normalized_start)

    if not past.empty:
        actual_start = past["date"].dt.normalize().min()
        actual_end = past["date"].dt.normalize().max()
        expected_start = normalized_start if period_is_season else actual_start
        expected_days = int((actual_end - expected_start).days) + 1
        valid_days = int(valid_past["date"].dt.normalize().nunique())
    else:
        actual_start = None
        actual_end = None
        expected_days = 0
        valid_days = 0
    missing_days = max(0, expected_days - valid_days)
    missing_fraction = round(missing_days / expected_days, 4) if expected_days else 0.0

    if phase:
        phenology_note = (
            f"Фактическая фаза «{phase}» указана пользователем и не рассчитана по ГДД."
        )
    else:
        phenology_note = (
            "Автоматическая фенофаза не выводится: пороги требуют "
            "независимой региональной валидации."
        )

    return {
        "crop": crop,
        "t_base": t_base,
        "t_upper": t_upper,
        "gdd_past": past_gdd,
        "gdd_forecast_7d": forecast_gdd,
        "gdd_by_source": gdd_by_source,
        "gdd_reanalysis": gdd_by_source.get("reanalysis", 0.0),
        "gdd_operational_past": gdd_by_source.get("operational_past", 0.0),
        "current_phase": phase,
        "next_phase": None,
        "period_is_season": period_is_season,
        "period_start": actual_start.isoformat() if actual_start is not None else None,
        "period_end": actual_end.isoformat() if actual_end is not None else None,
        "valid_days": valid_days,
        "expected_days": expected_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "phenology_note": phenology_note,
        "phenology_thresholds": crop_data.get("gdd_stages", {}),
        "method_reference": (
            "McMaster & Wilhelm (1997), Agricultural and Forest "
            "Meteorology 87:291-300, simple mean-temperature method"
        ),
        "units": "°C·day",
        "source_partition": (
            "past observation/reanalysis/operational rows accumulated; "
            "forecast reported separately"
        ),
    }


def calc_frost_risk(
    df_daily: pd.DataFrame,
    utc_offset_seconds: int = 0,
    *,
    crop: str | None = None,
    phase: str | None = None,
    elevation_m: float | None = None,
) -> dict:
    """Screen forecast Tmin at 2 m without damage-probability claims."""
    from src.agro.data_quality import forecast_rows, prepare_daily_frame

    frame = prepare_daily_frame(df_daily, {"t_min"})
    future = forecast_rows(frame).dropna(subset=["t_min"]).copy()
    alerts: list[dict] = []
    offset = timedelta(seconds=utc_offset_seconds)
    now = _now_utc()
    for _, row in future.iterrows():
        t_min = float(row["t_min"])
        if t_min > FROST_WARNING_T:
            continue
        local_date = row["date"] + offset
        alerts.append(
            {
                "date": row["date"].strftime("%d.%m %H:%M UTC"),
                "date_local": local_date.strftime("%d.%m %H:%M"),
                "event_date": local_date.strftime("%Y-%m-%d"),
                "t_min": round(t_min, 1),
                "min_temp": round(t_min, 1),
                "lead_hours": max(
                    0,
                    int((row["date"] - now).total_seconds() // 3600),
                ),
                "level": "critical" if t_min <= FROST_CRITICAL_T else "warning",
                "data_kind": "forecast",
                "action": (
                    "уточнить локальный прогноз, фактическую фазу и "
                    "условия понижений рельефа"
                ),
            }
        )

    context = []
    if crop:
        context.append(f"crop={crop}")
    if phase:
        context.append(f"phase={phase}")
    if elevation_m is not None:
        context.append(f"model_elevation={elevation_m:.0f} m")
    return {
        "alerts": alerts,
        "frost_free_days_7d": max(0, int(len(future) - len(alerts))),
        "forecast_contains_48h": bool(len(future) >= 2),
        "forecast_days": int(len(future)),
        "method_note": (
            "общий скрининг по прогнозной Tmin воздуха 2 м; это не "
            "температура растений и не crop-specific damage threshold"
        ),
        "context_note": ", ".join(context) if context else None,
        "method_reference": "provider daily minimum air temperature at 2 m",
        "units": "°C",
    }


def calc_et0_balance(
    df_daily: pd.DataFrame,
    window_days: int = 7,
    min_valid_days: int | None = None,
) -> dict:
    """Calculate P - provider ET0 when paired past data are sufficient."""
    import math

    from src.agro.data_quality import past_rows, prepare_daily_frame, source_counts

    if window_days <= 0:
        raise ValueError("window_days must be positive")
    required_days = (
        max(1, math.ceil(window_days * 0.7))
        if min_valid_days is None
        else min_valid_days
    )
    if required_days <= 0 or required_days > window_days:
        raise ValueError("min_valid_days must be within window_days")

    frame = prepare_daily_frame(df_daily, {"precip_sum", "et0_sum"})
    past = past_rows(frame)
    if past.empty:
        valid_days = 0
        missing_days = window_days
        window = past
    else:
        end_day = past["date"].dt.normalize().max()
        start_day = end_day - pd.Timedelta(days=window_days - 1)
        window = past[
            (past["date"].dt.normalize() >= start_day)
            & (past["date"].dt.normalize() <= end_day)
        ].copy()
        valid_days = int(
            window.dropna(subset=["precip_sum", "et0_sum"])["date"]
            .dt.normalize()
            .nunique()
        )
        missing_days = max(0, window_days - valid_days)
    missing_fraction = round(missing_days / window_days, 4)
    common = {
        "window_days": window_days,
        "valid_days": valid_days,
        "expected_days": window_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "min_valid_days": required_days,
        "et0_source": "Open-Meteo et0_fao_evapotranspiration",
        "data_sources": source_counts(window),
        "method_reference": "P - ET0 diagnostic balance; ET0 is provider data",
        "units": "mm",
    }
    if valid_days < required_days:
        return {
            "available": False,
            "precip_sum_mm": None,
            "et0_sum_mm": None,
            "balance_mm": None,
            "status": (
                f"недостаточно парных данных: {valid_days} сут.; "
                f"требуется не менее {required_days}"
            ),
            **common,
        }

    valid = window.dropna(subset=["precip_sum", "et0_sum"]).copy()
    precip = float(valid["precip_sum"].clip(lower=0).sum())
    et0 = float(valid["et0_sum"].clip(lower=0).sum())
    balance = round(precip - et0, 1)
    if balance >= 0:
        status = "профицит по диагностическому балансу"
    elif balance >= -30:
        status = "умеренный дефицит по диагностическому балансу"
    else:
        status = "выраженный дефицит; требуется проверка влажности почвы"
    return {
        "available": True,
        "precip_sum_mm": round(precip, 1),
        "et0_sum_mm": round(et0, 1),
        "balance_mm": balance,
        "status": status,
        **common,
    }


def compute_all_indices(
    df_daily: pd.DataFrame,
    crop: str = "wheat",
    *,
    utc_offset_seconds: int = 0,
    season_start: pd.Timestamp | None = None,
    phase: str | None = None,
    elevation_m: float | None = None,
) -> dict:
    return {
        "htc": calc_htc(df_daily),
        "gdd": calc_gdd(
            df_daily,
            crop,
            season_start=season_start,
            phase=phase,
        ),
        "frost": calc_frost_risk(
            df_daily,
            utc_offset_seconds=utc_offset_seconds,
            crop=crop,
            phase=phase,
            elevation_m=elevation_m,
        ),
        "et0_bal": calc_et0_balance(df_daily),
    }


def format_indices_for_rag(
    indices: dict,
    crop: str,
    crop_phase: str | None = None,
) -> str:
    lines = ["=== ОПЕРАТИВНОЕ СОСТОЯНИЕ ПОЛЯ ===", f"Культура: {crop}"]
    phase = crop_phase or indices.get("gdd", {}).get("current_phase")
    lines.append(
        f"Фактическая фаза: {phase} (наблюдение пользователя)"
        if phase
        else "Фактическая фаза: не указана"
    )

    htc = indices.get("htc", {})
    if htc.get("htc") is not None:
        lines.append(f"ГТК: {htc['htc']:.2f} — {htc.get('interpretation', '')}")
    else:
        lines.append(f"ГТК: не рассчитан — {htc.get('interpretation', 'нет данных')}")

    gdd = indices.get("gdd", {})
    label = "с начала сезона" if gdd.get("period_is_season") else "за доступный период"
    lines.append(f"ГДД {label}: {gdd.get('gdd_past', 0):.1f} °C·сут")
    lines.append(f"Прогнозный прирост ГДД: {gdd.get('gdd_forecast_7d', 0):.1f} °C·сут")

    alerts = indices.get("frost", {}).get("alerts", [])
    if alerts:
        event = alerts[0]
        lines.append(
            f"Общий температурный риск: Tmin воздуха 2 м "
            f"{event['t_min']}°C, {event['date_local']}"
        )

    water = indices.get("et0_bal", {})
    if water.get("available") and water.get("balance_mm") is not None:
        lines.append(f"Баланс осадки − ET0: {water['balance_mm']:.1f} мм")
    else:
        lines.append(
            f"Баланс осадки − ET0: не рассчитан — {water.get('status', 'нет данных')}"
        )
    lines.append(
        "Источники разделены: реанализ, оперативное прошлое модели и прогноз; "
        "это не климатическая норма и не прогноз урожайности"
    )
    lines.append("=== КОНЕЦ ДАННЫХ ===")
    return "\n".join(lines)
