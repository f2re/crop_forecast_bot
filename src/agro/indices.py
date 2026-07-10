"""Scientifically bounded agrometeorological indicators.

Sources:
- Selyaninov hydrothermal coefficient: Selyaninov (1937).
- Growing degree days: McMaster & Wilhelm (1997), Agric. For. Meteorol.
- Reference evapotranspiration source: Open-Meteo ET0 variable based on FAO-56.

The module does not infer yield.  Phenology is not inferred unless a season start
is supplied and the dataset actually covers that period.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import pandas as pd

logger = logging.getLogger(__name__)

GDD_BASE: dict[str, float] = {
    "wheat": 5.0,
    "barley": 5.0,
    "corn": 10.0,
    "sunflower": 10.0,
    "soy": 10.0,
    "rapeseed": 5.0,
    "potato": 7.0,
    "sugar_beet": 5.0,
}

GDD_PHENOLOGY: dict[str, dict[str, int]] = {
    "wheat": {"посев": 0, "кущение": 150, "колошение": 600, "молочная спелость": 900, "уборка": 1200},
    "corn": {"посев": 0, "всходы": 100, "6-й лист": 400, "цветение": 800, "уборка": 1800},
    "sunflower": {"посев": 0, "всходы": 80, "бутонизация": 400, "цветение": 700, "уборка": 1400},
    "barley": {"посев": 0, "кущение": 120, "колошение": 550, "уборка": 1100},
    "soy": {"посев": 0, "всходы": 80, "цветение": 600, "уборка": 1400},
    "rapeseed": {"посев": 0, "розетка": 100, "цветение": 400, "уборка": 900},
    "potato": {"посев": 0, "всходы": 120, "бутонизация": 400, "уборка": 900},
    "sugar_beet": {"посев": 0, "всходы": 100, "смыкание": 500, "уборка": 1300},
}

FROST_WARNING_T = 2.0
FROST_CRITICAL_T = 0.0


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _require_columns(df: pd.DataFrame, columns: set[str]) -> None:
    missing = columns.difference(df.columns)
    if missing:
        raise ValueError(f"Missing weather columns: {', '.join(sorted(missing))}")


def calc_htc(
    df_daily: pd.DataFrame,
    window_days: int = 30,
    min_valid_days: int = 20,
) -> dict:
    """Calculate HTC only when a sufficiently long warm-period window exists."""
    _require_columns(df_daily, {"date", "t_mean", "precip_sum"})
    now = _now_utc()
    df = df_daily[
        (df_daily["date"] <= now)
        & (df_daily["date"] >= now - pd.Timedelta(days=window_days))
    ][["date", "t_mean", "precip_sum"]].dropna()
    warm = df[df["t_mean"] > 10.0]
    available_days = int(len(warm))
    sum_precip = float(warm["precip_sum"].clip(lower=0).sum())
    sum_t = float(warm["t_mean"].sum())

    if available_days < min_valid_days:
        value = None
        interpretation = (
            f"недостаточно данных тёплого периода: {available_days} сут., "
            f"требуется не менее {min_valid_days}"
        )
    elif sum_t <= 0:
        value = None
        interpretation = "вегетационный период с Tср > 10°C не выделен"
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
        "available_days": available_days,
        "min_valid_days": min_valid_days,
        "interpretation": interpretation,
    }


def calc_gdd(
    df_daily: pd.DataFrame,
    crop: str = "wheat",
    season_start: pd.Timestamp | None = None,
) -> dict:
    """Calculate GDD for the explicitly available period or a supplied season."""
    _require_columns(df_daily, {"date", "t_max", "t_min"})
    t_base = GDD_BASE.get(crop, 5.0)
    now = _now_utc()
    df = df_daily[["date", "t_max", "t_min"]].dropna().copy()

    if season_start is not None:
        season_start = pd.Timestamp(season_start)
        if season_start.tzinfo is None:
            season_start = season_start.tz_localize("UTC")
        else:
            season_start = season_start.tz_convert("UTC")
        df = df[df["date"] >= season_start]

    df["gdd_day"] = ((df["t_max"] + df["t_min"]) / 2.0 - t_base).clip(lower=0)
    past_gdd = round(float(df.loc[df["date"] <= now, "gdd_day"].sum()), 1)
    forecast_gdd = round(float(df.loc[df["date"] > now, "gdd_day"].sum()), 1)

    phase: str | None = None
    next_phase: dict | None = None
    period_is_season = season_start is not None and (
        df.empty or df["date"].min() <= season_start + pd.Timedelta(days=1)
    )
    if period_is_season:
        phases = list(GDD_PHENOLOGY.get(crop, {}).items())
        for index, (name, threshold) in enumerate(phases):
            if past_gdd >= threshold:
                phase = name
                if index + 1 < len(phases):
                    next_name, next_threshold = phases[index + 1]
                    next_phase = {
                        "name": next_name,
                        "gdd_needed": max(0.0, round(next_threshold - past_gdd, 1)),
                    }

    return {
        "crop": crop,
        "t_base": t_base,
        "gdd_past": past_gdd,
        "gdd_forecast_7d": forecast_gdd,
        "current_phase": phase,
        "next_phase": next_phase,
        "period_is_season": period_is_season,
        "period_start": None if df.empty else df["date"].min().isoformat(),
        "phenology_thresholds": GDD_PHENOLOGY.get(crop, {}),
    }


def calc_frost_risk(
    df_daily: pd.DataFrame,
    utc_offset_seconds: int = 0,
) -> dict:
    """Screen model air-temperature minima for potential frost conditions."""
    _require_columns(df_daily, {"date", "t_min"})
    now = _now_utc()
    future = df_daily[df_daily["date"] > now][["date", "t_min"]].dropna().copy()
    alerts: list[dict] = []
    offset = timedelta(seconds=utc_offset_seconds)

    for _, row in future.iterrows():
        t_min = float(row["t_min"])
        if t_min > FROST_WARNING_T:
            continue
        lead_hours = max(0, int((row["date"] - now).total_seconds() // 3600))
        local_date = row["date"] + offset
        level = "critical" if t_min <= FROST_CRITICAL_T else "warning"
        alerts.append(
            {
                "date": row["date"].strftime("%d.%m %H:%M UTC"),
                "date_local": local_date.strftime("%d.%m %H:%M"),
                "event_date": local_date.strftime("%Y-%m-%d"),
                "t_min": round(t_min, 1),
                "min_temp": round(t_min, 1),
                "lead_hours": lead_hours,
                "level": level,
                "action": "уточнить локальный прогноз и оценить защитные меры по фазе культуры",
            }
        )

    return {
        "alerts": alerts,
        "frost_free_days_7d": max(0, int(len(future) - len(alerts))),
        "forecast_contains_48h": bool(len(future) >= 2),
        "method_note": "скрининг по прогнозной Tmin воздуха на высоте 2 м",
    }


def calc_et0_balance(df_daily: pd.DataFrame, window_days: int = 7) -> dict:
    """Calculate precipitation minus provider ET0 for the completed past window."""
    _require_columns(df_daily, {"date", "precip_sum", "et0_sum"})
    now = _now_utc()
    df = df_daily[
        (df_daily["date"] <= now)
        & (df_daily["date"] >= now - pd.Timedelta(days=window_days))
    ][["precip_sum", "et0_sum"]].dropna()
    precip = float(df["precip_sum"].clip(lower=0).sum())
    et0 = float(df["et0_sum"].clip(lower=0).sum())
    balance = round(precip - et0, 1)
    if balance >= 0:
        status = "профицит по расчётному балансу"
    elif balance >= -30:
        status = "умеренный дефицит по расчётному балансу"
    else:
        status = "выраженный дефицит; требуется проверка влажности почвы"
    return {
        "precip_sum_mm": round(precip, 1),
        "et0_sum_mm": round(et0, 1),
        "balance_mm": balance,
        "status": status,
        "window_days": window_days,
        "et0_source": "Open-Meteo et0_fao_evapotranspiration",
    }


def compute_all_indices(
    df_daily: pd.DataFrame,
    crop: str = "wheat",
    *,
    utc_offset_seconds: int = 0,
    season_start: pd.Timestamp | None = None,
) -> dict:
    return {
        "htc": calc_htc(df_daily),
        "gdd": calc_gdd(df_daily, crop, season_start=season_start),
        "frost": calc_frost_risk(df_daily, utc_offset_seconds=utc_offset_seconds),
        "et0_bal": calc_et0_balance(df_daily),
    }


def format_indices_for_rag(indices: dict, crop: str, crop_phase: str | None = None) -> str:
    lines = ["=== ОПЕРАТИВНОЕ СОСТОЯНИЕ ПОЛЯ ===", f"Культура: {crop}"]
    phase = crop_phase or indices.get("gdd", {}).get("current_phase")
    if phase:
        lines.append(f"Фенологическая фаза: {phase}")
    else:
        lines.append("Фенологическая фаза: не определена без даты начала сезона")

    htc_data = indices.get("htc", {})
    if htc_data.get("htc") is not None:
        lines.append(
            f"ГТК: {htc_data['htc']:.2f} — {htc_data.get('interpretation', '')}"
        )
    else:
        lines.append(f"ГТК: не рассчитан — {htc_data.get('interpretation', 'нет данных')}")

    gdd_data = indices.get("gdd", {})
    if gdd_data.get("gdd_past") is not None:
        lines.append(f"ГДД за доступный период: {gdd_data['gdd_past']:.0f} °C·сут")

    alerts = indices.get("frost", {}).get("alerts", [])
    if alerts:
        next_frost = alerts[0]
        lines.append(
            f"Температурный риск: Tmin {next_frost['t_min']}°C, {next_frost['date_local']}"
        )

    balance = indices.get("et0_bal", {}).get("balance_mm")
    if balance is not None:
        lines.append(f"Баланс осадки − ET0: {balance:.1f} мм")
    lines.append("Источник: оперативные данные; не климатическая норма и не прогноз урожайности")
    lines.append("=== КОНЕЦ ДАННЫХ ===")
    return "\n".join(lines)
