from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.domain.pests import (
    PestModel,
    PestNotification,
    PestOutlook,
    get_pest_model,
    next_stage,
    stage_for_accumulation,
)

_COMPLETED_KINDS = frozenset({"observation", "reanalysis", "operational_past"})
_FORECAST_KINDS = frozenset({"current_forecast", "forecast"})


def daily_average_degree_days(
    t_min_c: float,
    t_max_c: float,
    *,
    lower_threshold_c: float,
    upper_threshold_c: float | None = None,
) -> float:
    """Return one daily heat increment using the transparent max-min method."""

    values = (t_min_c, t_max_c, lower_threshold_c)
    if not all(pd.notna(value) for value in values):
        raise ValueError("Для расчёта тепла нужны Tmin, Tmax и нижний порог.")
    if t_min_c > t_max_c:
        raise ValueError("Минимальная температура не может быть выше максимальной.")
    if upper_threshold_c is not None and upper_threshold_c <= lower_threshold_c:
        raise ValueError("Верхний порог должен быть выше нижнего.")

    mean_c = (float(t_min_c) + float(t_max_c)) / 2.0
    if upper_threshold_c is not None:
        mean_c = min(mean_c, float(upper_threshold_c))
    return max(0.0, mean_c - float(lower_threshold_c))


def _prepare_daily(df_daily: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "t_min", "t_max"}
    missing = required.difference(df_daily.columns)
    if missing:
        raise ValueError(
            "Не хватает погодных столбцов: " + ", ".join(sorted(missing))
        )

    optional = {"data_kind", "data_source", "local_date"}.intersection(
        df_daily.columns
    )
    frame = df_daily[list(required | optional)].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame["t_min"] = pd.to_numeric(frame["t_min"], errors="coerce")
    frame["t_max"] = pd.to_numeric(frame["t_max"], errors="coerce")
    frame = frame.dropna(subset=["date"])

    if "local_date" in frame.columns:
        local_day = pd.to_datetime(frame["local_date"], errors="coerce")
        frame["_day"] = local_day.dt.normalize()
    else:
        frame["_day"] = frame["date"].dt.tz_localize(None).dt.normalize()
    frame = frame.dropna(subset=["_day"])
    frame.loc[frame["t_min"] > frame["t_max"], ["t_min", "t_max"]] = pd.NA
    return frame.sort_values(["_day", "date"])


def _select_kind(frame: pd.DataFrame, kinds: frozenset[str]) -> pd.DataFrame:
    selected = frame
    if "data_kind" in frame.columns:
        selected = frame[frame["data_kind"].isin(kinds)]
    return selected.sort_values(["_day", "date"]).drop_duplicates(
        "_day",
        keep="last",
    )


def _source_counts(frame: pd.DataFrame) -> dict[str, int]:
    if frame.empty or "data_kind" not in frame.columns:
        return {}
    return {
        str(key): int(value)
        for key, value in frame["data_kind"].value_counts().to_dict().items()
    }


def _empty_outlook(
    model: PestModel,
    biofix_date: date,
    status: str,
    *,
    completed_days: int = 0,
    expected_days: int = 0,
    missing_days: int = 0,
    period_end: date | None = None,
    source_counts: dict[str, int] | None = None,
) -> PestOutlook:
    return PestOutlook(
        available=False,
        status=status,
        model=model,
        biofix_date=biofix_date,
        accumulated_dd_c=None,
        completed_days=completed_days,
        expected_days=expected_days,
        missing_days=missing_days,
        current_stage=None,
        next_stage=None,
        next_threshold_dd_c=None,
        projected_crossing_date=None,
        forecast_added_dd_c=None,
        forecast_days=0,
        period_end=period_end,
        source_counts=source_counts or {},
    )


def _daily_increment(row: pd.Series, model: PestModel) -> float:
    if model.calculation_method != "daily_average":
        raise ValueError("Метод расчёта модели вредителя не поддерживается.")
    return daily_average_degree_days(
        float(row["t_min"]),
        float(row["t_max"]),
        lower_threshold_c=model.lower_threshold_c,
        upper_threshold_c=model.upper_threshold_c,
    )


def _continuous_forecast_prefix(
    forecast: pd.DataFrame,
    *,
    today: date,
    horizon_days: int,
) -> pd.DataFrame:
    if horizon_days <= 0:
        return forecast.iloc[0:0].copy()
    by_day = {
        row["_day"].date(): row
        for _, row in forecast.sort_values("_day").iterrows()
    }
    rows: list[pd.Series] = []
    for offset in range(horizon_days):
        day = today + timedelta(days=offset)
        row = by_day.get(day)
        if row is None or pd.isna(row["t_min"]) or pd.isna(row["t_max"]):
            break
        rows.append(row)
    if not rows:
        return forecast.iloc[0:0].copy()
    return pd.DataFrame(rows).reset_index(drop=True)


