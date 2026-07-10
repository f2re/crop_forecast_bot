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
    """Calculate HTC only when a sufficiently long warm-period window exists."""
    _require_columns(df_daily, {"date", "t_mean", "precip_sum"})
    now = _now_utc()
    df = df_daily[
        (df_daily["date"] <= now)
        & (df_daily["date"] >= now - pd.Timedelta(days=window_days))
    ][["date", "t_mean", "precip_sum"]].dropna()
    warm = df[df["t_mean"] > 10.0]
    available_days = int(warm["date"].dt.normalize().nunique())
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
    """Calculate GDD for the available series or a fully covered season.

    GDD_day = max(0, (Tmax + Tmin) / 2 - Tbase), °C·day. Tbase is read from
    ``crop_catalog``. Automatic phenological stage inference is deliberately
    disabled: catalogue thresholds still require regional validation.
    """
    _require_columns(df_daily, {"date", "t_max", "t_min"})
    crop_definition = get_crop(crop)
    t_base = float(crop_definition["t_base"])
    now = _now_utc()
    df = df_daily[[column for column in df_daily.columns if column in {
        "date", "t_max", "t_min", "data_kind", "data_source"
    }]].dropna(subset=["date", "t_max", "t_min"]).copy()
    df["date"] = pd.to_datetime(df["date"], utc=True)

    normalized_start: pd.Timestamp | None = None
    if season_start is not None:
        normalized_start = _as_utc(pd.Timestamp(season_start))
        df = df[df["date"] >= normalized_start - pd.Timedelta(hours=36)]

    df["gdd_day"] = ((df["t_max"] + df["t_min"]) / 2.0 - t_base).clip(lower=0)
    past = df[df["date"] <= now]
    forecast = df[df["date"] > now]
    past_gdd = round(float(past["gdd_day"].sum()), 1)
    forecast_gdd = round(float(forecast["gdd_day"].sum()), 1)

    period_is_season = bool(
        normalized_start is not None
        and not past.empty
        and past["date"].min() <= normalized_start + pd.Timedelta(hours=36)
    )
    period_start = None if past.empty else past["date"].min()
    expected_start = normalized_start if period_is_season else period_start
    if expected_start is None:
        expected_days = 0
    else:
        expected_days = max(0, (now.normalize() - expected_start.normalize()).days + 1)
    valid_days = int(past["date"].dt.normalize().nunique())
    missing_days = max(0, expected_days - valid_days)
    missing_fraction = round(missing_days / expected_days, 3) if expected_days else None

    source_counts: dict[str, int] = {}
    if "data_kind" in past.columns:
        source_counts = {
            str(key): int(value)
            for key, value in past["data_kind"].value_counts().to_dict().items()
        }

    return {
        "crop": crop,
        "t_base": t_base,
        "t_upper": crop_definition.get("t_upper"),
        "gdd_past": past_gdd,
        "gdd_forecast_7d": forecast_gdd,
        "current_phase": None,
        "next_phase": None,
        "period_is_season": period_is_season,
        "period_start": None if period_start is None else period_start.isoformat(),
        "season_start": (
            None if normalized_start is None else normalized_start.date().isoformat()
        ),
        "valid_days": valid_days,
        "expected_days": expected_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "source_counts": source_counts,
        "phenology_thresholds": GDD_PHENOLOGY.get(crop, {}),
        "phenology_note": (
            "автоматическая фенофаза не определяется: пороги требуют "
            "валидации по культуре и региону"
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
    """Screen model air-temperature minima for potential frost conditions.

    The generic 2/0°C screening thresholds are not presented as crop damage
    thresholds. Crop, manually observed phase and model elevation are carried as
    context for the user, while the air/surface-temperature distinction remains
    explicit.
    """
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
                "crop_key": crop,
                "phase": phase,
                "elevation_m": elevation_m,
                "action": (
                    "сверить локальный прогноз, фактическую фазу и условия "
                    "микрорельефа"
                ),
            }
        )

    return {
        "alerts": alerts,
        "frost_free_days_7d": max(0, int(len(future) - len(alerts))),
        "forecast_contains_48h": bool(len(future) >= 2),
        "method_note": (
            "скрининг по прогнозной Tmin воздуха на высоте 2 м; это не "
            "температура поверхности растений и не порог повреждения культуры"
        ),
        "context": {
            "crop": crop,
            "phase": phase,
            "elevation_m": elevation_m,
        },
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
    phase: str | None = None,
    elevation_m: float | None = None,
) -> dict:
    return {
        "htc": calc_htc(df_daily),
        "gdd": calc_gdd(df_daily, crop, season_start=season_start),
        "frost": calc_frost_risk(
            df_daily,
            utc_offset_seconds=utc_offset_seconds,
            crop=crop,
            phase=phase,
            elevation_m=elevation_m,
        ),
        "et0_bal": calc_et0_balance(df_daily),
    }


def format_indices_for_rag(indices: dict, crop: str, crop_phase: str | None = None) -> str:
    lines = ["=== ОПЕРАТИВНОЕ СОСТОЯНИЕ ПОЛЯ ===", f"Культура: {crop}"]
    if crop_phase:
        lines.append(f"Фенологическая фаза (указана пользователем): {crop_phase}")
    else:
        lines.append("Фенологическая фаза: не задана пользователем")

    htc_data = indices.get("htc", {})
    if htc_data.get("htc") is not None:
        lines.append(
            f"ГТК: {htc_data['htc']:.2f} — {htc_data.get('interpretation', '')}"
        )
    else:
        lines.append(f"ГТК: не рассчитан — {htc_data.get('interpretation', 'нет данных')}")

    gdd_data = indices.get("gdd", {})
    if gdd_data.get("gdd_past") is not None:
        scope = "с начала сезона" if gdd_data.get("period_is_season") else "за доступный период"
        lines.append(f"ГДД {scope}: {gdd_data['gdd_past']:.0f} °C·сут")

    alerts = indices.get("frost", {}).get("alerts", [])
    if alerts:
        next_frost = alerts[0]
        lines.append(
            f"Температурный риск: Tmin {next_frost['t_min']}°C, {next_frost['date_local']}"
        )

    balance = indices.get("et0_bal", {}).get("balance_mm")
    if balance is not None:
        lines.append(f"Баланс осадки − ET0: {balance:.1f} мм")
    lines.append("Источник: реанализ и оперативный прогноз разделены в метаданных")
    lines.append("Это не климатическая норма и не прогноз урожайности")
    lines.append("=== КОНЕЦ ДАННЫХ ===")
    return "\n".join(lines)
