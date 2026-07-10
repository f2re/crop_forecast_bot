"""Scientifically bounded agrometeorological indicators.

Only deterministic calculations supported by the available weather series live here.
The module does not estimate yield, crop suitability, profitability, pesticide or
fertiliser doses.

Method references
-----------------
* Growing degree days: McMaster, G.S. & Wilhelm, W.W. (1997), Agricultural
  and Forest Meteorology 87, 291-300. DOI: 10.1016/S0168-1923(97)00027-0.
* Selyaninov hydrothermal coefficient: Selyaninov, G.T. (1937),
  Methodology of agricultural climatology.
* ET0 is not recomputed locally. The value is the provider's
  ``et0_fao_evapotranspiration`` based on FAO-56 Penman-Monteith.

Crop-stage thresholds are not used as an automatic phenology model. A phase shown
to the user is an explicit field observation entered by the user.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import pandas as pd

from src.agro.crop_catalog import CROPS, get_crop

GDD_BASE: dict[str, float] = {
    crop_key: float(crop["t_base"]) for crop_key, crop in CROPS.items()
}
GDD_PHENOLOGY: dict[str, dict[str, int]] = {crop_key: {} for crop_key in CROPS}

_NEAR_FREEZING_C = 2.0
_AIR_FROST_C = 0.0
_COMPLETED_KINDS = {"observation", "reanalysis", "operational_past"}
_FORECAST_KINDS = {"forecast"}


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _require_columns(frame: pd.DataFrame, columns: set[str]) -> None:
    missing = columns.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing weather columns: {', '.join(sorted(missing))}")


def _as_utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _prepare_daily(frame: pd.DataFrame, required: set[str]) -> pd.DataFrame:
    _require_columns(frame, required | {"date"})
    columns = list(
        dict.fromkeys(
            [
                "date",
                "local_date",
                *sorted(required - {"date"}),
                "data_kind",
                "data_source",
            ]
        )
    )
    columns = [column for column in columns if column in frame.columns]
    prepared = frame[columns].copy()
    prepared["date"] = pd.to_datetime(prepared["date"], utc=True, errors="coerce")
    prepared = prepared.dropna(subset=["date"])

    if "local_date" in prepared.columns:
        prepared["local_day"] = pd.to_datetime(
            prepared["local_date"], errors="coerce"
        ).dt.date
    else:
        prepared["local_day"] = prepared["date"].dt.date

    prepared = prepared.dropna(subset=["local_day"])
    priority = {
        "reanalysis": 1,
        "operational_past": 2,
        "forecast": 3,
        "observation": 4,
    }
    if "data_kind" in prepared.columns:
        prepared["_priority"] = prepared["data_kind"].map(priority).fillna(0)
    else:
        prepared["_priority"] = 0
    prepared = prepared.sort_values(["local_day", "_priority", "date"])
    prepared = prepared.drop_duplicates("local_day", keep="last")
    return prepared.drop(columns="_priority").reset_index(drop=True)


def _completed_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if "data_kind" in frame.columns:
        return frame[frame["data_kind"].isin(_COMPLETED_KINDS)].copy()
    yesterday = _now_utc().date() - timedelta(days=1)
    return frame[frame["local_day"] <= yesterday].copy()


def _forecast_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if "data_kind" in frame.columns:
        return frame[frame["data_kind"].isin(_FORECAST_KINDS)].copy()
    today = _now_utc().date()
    return frame[frame["local_day"] >= today].copy()


def _source_counts(frame: pd.DataFrame) -> dict[str, int]:
    if "data_kind" not in frame.columns:
        return {}
    return {
        str(key): int(value)
        for key, value in frame["data_kind"].value_counts().to_dict().items()
    }


def calc_htc(
    df_daily: pd.DataFrame,
    window_days: int = 30,
    min_warm_days: int = 20,
    max_missing_fraction: float = 0.10,
) -> dict[str, Any]:
    """Calculate a bounded operational Selyaninov HTC.

    HTC = 10 * sum(P) / sum(Tmean), where only days with Tmean > 10 °C are
    included. The function uses completed days only and refuses to publish a
    value when calendar coverage is insufficient.

    The numeric value is returned without a universal agroclimatic category:
    interpretation thresholds are region-, crop- and period-dependent.
    """

    if window_days < 1:
        raise ValueError("window_days must be positive")
    if not 0 <= max_missing_fraction < 1:
        raise ValueError("max_missing_fraction must be in [0, 1)")

    prepared = _prepare_daily(
        df_daily,
        {"date", "t_mean", "precip_sum"},
    )
    completed = _completed_rows(prepared).sort_values("local_day")
    if completed.empty:
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
            "period_start": None,
            "period_end": None,
            "interpretation": "нет завершённых суток для расчёта",
            "source_counts": {},
            "method_reference": "Selyaninov (1937)",
        }

    end_day = max(completed["local_day"])
    start_day = end_day - timedelta(days=window_days - 1)
    window = completed[
        (completed["local_day"] >= start_day)
        & (completed["local_day"] <= end_day)
    ].copy()
    window = window.dropna(subset=["t_mean", "precip_sum"])
    window = window[window["precip_sum"] >= 0]

    valid_days = int(window["local_day"].nunique())
    missing_days = max(0, window_days - valid_days)
    missing_fraction = round(missing_days / window_days, 3)
    warm = window[window["t_mean"] > 10.0]
    warm_days = int(warm["local_day"].nunique())
    sum_precip = float(warm["precip_sum"].sum()) if warm_days else 0.0
    sum_temperature = float(warm["t_mean"].sum()) if warm_days else 0.0

    minimum_calendar_days = math.ceil(window_days * (1 - max_missing_fraction))
    value: float | None = None
    if valid_days < minimum_calendar_days:
        interpretation = (
            "недостаточное календарное покрытие: "
            f"{valid_days}/{window_days} завершённых суток"
        )
    elif warm_days < min_warm_days:
        interpretation = (
            "недостаточно тёплых суток с Tср > 10°C: "
            f"{warm_days}, требуется не менее {min_warm_days}"
        )
    elif sum_temperature <= 0:
        interpretation = "сумма температур тёплого периода некорректна"
    else:
        value = round(10.0 * sum_precip / sum_temperature, 3)
        interpretation = (
            "числовой ГТК; агроклиматическая категория требует "
            "региональной калибровки"
        )

    return {
        "htc": value,
        "sum_precip_mm": round(sum_precip, 1),
        "sum_t_above10": round(sum_temperature, 1),
        "window_days": window_days,
        "available_days": warm_days,
        "valid_days": valid_days,
        "expected_days": window_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "period_start": start_day.isoformat(),
        "period_end": end_day.isoformat(),
        "interpretation": interpretation,
        "source_counts": _source_counts(window),
        "method_reference": "Selyaninov (1937)",
    }


def calc_gdd(
    df_daily: pd.DataFrame,
    crop: str = "wheat",
    season_start: pd.Timestamp | date | None = None,
    *,
    t_base: float | None = None,
    t_base_source: str | None = None,
    max_missing_fraction: float = 0.10,
) -> dict[str, Any]:
    """Calculate GDD from completed days and a separate forecast contribution.

    Daily GDD uses the simple averaging method:
    ``max(0, (Tmax + Tmin) / 2 - Tbase)``.

    A seasonal total is declared only when the series reaches the requested
    season start and the completed period has no more than the configured share
    of missing days. No phenological stage is inferred.
    """

    if not 0 <= max_missing_fraction < 1:
        raise ValueError("max_missing_fraction must be in [0, 1)")
    crop_definition = get_crop(crop)
    resolved_t_base = (
        float(t_base) if t_base is not None else float(crop_definition["t_base"])
    )
    if not -10.0 <= resolved_t_base <= 30.0:
        raise ValueError("Tbase must be between -10 and 30 °C")

    prepared = _prepare_daily(df_daily, {"date", "t_max", "t_min"})
    completed = _completed_rows(prepared).copy()
    forecast = _forecast_rows(prepared).copy()

    normalized_start: date | None = None
    if season_start is not None:
        if isinstance(season_start, date) and not isinstance(
            season_start, pd.Timestamp
        ):
            normalized_start = season_start
        else:
            normalized_start = _as_utc(pd.Timestamp(season_start)).date()
        completed = completed[completed["local_day"] >= normalized_start]
        forecast = forecast[forecast["local_day"] >= normalized_start]

    completed = completed.dropna(subset=["t_max", "t_min"])
    forecast = forecast.dropna(subset=["t_max", "t_min"])

    for frame in (completed, forecast):
        frame["gdd_day"] = (
            (frame["t_max"] + frame["t_min"]) / 2.0 - resolved_t_base
        ).clip(lower=0)

    past_gdd = (
        round(float(completed["gdd_day"].sum()), 1)
        if not completed.empty
        else None
    )
    forecast_gdd = (
        round(float(forecast["gdd_day"].sum()), 1)
        if not forecast.empty
        else None
    )

    period_end = max(completed["local_day"]) if not completed.empty else None
    actual_start = min(completed["local_day"]) if not completed.empty else None
    expected_start = normalized_start or actual_start
    if expected_start is not None and period_end is not None:
        expected_days = max(0, (period_end - expected_start).days + 1)
    else:
        expected_days = 0
    valid_days = int(completed["local_day"].nunique())
    missing_days = max(0, expected_days - valid_days)
    missing_fraction = (
        round(missing_days / expected_days, 3) if expected_days else None
    )
    period_reaches_start = bool(
        normalized_start is not None
        and actual_start is not None
        and actual_start <= normalized_start
    )
    period_is_season = bool(
        period_reaches_start
        and missing_fraction is not None
        and missing_fraction <= max_missing_fraction
    )

    source = t_base_source
    if source is None:
        source = (
            "user setting"
            if t_base is not None
            else "operational crop-catalogue default; verify cultivar/local guidance"
        )

    if normalized_start is None:
        scope_note = "дата начала сезона не задана; сумма относится к доступному периоду"
    elif not period_reaches_start:
        scope_note = "ряд не достигает даты начала сезона"
    elif not period_is_season:
        scope_note = (
            "ряд достигает даты сезона, но доля пропусков превышает "
            f"{max_missing_fraction:.0%}"
        )
    else:
        scope_note = "ряд покрывает сезон в пределах допустимой доли пропусков"

    return {
        "crop": crop,
        "t_base": resolved_t_base,
        "t_base_source": source,
        "t_upper": None,
        "gdd_past": past_gdd,
        "gdd_forecast_7d": forecast_gdd,
        "current_phase": None,
        "next_phase": None,
        "period_is_season": period_is_season,
        "period_start": None if actual_start is None else actual_start.isoformat(),
        "period_end": None if period_end is None else period_end.isoformat(),
        "season_start": (
            None if normalized_start is None else normalized_start.isoformat()
        ),
        "valid_days": valid_days,
        "expected_days": expected_days,
        "missing_days": missing_days,
        "missing_fraction": missing_fraction,
        "source_counts": _source_counts(completed),
        "phenology_thresholds": {},
        "phenology_note": (
            "автоматическая фенофаза не определяется; используйте фактическое "
            "полевое наблюдение"
        ),
        "scope_note": scope_note,
        "method_reference": (
            "McMaster & Wilhelm (1997), DOI "
            "10.1016/S0168-1923(97)00027-0"
        ),
    }


def calc_frost_risk(
    df_daily: pd.DataFrame,
    utc_offset_seconds: int = 0,
    *,
    crop: str | None = None,
    phase: str | None = None,
    elevation_m: float | None = None,
) -> dict[str, Any]:
    """Screen forecast Tmin at 2 m for freezing and near-freezing conditions.

    The 0 °C threshold describes modelled air freezing, not plant-tissue
    temperature or a crop-specific damage threshold. The 0..2 °C band is only an
    operational buffer for local cold-air pooling and forecast error.
    """

    prepared = _prepare_daily(df_daily, {"date", "t_min"})
    future = _forecast_rows(prepared).dropna(subset=["t_min"]).copy()
    if future.empty:
        return {
            "alerts": [],
            "risk_status": "unavailable",
            "forecast_days": 0,
            "frost_free_days_7d": None,
            "forecast_contains_48h": False,
            "method_note": "нет валидного прогнозного ряда Tmin воздуха 2 м",
            "context": {
                "crop": crop,
                "phase": phase,
                "elevation_m": elevation_m,
            },
        }

    now = _now_utc()
    offset = timedelta(seconds=utc_offset_seconds)
    alerts: list[dict[str, Any]] = []
    for _, row in future.sort_values("date").iterrows():
        minimum = float(row["t_min"])
        if minimum > _NEAR_FREEZING_C:
            continue
        timestamp = pd.Timestamp(row["date"])
        local_timestamp = timestamp + offset
        event_type = (
            "air_frost_or_freezing"
            if minimum <= _AIR_FROST_C
            else "near_freezing"
        )
        alerts.append(
            {
                "date": timestamp.strftime("%d.%m %H:%M UTC"),
                "date_local": local_timestamp.strftime("%d.%m %H:%M"),
                "event_date": row["local_day"].isoformat(),
                "t_min": round(minimum, 1),
                "min_temp": round(minimum, 1),
                "lead_hours": max(
                    0,
                    int((timestamp - now).total_seconds() // 3600),
                ),
                "level": event_type,
                "event_type": event_type,
                "crop_key": crop,
                "phase": phase,
                "elevation_m": elevation_m,
                "action": (
                    "сверить локальный прогноз, рельеф и фактическую фазу; "
                    "при необходимости проверить температуру у растений"
                ),
            }
        )

    return {
        "alerts": alerts,
        "risk_status": "alerts" if alerts else "no_threshold_crossing",
        "forecast_days": int(future["local_day"].nunique()),
        "frost_free_days_7d": max(
            0,
            int(future["local_day"].nunique() - len(alerts)),
        ),
        "forecast_contains_48h": bool(future["local_day"].nunique() >= 2),
        "method_note": (
            "скрининг по прогнозной Tmin воздуха на высоте 2 м; 0°C — "
            "порог замерзания воздуха, 0…2°C — операционный буфер, а не "
            "порог повреждения культуры"
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
    min_valid_days: int = 5,
) -> dict[str, Any]:
    """Return completed-period precipitation minus provider reference ET0.

    This is an atmospheric reference balance. It is not root-zone water balance,
    crop evapotranspiration, soil-water deficit or an irrigation prescription.
    """

    prepared = _prepare_daily(
        df_daily,
        {"date", "precip_sum", "et0_sum"},
    )
    completed = _completed_rows(prepared).sort_values("local_day")
    if completed.empty:
        return {
            "precip_sum_mm": None,
            "et0_sum_mm": None,
            "balance_mm": None,
            "status": "нет завершённых суток",
            "window_days": window_days,
            "valid_days": 0,
            "period_start": None,
            "period_end": None,
            "et0_source": "Open-Meteo et0_fao_evapotranspiration",
            "method_note": (
                "P−ET0 не является балансом влаги корнеобитаемого слоя "
                "или нормой полива"
            ),
        }

    end_day = max(completed["local_day"])
    start_day = end_day - timedelta(days=window_days - 1)
    window = completed[
        (completed["local_day"] >= start_day)
        & (completed["local_day"] <= end_day)
    ].dropna(subset=["precip_sum", "et0_sum"])
    window = window[
        (window["precip_sum"] >= 0)
        & (window["et0_sum"] >= 0)
    ]
    valid_days = int(window["local_day"].nunique())
    if valid_days < min_valid_days:
        precipitation = et0 = balance = None
        status = (
            f"недостаточно валидных суток: {valid_days}, "
            f"требуется не менее {min_valid_days}"
        )
    else:
        precipitation = round(float(window["precip_sum"].sum()), 1)
        et0 = round(float(window["et0_sum"].sum()), 1)
        balance = round(precipitation - et0, 1)
        status = "справочный баланс осадки − референсная ET0"

    return {
        "precip_sum_mm": precipitation,
        "et0_sum_mm": et0,
        "balance_mm": balance,
        "status": status,
        "window_days": window_days,
        "valid_days": valid_days,
        "period_start": start_day.isoformat(),
        "period_end": end_day.isoformat(),
        "et0_source": "Open-Meteo et0_fao_evapotranspiration",
        "method_note": (
            "P−ET0 не учитывает Kc, корнеобитаемый слой, сток, "
            "инфильтрацию и исходную влажность; это не норма полива"
        ),
        "method_reference": "FAO Irrigation and Drainage Paper 56",
    }


def compute_all_indices(
    df_daily: pd.DataFrame,
    crop: str = "wheat",
    *,
    utc_offset_seconds: int = 0,
    season_start: pd.Timestamp | date | None = None,
    phase: str | None = None,
    elevation_m: float | None = None,
    t_base: float | None = None,
    t_base_source: str | None = None,
) -> dict[str, Any]:
    return {
        "htc": calc_htc(df_daily),
        "gdd": calc_gdd(
            df_daily,
            crop,
            season_start=season_start,
            t_base=t_base,
            t_base_source=t_base_source,
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
    indices: dict[str, Any],
    crop: str,
    crop_phase: str | None = None,
) -> str:
    """Format deterministic field context without creating recommendations."""

    lines = ["=== ОПЕРАТИВНОЕ СОСТОЯНИЕ ПОЛЯ ===", f"Культура: {crop}"]
    if crop_phase:
        lines.append(f"Фаза (наблюдение пользователя): {crop_phase}")
    else:
        lines.append("Фаза: не задана пользователем")

    htc = indices.get("htc", {})
    if htc.get("htc") is None:
        lines.append(f"ГТК: не рассчитан — {htc.get('interpretation', 'нет данных')}")
    else:
        lines.append(
            f"ГТК {htc['period_start']}–{htc['period_end']}: "
            f"{htc['htc']:.2f}; без универсальной региональной категории"
        )

    gdd = indices.get("gdd", {})
    if gdd.get("gdd_past") is None:
        lines.append("ГДД: нет валидных завершённых суток")
    else:
        scope = "с начала сезона" if gdd.get("period_is_season") else "за доступный период"
        lines.append(
            f"ГДД {scope}: {gdd['gdd_past']:.1f} °C·сут, "
            f"Tbase={gdd['t_base']:.1f}°C"
        )

    frost = indices.get("frost", {})
    if frost.get("risk_status") == "unavailable":
        lines.append("Tmin-прогноз: недоступен")
    elif frost.get("alerts"):
        next_event = frost["alerts"][0]
        lines.append(
            f"Tmin воздуха 2 м: {next_event['t_min']:.1f}°C, "
            f"{next_event['date_local']} ({next_event['event_type']})"
        )
    else:
        lines.append("Tmin воздуха 2 м: пороги 0/2°C в доступном прогнозе не пересечены")

    water = indices.get("et0_bal", {})
    if water.get("balance_mm") is not None:
        lines.append(
            f"Осадки − референсная ET0: {water['balance_mm']:+.1f} мм "
            f"за {water['valid_days']} валидных суток"
        )
    else:
        lines.append(f"Осадки − ET0: не рассчитано — {water.get('status', 'нет данных')}")

    lines.append(
        "Данные являются модельными/реанализом; это не наблюдения, "
        "не прогноз урожайности и не агрономическая доза."
    )
    lines.append("=== КОНЕЦ ДАННЫХ ===")
    return "\n".join(lines)
