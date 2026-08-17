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
_RISK_NAMES: dict[RiskType, str] = {
    "frost": "Температура приблизится к нулю",
    "heat": "Сильная жара",
    "heavy_rain": "Сильный дождь",
    "strong_wind": "Сильные порывы ветра",
    "convection": "Условия для развития грозовых облаков",
}
_STATUS: dict[RiskLevel, tuple[str, str]] = {
    "watch": ("🟡", "срочных действий нет"),
    "elevated": ("🟠", "подготовьтесь заранее"),
    "high": ("🔴", "подготовьтесь сегодня"),
}
_VALUE_LABELS: dict[RiskType, str] = {
    "frost": "температура",
    "heat": "температура",
    "heavy_rain": "осадки",
    "strong_wind": "порывы",
    "convection": "неустойчивость атмосферы",
}
_ACTIONS: dict[RiskType, dict[RiskLevel, str]] = {
    "frost": {
        "watch": (
            "К вечеру снова проверьте прогноз и температуру рядом с растениями, "
            "особенно в низинах."
        ),
        "elevated": (
            "До вечера подготовьте подходящие для культуры укрытия или другую "
            "заранее отработанную защиту."
        ),
        "high": (
            "До вечера примените заранее выбранную защиту чувствительных посадок "
            "и проверьте температуру рядом с растениями."
        ),
    },
    "heat": {
        "watch": (
            "Утром проверьте влажность почвы на глубине корней и состояние растений."
        ),
        "elevated": (
            "Если почва на глубине корней сухая, полейте рано утром прямо в "
            "корневую зону; перенесите обработки с полудня."
        ),
        "high": (
            "До жары проверьте почву на глубине корней; при нехватке влаги "
            "полейте рано утром и не проводите обработки в пик жары."
        ),
    },
    "heavy_rain": {
        "watch": "Проверьте водоотвод и прогноз перед выездом в поле.",
        "elevated": (
            "Очистите водоотвод; перенесите тяжёлую технику и внесение удобрений, "
            "если возможен смыв."
        ),
        "high": (
            "Освободите водоотвод, уберите технику из низин и не выезжайте на "
            "размокшую почву."
        ),
    },
    "strong_wind": {
        "watch": "Проверьте прогноз перед опрыскиванием и работой с укрытиями.",
        "elevated": (
            "Закрепите теплицы, укрытия, поливные линии и лёгкое оборудование; "
            "перенесите опрыскивание."
        ),
        "high": (
            "Уберите людей от теплиц, сеток и высоких конструкций; остановите "
            "опрыскивание и работу подъёмной техники."
        ),
    },
    "convection": {
        "watch": "Ближе к сроку проверьте официальное предупреждение и радар.",
        "elevated": (
            "Заранее закрепите оборудование. Если есть противоградовая сетка, "
            "проверьте её крепления; не работайте на ней при грозе или сильном ветре."
        ),
        "high": (
            "При официальном предупреждении или приближении грозы уведите людей "
            "с поля в капитальное здание или закрытый автомобиль; теплица и навес "
            "не защищают от молнии."
        ),
    },
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
    """Detailed threshold wording for diagnostics and help screens."""

    threshold = event.threshold
    if event.risk_type == "frost":
        return f"минимальная температура воздуха 2 м — {threshold:g}°C или ниже"
    if event.risk_type == "heat":
        return f"максимальная температура воздуха 2 м — {threshold:g}°C или выше"
    if event.risk_type == "heavy_rain":
        return f"суточные осадки — {threshold:g} мм или больше"
    if event.risk_type == "strong_wind":
        return f"порывы ветра 10 м — {threshold:g} м/с или сильнее"
    return (
        "расчётная неустойчивость атмосферы — "
        f"{threshold:g} Дж/кг или выше"
    )


def _value_unit(risk_type: RiskType) -> str:
    if risk_type in {"frost", "heat"}:
        return "°C"
    if risk_type == "heavy_rain":
        return "мм"
    if risk_type == "strong_wind":
        return "м/с"
    return "Дж/кг"


def _number(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 0.15:
        return str(int(rounded))
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _range_text(low: float, high: float, unit: str) -> str:
    if abs(low - high) < 0.05:
        return f"{_number(low)} {unit}"
    return f"{_number(low)}–{_number(high)} {unit}"


def agreement_label(fraction: float) -> str:
    """Compatibility helper for diagnostics; not shown in automatic alerts."""

    if fraction >= 0.80:
        return "высокая согласованность"
    if fraction >= 0.30:
        return "средняя согласованность"
    return "слабый сигнал"


def priority_label(level: RiskLevel, lead_days: int) -> str:
    """Compatibility helper returning the same action class as the colour badge."""

    if lead_days > 7:
        return "срочных действий нет"
    if lead_days > 3 and level in {"elevated", "high"}:
        return "подготовьтесь заранее"
    return _STATUS[level][1]


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


def presentation_level(period: RiskPeriod) -> RiskLevel:
    """Convert model strength and lead time into a user action level."""

    lead_days = min(event.lead_days for event in period.events)
    if lead_days > 7:
        return "watch"
    if lead_days > 3 and period.highest_level in {"elevated", "high"}:
        return "elevated"
    return period.highest_level


def period_action(period: RiskPeriod) -> str:
    return _ACTIONS[period.risk_type][presentation_level(period)]


def format_risk_period(period: RiskPeriod) -> str:
    level = presentation_level(period)
    emoji, status = _STATUS[level]
    name = _RISK_NAMES[period.risk_type]
    if period.risk_type == "convection":
        details = (
            f"{period_date_label(period)} · атмосфера может стать неустойчивой.\n"
            "Гроза и град этим расчётом не подтверждены. "
            "Проверьте официальное предупреждение и радар."
        )
    else:
        low = min(event.p10 for event in period.events)
        high = max(event.p90 for event in period.events)
        value = _range_text(low, high, _value_unit(period.risk_type))
        details = (
            f"{period_date_label(period)} · {_VALUE_LABELS[period.risk_type]} {value}"
        )
    return (
        f"{emoji} <b>{name} — {status}</b>\n"
        f"{details}\n"
        f"Что лучше сделать: {html.escape(period_action(period))}"
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
        lines.append(f"🌱 {html.escape(names)}")
    if phase:
        if selected_crop:
            crop_name = html.escape(get_crop_name(selected_crop))
            lines.append(f"🌿 {crop_name}: <b>{html.escape(phase)}</b>")
        else:
            lines.append(f"🌿 Фаза: <b>{html.escape(phase)}</b>")
    return lines


def unique_actions(periods: tuple[RiskPeriod, ...], limit: int = 3) -> tuple[str, ...]:
    actions: list[str] = []
    for period in periods:
        action = period_action(period)
        if action not in actions:
            actions.append(action)
        if len(actions) >= limit:
            break
    return tuple(actions)
