from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date

from src.agro.crop_catalog import get_crop_name
from src.domain.risk import RiskEvent, RiskLevel, RiskType

_RISK_ORDER: dict[RiskType, int] = {
    "frost": 0,
    "heat": 1,
    "heavy_rain": 2,
    "strong_wind": 3,
    "convection": 4,
}
_LEVEL_ORDER: dict[RiskLevel, int] = {"watch": 0, "elevated": 1, "high": 2}
_NEAR_TERM_PRIORITY: dict[RiskLevel, str] = {
    "watch": "наблюдать и проверить следующий запуск",
    "elevated": "подготовить меры и уточнить локальный прогноз",
    "high": "подготовиться, сверив официальный и локальный прогноз",
}
_RISK_NAMES: dict[RiskType, tuple[str, str]] = {
    "frost": ("🌡", "Холод / возможный заморозок"),
    "heat": ("🔥", "Жара"),
    "heavy_rain": ("🌧", "Сильные осадки"),
    "strong_wind": ("💨", "Сильные порывы ветра"),
    "convection": ("⛈", "Неустойчивая атмосфера"),
}
_MONTHS = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


@dataclass(frozen=True, slots=True)
class RiskPeriod:
    risk_type: RiskType
    events: tuple[RiskEvent, ...]
    start_date: date
    end_date: date
    highest_level: RiskLevel


def model_label(model: str) -> str:
    labels = {
        "gfs_seamless": "ансамбль GFS",
        "gfs": "ансамбль GFS",
    }
    return labels.get(model, model.replace("_", " "))


def _date_label(value: date) -> str:
    return f"{value.day} {_MONTHS[value.month]}"


def period_date_label(period: RiskPeriod) -> str:
    if period.start_date == period.end_date:
        return _date_label(period.start_date)
    if period.start_date.month == period.end_date.month:
        return (
            f"{period.start_date.day}–{period.end_date.day} "
            f"{_MONTHS[period.start_date.month]}"
        )
    return f"{_date_label(period.start_date)} — {_date_label(period.end_date)}"


def condition_text(event: RiskEvent) -> str:
    threshold = event.threshold
    if event.risk_type == "frost":
        return f"минимальная температура воздуха на высоте 2 м — {threshold:g}°C или ниже"
    if event.risk_type == "heat":
        return f"дневной максимум воздуха на высоте 2 м — {threshold:g}°C или выше"
    if event.risk_type == "heavy_rain":
        return f"суточная сумма осадков — {threshold:g} мм или больше"
    if event.risk_type == "strong_wind":
        return f"порывы ветра на высоте 10 м — {threshold:g} м/с или сильнее"
    return (
        f"CAPE — {threshold:g} Дж/кг или выше; это запас энергии для конвекции, "
        "а не прогноз грозы или града"
    )


def _value_unit(risk_type: RiskType) -> str:
    if risk_type in {"frost", "heat"}:
        return "°C"
    if risk_type == "heavy_rain":
        return "мм/сут"
    if risk_type == "strong_wind":
        return "м/с"
    return "Дж/кг"


def _value_label(risk_type: RiskType) -> str:
    labels = {
        "frost": "ожидаемый минимум",
        "heat": "ожидаемый максимум",
        "heavy_rain": "ожидаемая суточная сумма",
        "strong_wind": "ожидаемый порыв",
        "convection": "ожидаемый CAPE",
    }
    return labels[risk_type]


