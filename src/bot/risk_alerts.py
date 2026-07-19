from __future__ import annotations

import html

from src.agro.crop_catalog import get_crop_name
from src.domain.risk import RiskEvent, RiskOutlook
from src.domain.risk_delivery import risk_delivery_mode_label

_RISK_LABELS = {
    "frost": ("🌡", "Заморозок / холод"),
    "heat": ("🔥", "Сильная жара"),
    "heavy_rain": ("🌧", "Сильные осадки"),
    "strong_wind": ("💨", "Сильный ветер"),
    "convection": ("⛈", "Конвективная неустойчивость"),
}
_LEVEL_LABELS = {
    "watch": "наблюдение",
    "elevated": "повышенный",
    "high": "высокий",
}


def format_ensemble_risk_alert(
    event: RiskEvent,
    outlook: RiskOutlook,
    *,
    field_name: str,
    crop: str | None = None,
    phase: str | None = None,
) -> str:
    emoji, label = _RISK_LABELS[event.risk_type]
    crop_line = (
        f"\n🌾 Культура: <b>{html.escape(get_crop_name(crop))}</b>" if crop else ""
    )
    phase_line = (
        f"\n🌿 Фаза: <b>{html.escape(phase)}</b> (указана пользователем)"
        if phase
        else ""
    )
    coverage_line = ""
    if outlook.forecast_days > 0:
        coverage_line = (
            f"\n• Полностью проверено суток: {outlook.valid_days} из "
            f"{outlook.forecast_days}"
        )
        if outlook.incomplete_days:
            coverage_line += (
                f"; исключено из-за неполных данных: {outlook.incomplete_days}"
            )
    lead = "сегодня" if event.lead_days == 0 else f"через {event.lead_days} сут."
    raw_percent = event.member_fraction * 100.0
    severe_percent = event.severe_member_fraction * 100.0
    threshold_sign = "≤" if event.risk_type == "frost" else "≥"

    return (
        f"{emoji} <b>Предупреждение: {label}</b>\n"
        f"🗺 Поле: <b>{html.escape(field_name)}</b>\n"
        f"📅 Дата: <b>{event.event_date:%d.%m.%Y}</b> ({lead})\n"
        f"⚠️ Уровень скрининга: <b>{_LEVEL_LABELS[event.level]}</b>\n"
        f"📊 Доля ансамбля: <b>{event.members_exceeding} из "
        f"{event.valid_members} ({raw_percent:.0f}%)</b> для порога "
        f"{threshold_sign}{event.threshold:g} {html.escape(event.unit)}\n"
        f"• Более строгий порог {threshold_sign}{event.severe_threshold:g}: "
        f"{event.severe_members_exceeding} из {event.valid_members} "
        f"({severe_percent:.0f}%)\n"
        f"• Диапазон P10–P90: {event.p10:g}…{event.p90:g}; "
        f"медиана {event.median:g} {html.escape(event.unit)}\n"
        f"• Модель: {html.escape(event.model)}; {html.escape(event.reliability_note)}"
        f"{coverage_line}{crop_line}{phase_line}\n\n"
        f"<b>Что делать:</b> {html.escape(event.action)}\n\n"
        f"<b>Ограничение:</b> {html.escape(event.caveat)}\n"
        "Доля ансамбля — это сырая доля модельных сценариев, а не "
        "откалиброванная вероятность. Проверяйте официальные предупреждения и "
        "более свежие прогнозы перед затратным или необратимым решением."
    )


def _digest_event_line(event: RiskEvent) -> str:
    emoji, label = _RISK_LABELS[event.risk_type]
    lead = "сегодня" if event.lead_days == 0 else f"через {event.lead_days} сут."
    raw_percent = event.member_fraction * 100.0
    threshold_sign = "≤" if event.risk_type == "frost" else "≥"
    return (
        f"• {emoji} <b>{label}</b> — {event.event_date:%d.%m}, {lead}; "
        f"уровень {_LEVEL_LABELS[event.level]}; "
        f"{event.members_exceeding} из {event.valid_members} ({raw_percent:.0f}%) "
        f"для {threshold_sign}{event.threshold:g} {html.escape(event.unit)}; "
        f"медиана {event.median:g}, P10–P90 {event.p10:g}…{event.p90:g}."
    )


def _unique_actions(events: tuple[RiskEvent, ...], limit: int = 3) -> tuple[str, ...]:
    actions: list[str] = []
    for event in events:
        if event.action not in actions:
            actions.append(event.action)
        if len(actions) >= limit:
            break
    return tuple(actions)


def format_ensemble_risk_digest(
    events: tuple[RiskEvent, ...],
    outlook: RiskOutlook,
    *,
    field_name: str,
    crop: str | None,
    phase: str | None,
    delivery_mode: str,
    priority_bypass: bool,
) -> str:
    if not events:
        raise ValueError("Risk digest requires at least one event")

    lines = [
        "⚠️ <b>Сводка погодных рисков</b>",
        f"🗺 Поле: <b>{html.escape(field_name)}</b>",
    ]
    if crop:
        lines.append(f"🌾 Культура: <b>{html.escape(get_crop_name(crop))}</b>")
    if phase:
        lines.append(f"🌿 Фаза: <b>{html.escape(phase)}</b> (наблюдение пользователя)")
    lines.extend(["", "<b>Что происходит</b>"])
    lines.extend(_digest_event_line(event) for event in events)

    lines.extend(["", "<b>Что делать сейчас</b>"])
    for action in _unique_actions(events):
        lines.append(f"• {html.escape(action)}")

    lines.extend(
        [
            "",
            "<b>Надёжность</b>",
            f"• Модель: {html.escape(events[0].model)}; полностью проверено "
            f"суток {outlook.valid_days} из {outlook.forecast_days}.",
            f"• Режим доставки: {html.escape(risk_delivery_mode_label(delivery_mode))}.",
            "• Доля ансамбля — сырая доля модельных сценариев, а не "
            "откалиброванная вероятность события или ущерба.",
            "• CAPE указывает только на потенциальную конвективную среду и не "
            "является прогнозом грозы или града.",
        ]
    )
    if priority_bypass:
        lines.append(
            "• В сводке есть высокий уровень: сообщение отправлено без ожидания "
            "обычного окна доставки."
        )
    lines.append(
        "• Перед затратным или необратимым решением проверьте официальное "
        "предупреждение, локальную станцию и фактическое состояние поля."
    )

    text = "\n".join(lines)
    if len(text) > 4096:
        raise ValueError("Risk digest exceeds Telegram message limit")
    return text


def format_ensemble_data_unavailable(field_name: str, reason: str) -> str:
    return (
        "⚠️ <b>Ежедневный анализ погодных рисков не выполнен</b>\n"
        f"🗺 Поле: <b>{html.escape(field_name)}</b>\n"
        f"Причина: {html.escape(reason)}.\n\n"
        "Отсутствие ансамблевых данных не означает отсутствие риска. Проверьте "
        "официальный локальный прогноз и повторите анализ после обновления данных."
    )
