"""Scientifically bounded multi-hazard screening from ensemble member forecasts.

The only probabilistic quantity calculated here is the raw member exceedance
fraction ``k / n``. It is deliberately not called a calibrated probability.
Operational thresholds are screening policy, not crop-damage thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

from src.domain.risk import EnsembleForecastData, RiskEvent, RiskOutlook, RiskType

Direction = Literal["below", "above"]

MIN_VALID_MEMBERS = 20
MIN_ALERT_FRACTION = 0.15


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    risk_type: RiskType
    column: str
    direction: Direction
    threshold: float
    severe_threshold: float
    unit: str
    action: str
    caveat: str


RISK_POLICIES: tuple[RiskPolicy, ...] = (
    RiskPolicy(
        risk_type="frost",
        column="t_min_c",
        direction="below",
        threshold=2.0,
        severe_threshold=0.0,
        unit="°C, Tmin воздуха 2 м",
        action=(
            "Проверьте низины и показания полевого датчика; заранее подготовьте "
            "доступные для культуры защитные меры и повторите оценку по более "
            "свежему краткосрочному прогнозу."
        ),
        caveat=(
            "Порог 2°C — уровень внимания, 0°C — замерзание воды. Это не "
            "температура листа и не нормативный порог повреждения культуры."
        ),
    ),
    RiskPolicy(
        risk_type="heat",
        column="t_max_c",
        direction="above",
        threshold=32.0,
        severe_threshold=35.0,
        unit="°C, Tmax воздуха 2 м",
        action=(
            "Проверьте влажность почвы и признаки стресса; перенесите чувствительные "
            "операции с полуденных часов и уточните потребность в воде по фактической "
            "фазе, почве и локальным измерениям."
        ),
        caveat=(
            "Это общий тепловой скрининг. Критические температуры зависят от "
            "культуры, сорта, фазы, влажности воздуха и обеспеченности водой."
        ),
    ),
    RiskPolicy(
        risk_type="heavy_rain",
        column="precip_mm",
        direction="above",
        threshold=30.0,
        severe_threshold=50.0,
        unit="мм/сут",
        action=(
            "Осмотрите водоотвод и участки застоя воды; не планируйте работы, "
            "усиливающие уплотнение почвы, и отдельно проверьте риск смыва на склонах."
        ),
        caveat=(
            "Суточная сумма в модельной ячейке не определяет локальный ливень, "
            "подтопление или эрозию без данных рельефа, почвы и интенсивности осадков."
        ),
    ),
    RiskPolicy(
        risk_type="strong_wind",
        column="wind_gust_ms",
        direction="above",
        threshold=15.0,
        severe_threshold=20.0,
        unit="м/с, порыв 10 м",
        action=(
            "Закрепите теплицы, укрытия и поливное оборудование; проверьте опоры и "
            "перенесите опрыскивание, если ветер превышает ограничения этикетки и "
            "местных правил."
        ),
        caveat=(
            "Порыв на высоте 10 м не равен ветру внутри посева; повреждаемость "
            "зависит от культуры, фазы, влажности почвы и экспозиции поля."
        ),
    ),
    RiskPolicy(
        risk_type="convection",
        column="cape_j_kg",
        direction="above",
        threshold=1000.0,
        severe_threshold=2000.0,
        unit="Дж/кг, CAPE max",
        action=(
            "Следите за официальными штормовыми предупреждениями и радаром; заранее "
            "закрепите оборудование и обеспечьте безопасное укрытие для людей и техники."
        ),
        caveat=(
            "CAPE показывает потенциальную конвективную неустойчивость. Это не "
            "прогноз грозы или града: необходимы подъём, влага, вертикальный сдвиг "
            "ветра, уровень замерзания и краткосрочные наблюдения."
        ),
    ),
)

_LEVEL_ORDER = {"high": 0, "elevated": 1, "watch": 2}


def _fraction(values: pd.Series, policy: RiskPolicy, threshold: float) -> tuple[int, float]:
    if policy.direction == "below":
        exceed = values <= threshold
    else:
        exceed = values >= threshold
    count = int(exceed.sum())
    return count, count / len(values)


def _risk_level(watch_fraction: float, severe_fraction: float) -> str | None:
    if severe_fraction >= 0.30 or watch_fraction >= 0.60:
        return "high"
    if severe_fraction >= 0.15 or watch_fraction >= 0.30:
        return "elevated"
    if watch_fraction >= MIN_ALERT_FRACTION:
        return "watch"
    return None


def _reliability_note(lead_days: int) -> str:
    if lead_days <= 3:
        return "короткий срок; ансамблевый сигнал следует сверить с локальными данными"
    if lead_days <= 7:
        return "средний срок; возможны заметные изменения следующих запусков"
    if lead_days <= 10:
        return "расширенный срок; используйте для подготовки, а не точного решения"
    return "дальний срок; низкая детализация и высокая изменчивость сценариев"


def calc_ensemble_risks(
    forecast: EnsembleForecastData,
    *,
    as_of_date: date,
    min_valid_members: int = MIN_VALID_MEMBERS,
) -> RiskOutlook:
    if min_valid_members < 2:
        raise ValueError("min_valid_members must be at least 2")

    frame = forecast.daily_members.copy()
    required = {"local_date", "member_id"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError("Missing ensemble columns: " + ", ".join(sorted(missing)))

    frame["local_date"] = pd.to_datetime(frame["local_date"], errors="coerce").dt.date
    frame = frame.dropna(subset=["local_date", "member_id"])
    frame = frame[frame["local_date"] >= as_of_date]
    if frame.empty:
        return RiskOutlook(
            available=False,
            status="нет прогнозных локальных суток",
            model=forecast.meta.model,
            member_count=forecast.meta.member_count,
            generated_for_date=as_of_date,
        )

    events: list[RiskEvent] = []
    valid_day_count = 0
    for local_day, day_frame in frame.groupby("local_date", sort=True):
        day_has_valid_policy = False
        lead_days = max(0, (local_day - as_of_date).days)
        for policy in RISK_POLICIES:
            if policy.column not in day_frame.columns:
                continue
            member_values = day_frame[["member_id", policy.column]].drop_duplicates(
                "member_id", keep="last"
            )
            values = pd.to_numeric(
                member_values[policy.column], errors="coerce"
            ).dropna()
            valid_members = int(values.shape[0])
            if valid_members < min_valid_members:
                continue
            day_has_valid_policy = True

            watch_count, watch_fraction = _fraction(values, policy, policy.threshold)
            severe_count, severe_fraction = _fraction(
                values,
                policy,
                policy.severe_threshold,
            )
            level = _risk_level(watch_fraction, severe_fraction)
            if level is None:
                continue

            quantiles = values.quantile([0.10, 0.50, 0.90])
            events.append(
                RiskEvent(
                    risk_type=policy.risk_type,
                    event_date=local_day,
                    lead_days=lead_days,
                    level=level,
                    members_exceeding=watch_count,
                    valid_members=valid_members,
                    member_fraction=round(watch_fraction, 4),
                    severe_members_exceeding=severe_count,
                    severe_member_fraction=round(severe_fraction, 4),
                    threshold=policy.threshold,
                    severe_threshold=policy.severe_threshold,
                    unit=policy.unit,
                    p10=round(float(quantiles.loc[0.10]), 1),
                    median=round(float(quantiles.loc[0.50]), 1),
                    p90=round(float(quantiles.loc[0.90]), 1),
                    model=forecast.meta.model,
                    reliability_note=_reliability_note(lead_days),
                    action=policy.action,
                    caveat=policy.caveat,
                )
            )
        if day_has_valid_policy:
            valid_day_count += 1

    events.sort(
        key=lambda event: (
            _LEVEL_ORDER[event.level],
            event.lead_days,
            -event.member_fraction,
            event.risk_type,
        )
    )
    status = (
        "риски выше порога уведомления выявлены"
        if events
        else "в валидном ансамбле риски выше порога уведомления не выявлены"
    )
    return RiskOutlook(
        available=valid_day_count > 0,
        status=status if valid_day_count > 0 else "недостаточно членов ансамбля",
        events=tuple(events),
        model=forecast.meta.model,
        member_count=forecast.meta.member_count,
        valid_days=valid_day_count,
        generated_for_date=as_of_date,
    )