def _number(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _range_text(low: float, high: float, unit: str) -> str:
    if abs(low - high) < 0.05:
        return f"{_number(low)} {unit}"
    return f"{_number(low)}–{_number(high)} {unit}"


def agreement_label(fraction: float) -> str:
    if fraction >= 0.80:
        return "очень высокая согласованность вариантов текущего запуска"
    if fraction >= 0.60:
        return "высокая согласованность вариантов текущего запуска"
    if fraction >= 0.30:
        return "средняя согласованность; прогноз ещё может заметно измениться"
    return "слабый ранний сигнал; требуется подтверждение следующими запусками"


def priority_label(level: RiskLevel, lead_days: int) -> str:
    """Translate a model signal into a cautious action priority.

    A large member fraction at long lead is not temporal stability. Long-range
    signals therefore remain planning information even when many members agree.
    """

    if lead_days > 10:
        return "дальний сигнал — только предварительное планирование"
    if lead_days > 7:
        return "подготовить варианты действий и подтвердить прогноз ближе к дате"
    if lead_days > 3:
        if level == "watch":
            return "следить за обновлениями и проверить ближе к дате"
        return "заранее подготовить меры и уточнять прогноз"
    return _NEAR_TERM_PRIORITY[level]


def group_risk_events(events: tuple[RiskEvent, ...]) -> tuple[RiskPeriod, ...]:
    """Join consecutive days of one hazard into readable weather periods."""

    grouped: list[RiskPeriod] = []
    by_type: dict[RiskType, list[RiskEvent]] = {}
    for event in events:
        by_type.setdefault(event.risk_type, []).append(event)

    for risk_type, typed_events in by_type.items():
        ordered = sorted(typed_events, key=lambda item: item.event_date)
        current: list[RiskEvent] = []
        for event in ordered:
            if current and (event.event_date - current[-1].event_date).days > 1:
                grouped.append(_make_period(risk_type, current))
                current = []
            current.append(event)
        if current:
            grouped.append(_make_period(risk_type, current))

    grouped.sort(
        key=lambda period: (
            period.start_date,
            -_LEVEL_ORDER[period.highest_level],
            _RISK_ORDER[period.risk_type],
        )
    )
    return tuple(grouped)


def _make_period(risk_type: RiskType, events: list[RiskEvent]) -> RiskPeriod:
    highest = max(events, key=lambda item: _LEVEL_ORDER[item.level]).level
    return RiskPeriod(
        risk_type=risk_type,
        events=tuple(events),
        start_date=events[0].event_date,
        end_date=events[-1].event_date,
        highest_level=highest,
    )


def format_risk_period(period: RiskPeriod) -> str:
    emoji, name = _RISK_NAMES[period.risk_type]
    events = period.events
    valid_members = max(event.valid_members for event in events)
    counts = [event.members_exceeding for event in events]
    fractions = [event.member_fraction for event in events]
    medians = [event.median for event in events]
    spread_low = min(event.p10 for event in events)
    spread_high = max(event.p90 for event in events)
    unit = _value_unit(period.risk_type)
    count_text = (
        f"{counts[0]} из {valid_members}"
        if min(counts) == max(counts)
        else f"от {min(counts)} до {max(counts)} из {valid_members}"
    )
    lead_min = min(event.lead_days for event in events)
    lead_max = max(event.lead_days for event in events)
    if lead_min == 0 and lead_max == 0:
        lead_text = "сегодня"
    elif lead_min == lead_max:
        lead_text = f"через {lead_min} сут."
    elif lead_min == 0:
        lead_text = f"сегодня — через {lead_max} сут."
    else:
        lead_text = f"через {lead_min}–{lead_max} сут."

    return (
        f"{emoji} <b>{name}: {period_date_label(period)}</b>\n"
        f"• {count_text} вариантов модели показывают условие: "
        f"{html.escape(condition_text(events[0]))}.\n"
        f"• {_value_label(period.risk_type).capitalize()}: "
        f"{_range_text(min(medians), max(medians), unit)}; основной разброс "
        f"вариантов {_range_text(spread_low, spread_high, unit)}.\n"
        f"• {agreement_label(min(fractions)).capitalize()}; срок: {lead_text}.\n"
        f"• Приоритет: {priority_label(period.highest_level, lead_min)}."
    )


def crop_context_lines(
    *,
    crops: tuple[str, ...],
    selected_crop: str | None,
    phase: str | None,
) -> list[str]:
    keys = tuple(dict.fromkeys(key for key in crops if key))
    if not keys and selected_crop:
        keys = (selected_crop,)
    lines: list[str] = []
    if keys:
        names = ", ".join(get_crop_name(key) for key in keys)
        lines.append(f"🌱 Культуры на точке: <b>{html.escape(names)}</b>")
    if len(keys) > 1:
        lines.append(
            "ℹ️ Погодные условия общие для точки. Чувствительность культур "
            "различается; повреждение каждой культуры отдельно не рассчитано."
        )
    if selected_crop:
        lines.append(
            f"✅ Для сезонного отчёта выбрана: "
            f"<b>{html.escape(get_crop_name(selected_crop))}</b>"
        )
    if phase:
        lines.append(
            f"🌿 Фаза выбранной культуры: <b>{html.escape(phase)}</b> "
            "(наблюдение пользователя)"
        )
    else:
        lines.append(
            "🌿 Фаза выбранной культуры не указана. Погодный сигнал рассчитан, "
            "но повреждение растения не оценивается."
        )
    return lines


def unique_actions(periods: tuple[RiskPeriod, ...], limit: int = 3) -> tuple[str, ...]:
    actions: list[str] = []
    for period in periods:
        action = period.events[0].action
        if action not in actions:
            actions.append(action)
        if len(actions) >= limit:
            break
    return tuple(actions)