def calculate_pest_outlook(
    df_daily: pd.DataFrame,
    pest_key: str,
    *,
    biofix_date: date,
    today: date,
    forecast_horizon_days: int = 7,
) -> PestOutlook:
    """Calculate a monitoring window from a user-confirmed biological event.

    The result predicts temperature-dependent development only. It does not
    infer pest presence, abundance, crop damage or a treatment requirement.
    """

    model = get_pest_model(pest_key)
    if biofix_date > today:
        return _empty_outlook(
            model,
            biofix_date,
            "дата первой находки находится в будущем",
        )
    if forecast_horizon_days < 0:
        raise ValueError("Горизонт прогноза не может быть отрицательным.")

    frame = _prepare_daily(df_daily)
    completed = _select_kind(frame, _COMPLETED_KINDS)
    forecast = _select_kind(frame, _FORECAST_KINDS)

    last_completed = today - timedelta(days=1)
    expected_days = max(0, (last_completed - biofix_date).days + 1)
    period_end = last_completed if expected_days else None

    if expected_days:
        completed = completed[
            (completed["_day"].dt.date >= biofix_date)
            & (completed["_day"].dt.date <= last_completed)
        ].copy()
        valid = completed.dropna(subset=["t_min", "t_max"])
        valid_days = {value.date() for value in valid["_day"]}
        expected = {
            biofix_date + timedelta(days=offset) for offset in range(expected_days)
        }
        missing_days = len(expected.difference(valid_days))
        if missing_days:
            return _empty_outlook(
                model,
                biofix_date,
                (
                    "расчёт скрыт: в завершённом ряду пропущено "
                    f"{missing_days} из {expected_days} суток"
                ),
                completed_days=len(valid_days),
                expected_days=expected_days,
                missing_days=missing_days,
                period_end=period_end,
                source_counts=_source_counts(valid),
            )
        completed = valid.sort_values("_day")
    else:
        completed = completed.iloc[0:0].copy()

    accumulated = sum(
        _daily_increment(row, model) for _, row in completed.iterrows()
    )
    current = stage_for_accumulation(model, accumulated)
    upcoming = next_stage(model, current)
    next_threshold = None if upcoming is None else upcoming.start_dd_c

    forecast = forecast[forecast["_day"].dt.date >= today].copy()
    forecast_prefix = _continuous_forecast_prefix(
        forecast,
        today=today,
        horizon_days=forecast_horizon_days,
    )
    projected_crossing: date | None = None
    forecast_added = 0.0
    if not forecast_prefix.empty:
        running = accumulated
        for _, row in forecast_prefix.iterrows():
            increment = _daily_increment(row, model)
            forecast_added += increment
            running += increment
            if (
                projected_crossing is None
                and next_threshold is not None
                and running >= next_threshold
            ):
                projected_crossing = row["_day"].date()

    return PestOutlook(
        available=True,
        status="расчётное окно наблюдения сформировано",
        model=model,
        biofix_date=biofix_date,
        accumulated_dd_c=round(accumulated, 1),
        completed_days=expected_days,
        expected_days=expected_days,
        missing_days=0,
        current_stage=current,
        next_stage=upcoming,
        next_threshold_dd_c=next_threshold,
        projected_crossing_date=projected_crossing,
        forecast_added_dd_c=(
            round(forecast_added, 1) if not forecast_prefix.empty else None
        ),
        forecast_days=int(len(forecast_prefix)),
        period_end=period_end,
        source_counts=_source_counts(completed),
    )


def choose_pest_notification(
    outlook: PestOutlook,
    *,
    last_notified_stage: str | None,
    last_notified_advance: str | None,
    today: date,
    advance_days: int = 3,
) -> PestNotification | None:
    """Choose one deduplicated scouting reminder for the current calculation."""

    if not outlook.available or outlook.current_stage is None:
        return None
    if advance_days < 0:
        raise ValueError("Срок предварительного напоминания не может быть отрицательным.")

    prefix = f"{outlook.model.model_version}:{outlook.biofix_date.isoformat()}"
    current_key = f"{prefix}:current:{outlook.current_stage.key}"
    if last_notified_stage != current_key:
        return PestNotification(
            event_key=current_key,
            kind="current_window",
            stage=outlook.current_stage,
            expected_date=None,
        )

    if outlook.next_stage is None or outlook.projected_crossing_date is None:
        return None
    lead_days = (outlook.projected_crossing_date - today).days
    if not 0 <= lead_days <= advance_days:
        return None

    approaching_key = f"{prefix}:approaching:{outlook.next_stage.key}"
    if last_notified_advance == approaching_key:
        return None
    return PestNotification(
        event_key=approaching_key,
        kind="approaching_window",
        stage=outlook.next_stage,
        expected_date=outlook.projected_crossing_date,
    )
