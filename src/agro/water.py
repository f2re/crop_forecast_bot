"""Completed-period precipitation and reference-ET0 indicators.

The calculations in this module are descriptive screening quantities. They use
completed local calendar days only and never convert reference
evapotranspiration into crop evapotranspiration, root-zone water storage or an
irrigation dose.

Scientific basis
----------------
* ETCCDI/Climdex defines a dry day as daily precipitation ``RR < 1 mm`` and CDD
  as the maximum consecutive run of such days. The same threshold is used here
  for a bounded period selected by the user, not as an annual climate index.
* FAO Irrigation and Drainage Paper 56 defines ET0 as the evaporative demand of
  a standardized, well-watered reference surface. Therefore ``P - ET0`` is
  reported only as a climatic screening difference.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

_COMPLETED_KINDS = frozenset({"observation", "reanalysis", "operational_past"})


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _as_utc(value: pd.Timestamp | str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _source_counts(frame: pd.DataFrame) -> dict[str, int]:
    if frame.empty or "data_kind" not in frame.columns:
        return {}
    return {
        str(key): int(value)
        for key, value in frame["data_kind"].value_counts().to_dict().items()
    }


def _longest_run(values: list[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _trailing_run(values: list[bool]) -> int:
    current = 0
    for value in reversed(values):
        if not value:
            break
        current += 1
    return current


def _prepare_completed_daily(
    df_daily: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
) -> pd.DataFrame:
    required = {"date", "precip_sum", "et0_sum"}
    missing = required.difference(df_daily.columns)
    if missing:
        raise ValueError(f"Missing weather columns: {', '.join(sorted(missing))}")

    optional = {"data_kind", "data_source", "local_date"}.intersection(
        df_daily.columns
    )
    frame = df_daily[list(required | optional)].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["date"])

    if "local_date" in frame.columns:
        local_day = pd.to_datetime(frame["local_date"], errors="coerce")
        frame["_day"] = local_day.dt.normalize()
        frame = frame.dropna(subset=["_day"])
    else:
        frame["_day"] = frame["date"].dt.tz_localize(None).dt.normalize()

    frame["precip_sum"] = pd.to_numeric(frame["precip_sum"], errors="coerce")
    frame["et0_sum"] = pd.to_numeric(frame["et0_sum"], errors="coerce")
    negative_precip = frame["precip_sum"] < 0
    negative_et0 = frame["et0_sum"] < 0
    frame["_negative_precip"] = negative_precip
    frame["_negative_et0"] = negative_et0
    frame.loc[negative_precip, "precip_sum"] = float("nan")
    frame.loc[negative_et0, "et0_sum"] = float("nan")

    # Partition before de-duplication. Otherwise an overlapping forecast row can
    # displace a valid completed row for the same local calendar day and make
    # the completed series appear to have a gap.
    if "data_kind" in frame.columns:
        frame = frame[frame["data_kind"].isin(_COMPLETED_KINDS)].copy()
    else:
        frame = frame[frame["date"] < as_of.normalize()].copy()
    return frame.sort_values(["_day", "date"]).drop_duplicates(
        "_day", keep="last"
    )


def _empty_result(
    *,
    season_start_day: pd.Timestamp | None,
    dry_day_threshold_mm: float,
    max_missing_fraction: float,
    negative_precip_days: int = 0,
    negative_et0_days: int = 0,
) -> dict[str, Any]:
    return {
        "available": False,
        "period_is_season": False,
        "coverage_start_reached": False,
        "season_start": (
            None
            if season_start_day is None
            else season_start_day.date().isoformat()
        ),
        "period_start": None,
        "period_end": None,
        "expected_days": 0,
        "row_days": 0,
        "calendar_missing_days": 0,
        "calendar_missing_fraction": None,
        "precip_available": False,
        "precip_sum_mm": None,
        "wet_day_precip_sum_mm": None,
        "precip_valid_days": 0,
        "precip_missing_days": 0,
        "precip_missing_fraction": None,
        "wet_days": None,
        "dry_days": None,
        "max_1day_precip_mm": None,
        "max_1day_precip_date": None,
        "max_5day_precip_mm": None,
        "max_5day_period_start": None,
        "max_5day_period_end": None,
        "dry_spell_available": False,
        "trailing_dry_spell_days": None,
        "max_dry_spell_days": None,
        "max_wet_spell_days": None,
        "dry_spell_status": "нет завершённых суток",
        "dry_day_threshold_mm": dry_day_threshold_mm,
        "et0_available": False,
        "et0_sum_mm": None,
        "et0_valid_days": 0,
        "et0_missing_days": 0,
        "et0_missing_fraction": None,
        "paired_available": False,
        "paired_days": 0,
        "paired_missing_days": 0,
        "paired_missing_fraction": None,
        "paired_precip_sum_mm": None,
        "paired_et0_sum_mm": None,
        "p_minus_et0_mm": None,
        "et0_minus_p_mm": None,
        "negative_precip_days": negative_precip_days,
        "negative_et0_days": negative_et0_days,
        "source_counts": {},
        "paired_source_counts": {},
        "status": "нет завершённых суток для расчёта",
        "scope_note": "нет завершённых суток для расчёта",
        "units": {"water_depth": "мм", "duration": "сут"},
        "et0_source": "provider et0_fao_evapotranspiration",
        "method_references": (
            "ETCCDI/Climdex: CDD, RR < 1 мм/сут",
            "Allen et al. (1998), FAO Irrigation and Drainage Paper 56",
        ),
        "limitations": (
            "P−ET0 не учитывает Kc, фактическую ET культуры, запасы влаги, "
            "сток, инфильтрацию, капиллярный подъём и глубину корней"
        ),
        "max_missing_fraction": max_missing_fraction,
    }


def calc_water_accumulation(
    df_daily: pd.DataFrame,
    *,
    season_start: pd.Timestamp | None = None,
    dry_day_threshold_mm: float = 1.0,
    max_missing_fraction: float = 0.10,
    as_of: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Calculate accumulated water indicators over completed local days.

    Precipitation and ET0 availability are checked independently. ``P - ET0``
    is computed only from paired valid days, so unequal missingness can never
    create a false balance. Consecutive-spell metrics are withheld when any
    calendar day or precipitation value is missing because a gap can hide the
    true run length.
    """
    if dry_day_threshold_mm <= 0:
        raise ValueError("dry_day_threshold_mm must be positive")
    if not 0 <= max_missing_fraction <= 1:
        raise ValueError("max_missing_fraction must be between 0 and 1")

    now = _as_utc(as_of if as_of is not None else _now_utc())
    season_start_day = (
        None
        if season_start is None
        else pd.Timestamp(pd.Timestamp(season_start).date())
    )
    frame = _prepare_completed_daily(df_daily, as_of=now)
    if season_start_day is not None:
        frame = frame[frame["_day"] >= season_start_day].copy()
    negative_precip_days = int(frame["_negative_precip"].sum())
    negative_et0_days = int(frame["_negative_et0"].sum())

    if frame.empty:
        return _empty_result(
            season_start_day=season_start_day,
            dry_day_threshold_mm=dry_day_threshold_mm,
            max_missing_fraction=max_missing_fraction,
            negative_precip_days=negative_precip_days,
            negative_et0_days=negative_et0_days,
        )

    period_start = pd.Timestamp(frame["_day"].min())
    period_end = pd.Timestamp(frame["_day"].max())
    expected_start = season_start_day if season_start_day is not None else period_start
    expected_days = max(0, int((period_end - expected_start).days) + 1)
    row_days = int(frame["_day"].nunique())
    calendar_missing_days = max(0, expected_days - row_days)
    calendar_missing_fraction = (
        round(calendar_missing_days / expected_days, 3)
        if expected_days > 0
        else None
    )
    coverage_start_reached = bool(
        season_start_day is not None and period_start <= season_start_day
    )
    period_is_season = bool(
        coverage_start_reached
        and calendar_missing_fraction is not None
        and calendar_missing_fraction <= max_missing_fraction
    )

    precip = frame.dropna(subset=["precip_sum"]).copy()
    et0 = frame.dropna(subset=["et0_sum"]).copy()
    paired = frame.dropna(subset=["precip_sum", "et0_sum"]).copy()

    precip_valid_days = int(precip["_day"].nunique())
    et0_valid_days = int(et0["_day"].nunique())
    paired_days = int(paired["_day"].nunique())
    precip_missing_days = max(0, expected_days - precip_valid_days)
    et0_missing_days = max(0, expected_days - et0_valid_days)
    paired_missing_days = max(0, expected_days - paired_days)
    precip_missing_fraction = (
        round(precip_missing_days / expected_days, 3)
        if expected_days > 0
        else None
    )
    et0_missing_fraction = (
        round(et0_missing_days / expected_days, 3) if expected_days > 0 else None
    )
    paired_missing_fraction = (
        round(paired_missing_days / expected_days, 3)
        if expected_days > 0
        else None
    )

    precip_available = bool(
        precip_valid_days > 0
        and precip_missing_fraction is not None
        and precip_missing_fraction <= max_missing_fraction
    )
    et0_available = bool(
        et0_valid_days > 0
        and et0_missing_fraction is not None
        and et0_missing_fraction <= max_missing_fraction
    )
    paired_available = bool(
        paired_days > 0
        and paired_missing_fraction is not None
        and paired_missing_fraction <= max_missing_fraction
    )

    precip_sum: float | None = None
    wet_day_precip_sum: float | None = None
    wet_days: int | None = None
    dry_days: int | None = None
    max_1day_precip: float | None = None
    max_1day_precip_date: str | None = None
    if precip_available:
        precip_values = precip["precip_sum"]
        precip_sum = round(float(precip_values.sum()), 1)
        wet_mask = precip_values >= dry_day_threshold_mm
        wet_day_precip_sum = round(float(precip_values[wet_mask].sum()), 1)
        wet_days = int(wet_mask.sum())
        dry_days = precip_valid_days - wet_days
        max_position = precip_values.idxmax()
        max_1day_precip = round(float(precip.loc[max_position, "precip_sum"]), 1)
        max_1day_precip_date = pd.Timestamp(
            precip.loc[max_position, "_day"]
        ).date().isoformat()

    et0_sum = round(float(et0["et0_sum"].sum()), 1) if et0_available else None

    paired_precip_sum: float | None = None
    paired_et0_sum: float | None = None
    p_minus_et0: float | None = None
    et0_minus_p: float | None = None
    if paired_available:
        raw_paired_precip = float(paired["precip_sum"].sum())
        raw_paired_et0 = float(paired["et0_sum"].sum())
        paired_precip_sum = round(raw_paired_precip, 1)
        paired_et0_sum = round(raw_paired_et0, 1)
        p_minus_et0 = round(raw_paired_precip - raw_paired_et0, 1)
        et0_minus_p = round(raw_paired_et0 - raw_paired_precip, 1)

    dry_spell_available = bool(
        expected_days > 0
        and precip_valid_days == expected_days
        and calendar_missing_days == 0
    )
    trailing_dry_spell_days: int | None = None
    max_dry_spell_days: int | None = None
    max_wet_spell_days: int | None = None
    max_5day_precip: float | None = None
    max_5day_period_start: str | None = None
    max_5day_period_end: str | None = None
    if dry_spell_available:
        continuous = precip.sort_values("_day").copy()
        dry_flags = (
            continuous["precip_sum"] < dry_day_threshold_mm
        ).tolist()
        wet_flags = [not flag for flag in dry_flags]
        trailing_dry_spell_days = _trailing_run(dry_flags)
        max_dry_spell_days = _longest_run(dry_flags)
        max_wet_spell_days = _longest_run(wet_flags)
        if len(continuous) >= 5:
            rolling = continuous["precip_sum"].rolling(window=5).sum()
            max_5day_position = rolling.idxmax()
            if pd.notna(rolling.loc[max_5day_position]):
                max_5day_precip = round(float(rolling.loc[max_5day_position]), 1)
                end_day = pd.Timestamp(continuous.loc[max_5day_position, "_day"])
                max_5day_period_end = end_day.date().isoformat()
                max_5day_period_start = (
                    end_day - pd.Timedelta(days=4)
                ).date().isoformat()
        dry_spell_status = "рассчитано по непрерывному ряду осадков"
    else:
        dry_spell_status = (
            "не рассчитано: для длительности серии нужен непрерывный ряд "
            "без пропущенных суток и значений осадков"
        )

    if season_start_day is None:
        scope_note = (
            "дата начала сезона не задана; накопления относятся к доступному "
            "завершённому периоду"
        )
    elif not coverage_start_reached:
        scope_note = (
            "ряд не достигает локальной даты начала сезона; сезонные "
            "накопления не заявляются"
        )
    elif not period_is_season:
        scope_note = (
            "ряд достигает даты сезона, но доля календарных пропусков "
            f"превышает {max_missing_fraction * 100:.0f}%"
        )
    else:
        scope_note = "период с начала сезона покрыт в допустимых пределах"

    if not precip_available and not et0_available:
        status = "нет достаточно полного ряда осадков и ET0"
    elif not paired_available:
        status = "осадки/ET0 доступны раздельно, но парная разность не рассчитана"
    else:
        status = "накопления рассчитаны; P−ET0 является климатической разностью"

    return {
        "available": precip_available or et0_available,
        "period_is_season": period_is_season,
        "coverage_start_reached": coverage_start_reached,
        "season_start": (
            None
            if season_start_day is None
            else season_start_day.date().isoformat()
        ),
        "period_start": period_start.date().isoformat(),
        "period_end": period_end.date().isoformat(),
        "expected_days": expected_days,
        "row_days": row_days,
        "calendar_missing_days": calendar_missing_days,
        "calendar_missing_fraction": calendar_missing_fraction,
        "precip_available": precip_available,
        "precip_sum_mm": precip_sum,
        "wet_day_precip_sum_mm": wet_day_precip_sum,
        "precip_valid_days": precip_valid_days,
        "precip_missing_days": precip_missing_days,
        "precip_missing_fraction": precip_missing_fraction,
        "wet_days": wet_days,
        "dry_days": dry_days,
        "max_1day_precip_mm": max_1day_precip,
        "max_1day_precip_date": max_1day_precip_date,
        "max_5day_precip_mm": max_5day_precip,
        "max_5day_period_start": max_5day_period_start,
        "max_5day_period_end": max_5day_period_end,
        "dry_spell_available": dry_spell_available,
        "trailing_dry_spell_days": trailing_dry_spell_days,
        "max_dry_spell_days": max_dry_spell_days,
        "max_wet_spell_days": max_wet_spell_days,
        "dry_spell_status": dry_spell_status,
        "dry_day_threshold_mm": dry_day_threshold_mm,
        "et0_available": et0_available,
        "et0_sum_mm": et0_sum,
        "et0_valid_days": et0_valid_days,
        "et0_missing_days": et0_missing_days,
        "et0_missing_fraction": et0_missing_fraction,
        "paired_available": paired_available,
        "paired_days": paired_days,
        "paired_missing_days": paired_missing_days,
        "paired_missing_fraction": paired_missing_fraction,
        "paired_precip_sum_mm": paired_precip_sum,
        "paired_et0_sum_mm": paired_et0_sum,
        "p_minus_et0_mm": p_minus_et0,
        "et0_minus_p_mm": et0_minus_p,
        "negative_precip_days": negative_precip_days,
        "negative_et0_days": negative_et0_days,
        "source_counts": _source_counts(precip),
        "paired_source_counts": _source_counts(paired),
        "status": status,
        "scope_note": scope_note,
        "units": {"water_depth": "мм", "duration": "сут"},
        "et0_source": "provider et0_fao_evapotranspiration",
        "method_references": (
            "ETCCDI/Climdex: CDD, RR < 1 мм/сут",
            "Allen et al. (1998), FAO Irrigation and Drainage Paper 56",
        ),
        "limitations": (
            "P−ET0 не учитывает Kc, фактическую ET культуры, запасы влаги, "
            "сток, инфильтрацию, капиллярный подъём и глубину корней"
        ),
        "max_missing_fraction": max_missing_fraction,
    }
