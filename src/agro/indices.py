"""
Агрометеорологические индексы.

Источники:
  - ГТК: Селянинов Г.Т. (1937), шкала Д.И. Шашко
  - ГДД: McMaster & Wilhelm (1997), Agric. For. Meteorol.
  - ЕТ0: FAO Irrigation and Drainage Paper No. 56 (Allen et al. 1998)
  - Заморозки: ГОСТ Р 58596-2019, WMO-No.8 (2018)

Все функции принимают df_daily из src.api.open_meteo.fetch_agro_data().
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# ── Базовые температуры для ГДД (°C) ────────────────────────────────────────
GDD_BASE: dict[str, float] = {
    "wheat":      5.0,
    "barley":     5.0,
    "corn":      10.0,
    "sunflower": 10.0,
    "soy":       10.0,
    "rapeseed":   5.0,
    "potato":     7.0,
    "sugar_beet": 5.0,
}

# ── Пороги ГДД для ключевых фенофаз (накопление с начала сезона) ────────────
GDD_PHENOLOGY: dict[str, dict[str, int]] = {
    "wheat":     {"посев": 0, "кущение": 150, "колошение": 600, "молочная спелость": 900, "уборка": 1200},
    "corn":      {"посев": 0, "всходы": 100, "6-й лист": 400, "цветение": 800, "уборка": 1800},
    "sunflower": {"посев": 0, "всходы": 80,  "бутонизация": 400, "цветение": 700, "уборка": 1400},
    "barley":    {"посев": 0, "кущение": 120, "колошение": 550, "уборка": 1100},
    "soy":       {"посев": 0, "всходы": 80,  "цветение": 600, "уборка": 1400},
    "rapeseed":  {"посев": 0, "розетка": 100, "цветение": 400, "уборка": 900},
    "potato":    {"посев": 0, "всходы": 120, "бутонизация": 400, "уборка": 900},
    "sugar_beet":{"посев": 0, "всходы": 100, "смыкание": 500, "уборка": 1300},
}

# ── Заморозковые пороги ──────────────────────────────────────────────────────
FROST_WARNING_T  = 2.0   # °C — подготовиться
FROST_CRITICAL_T = 0.0   # °C — действовать немедленно


def calc_htc(df_daily: pd.DataFrame, window_days: int = 30) -> dict:
    """
    Гидротермический коэффициент Селянинова (ГТК) за последние window_days суток.

    K = 10 * ΣR / ΣT,  где T — суточные среднесуточные T > 10 °C.

    Шкала Д.И. Шашко:
      < 0.5  — засуха
      0.5–1.0 — полузасушливо
      1.0–1.5 — умеренное увлажнение
      > 1.5  — достаточное увлажнение
    """
    now = pd.Timestamp.now(tz="UTC")
    mask = (
        (df_daily["date"] <= now)
        & (df_daily["date"] >= now - pd.Timedelta(days=window_days))
    )
    df = df_daily[mask].copy()

    sum_precip     = float(df["precip_sum"].clip(lower=0).sum())
    sum_t_above10  = float(df.loc[df["t_mean"] > 10, "t_mean"].sum())

    if sum_t_above10 == 0:
        htc_value = None
        interpretation = "Температура ниже 10°C — вегетационный период не начался"
    else:
        htc_value = round(10 * sum_precip / sum_t_above10, 3)
        if htc_value < 0.5:
            interpretation = "🔴 Засуха (ГТК < 0.5)"
        elif htc_value < 1.0:
            interpretation = "🟡 Полузасушливо (ГТК 0.5–1.0)"
        elif htc_value < 1.5:
            interpretation = "🟢 Умеренное увлажнение (ГТК 1.0–1.5)"
        else:
            interpretation = "🔵 Достаточное увлажнение (ГТК > 1.5)"

    logger.info(f"ГТК ({window_days}д): {htc_value} → {interpretation}")
    return {
        "htc":             htc_value,
        "sum_precip_mm":   round(sum_precip, 1),
        "sum_t_above10":   round(sum_t_above10, 1),
        "window_days":     window_days,
        "interpretation":  interpretation,
    }


def calc_gdd(df_daily: pd.DataFrame, crop: str = "wheat") -> dict:
    """
    Накопленные градусо-дни роста (ГДД) по методу McMaster & Wilhelm (1997).

    GDD_day = max(0, (T_max + T_min) / 2 − T_base)

    Разбивка: факт (past_days) и прогноз (+7 сут).
    Оценка текущей фенофазы по накопленным ГДД.
    """
    t_base = GDD_BASE.get(crop, 5.0)
    df = df_daily.copy()
    df["gdd_day"] = ((df["t_max"] + df["t_min"]) / 2 - t_base).clip(lower=0)

    now        = pd.Timestamp.now(tz="UTC")
    past_mask  = df["date"] <= now
    past_gdd   = round(float(df.loc[past_mask,  "gdd_day"].sum()), 1)
    fore_gdd   = round(float(df.loc[~past_mask, "gdd_day"].sum()), 1)

    phenology = GDD_PHENOLOGY.get(crop, {})
    phase = "начало сезона"
    next_phase = None
    if phenology:
        phases = list(phenology.items())
        for i, (phase_name, threshold) in enumerate(phases):
            if past_gdd >= threshold:
                phase = phase_name
                if i + 1 < len(phases):
                    nxt_name, nxt_thresh = phases[i + 1]
                    next_phase = {
                        "name": nxt_name,
                        "gdd_needed": round(nxt_thresh - past_gdd, 1),
                    }

    logger.info(
        f"ГДД ({crop}, Tbase={t_base}°C): "
        f"факт={past_gdd}, прогноз+7д={fore_gdd}, фаза={phase}"
    )
    return {
        "crop":                    crop,
        "t_base":                  t_base,
        "gdd_past":                past_gdd,
        "gdd_forecast_7d":         fore_gdd,
        "current_phase":           phase,
        "next_phase":              next_phase,
        "phenology_thresholds":    phenology,
    }


def calc_frost_risk(df_daily: pd.DataFrame) -> dict:
    """
    Риск заморозков на горизонте 7 суток прогноза.

    Уровни:
      🔴 КРИТИЧЕСКИЙ  — T_min ≤ 0°C  — действовать 0–24ч
      🟡 ПРЕДУПРЕЖДЕНИЕ — T_min ≤ 2°C — подготовиться 1–7 сут

    KPI: lead_hours ≥ 48 для соответствия стандарту проекта.
    """
    now    = pd.Timestamp.now(tz="UTC")
    future = df_daily[df_daily["date"] > now].copy()

    alerts = []
    for _, row in future.iterrows():
        t_min      = float(row["t_min"])
        lead_hours = int((row["date"] - now).total_seconds() / 3600)

        if t_min <= FROST_CRITICAL_T:
            level  = "🔴 КРИТИЧЕСКИЙ"
            action = "Защитить посевы — дымовые шашки, укрытие, полив дождеванием"
        elif t_min <= FROST_WARNING_T:
            level  = "🟡 ПРЕДУПРЕЖДЕНИЕ"
            action = "Подготовить укрывной материал и дымовые шашки"
        else:
            continue

        alerts.append({
            "date":       row["date"].strftime("%d.%m %H:00 UTC"),
            "t_min":      round(t_min, 1),
            "lead_hours": lead_hours,
            "level":      level,
            "action":     action,
        })

    meets_kpi = all(a["lead_hours"] >= 48 for a in alerts)
    logger.info(f"Заморозки: алертов={len(alerts)}, KPI_48h={meets_kpi}")
    return {
        "alerts":             alerts,
        "frost_free_days_7d": int(len(future) - len({a["date"] for a in alerts})),
        "kpi_lead_time_ok":   meets_kpi,
    }


def calc_et0_balance(df_daily: pd.DataFrame, window_days: int = 7) -> dict:
    """
    Декадный баланс влаги: ΣP − ΣET0 (FAO-56) за последние window_days суток.

    > 0  — профицит, полив не нужен
    < 0  — дефицит, возможен водный стресс
    < -30 — критический дефицит, полив необходим
    """
    now  = pd.Timestamp.now(tz="UTC")
    mask = (
        (df_daily["date"] <= now)
        & (df_daily["date"] >= now - pd.Timedelta(days=window_days))
    )
    df = df_daily[mask].copy()

    precip  = float(df["precip_sum"].clip(lower=0).sum())
    et0     = float(df["et0_sum"].clip(lower=0).sum())
    balance = round(precip - et0, 1)

    if balance >= 0:
        status = f"🟢 Профицит +{balance} мм — полив не требуется"
    elif balance >= -30:
        status = f"🟡 Дефицит {balance} мм — возможен водный стресс"
    else:
        status = f"🔴 Дефицит {balance} мм — полив необходим"

    logger.info(f"ЕТ0-баланс ({window_days}д): P={precip:.1f}, ET0={et0:.1f}, Δ={balance}")
    return {
        "precip_sum_mm": round(precip, 1),
        "et0_sum_mm":    round(et0, 1),
        "balance_mm":    balance,
        "status":        status,
        "window_days":   window_days,
    }


def compute_all_indices(df_daily: pd.DataFrame, crop: str = "wheat") -> dict:
    """
    Единая точка входа — вычисляет все четыре индекса за один вызов.

    Returns:
        {
          'htc':     dict от calc_htc(),
          'gdd':     dict от calc_gdd(),
          'frost':   dict от calc_frost_risk(),
          'et0_bal': dict от calc_et0_balance(),
        }
    """
    return {
        "htc":     calc_htc(df_daily),
        "gdd":     calc_gdd(df_daily, crop),
        "frost":   calc_frost_risk(df_daily),
        "et0_bal": calc_et0_balance(df_daily),
    }
