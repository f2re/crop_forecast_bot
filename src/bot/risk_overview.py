from __future__ import annotations

import html
from datetime import timezone

from src.agro.crop_catalog import get_crop_name
from src.application.risk_overview import RiskOverview
from src.domain.risk import RiskEvent

_RISK_LABELS = {
    "frost": ("🌡", "холод / возможный заморозок"),
    "heat": ("🔥", "сильная жара"),
    "heavy_rain": ("🌧", "сильные осадки"),
    "strong_wind": ("💨", "сильный ветер"),
    "convection": ("⛈", "конвективная неустойчивость"),
}
_LEVEL_LABELS = {
    "watch": "наблюдение",
    "elevated": "повышенный",
    "high": "высокий",
}
_MAX_EVENTS = 5
_MAX_ACTIONS = 3


def _event_line(event: RiskEvent) -> str:
    emoji, label = _RISK_LABELS[event.risk_type]
    lead = "сегодня" if event.lead_days == 0 else f"через {event.lead_days} сут."
    share = event.member_fraction * 100.0
    threshold_sign = "≤" if event.risk_type == "frost" else "≥"
    return (
        f"• {emoji} <b>{label}</b>: {event.event_date:%d.%m}, {lead}; "
        f"{event.members_exceeding}/{event.valid_members} сценариев "
        f"({share:.0f}%) пересекли {threshold_sign}{event.threshold:g} "
        f"{html.escape(event.unit)}; уровень — {_LEVEL_LABELS[event.level]}; "
        f"медиана {event.median:g}, P10–P90 {event.p10:g}…{event.p90:g}."
    )


def _unique_actions(events: tuple[RiskEvent, ...]) -> list[str]:
    actions: list[str] = []
    for event in events:
        if event.action not in actions:
            actions.append(event.action)
        if len(actions) >= _MAX_ACTIONS:
            break
    return actions


def format_risk_overview(
    overview: RiskOverview,
    *,
    field_name: str,
    crop: str,
    phase: str | None = None,
) -> str:
    """Render one Telegram-safe overview without probability or damage claims."""

    outlook = overview.outlook
    meta = overview.meta
    retrieved_at = meta.retrieved_at.astimezone(timezone.utc)
    safe_field = html.escape(field_name)
    safe_crop = html.escape(get_crop_name(crop))
    safe_phase = html.escape(phase) if phase else None

    lines = [
        "⚠️ <b>Погодные риски на 16 суток</b>",
        f"🗺 Поле: <b>{safe_field}</b>",
        f"🌱 Культура: <b>{safe_crop}</b>",
    ]
    if safe_phase:
        lines.append(f"🌿 Фаза: <b>{safe_phase}</b> — указана пользователем")
    else:
        lines.append("🌿 Фаза: не указана; пороги повреждения культуры не оцениваются")

    lines.extend(["", "<b>Что происходит</b>"])
    if not outlook.available:
        lines.append(f"• Анализ не выполнен: {html.escape(outlook.status)}.")
        lines.append(
            "• Отсутствие полного ансамбля не означает отсутствие локального риска."
        )
    elif outlook.events:
        for event in outlook.events[:_MAX_EVENTS]:
            lines.append(_event_line(event))
        hidden_events = max(0, len(outlook.events) - _MAX_EVENTS)
        if hidden_events:
            lines.append(f"• Ещё сигналов выше порога: {hidden_events}.")
    else:
        lines.append(
            "• На полностью обеспеченных сутках сигналы выше операционных "
            "порогов уведомления не выявлены."
        )

    lines.extend(
        [
            "",
            "<b>Насколько надёжно</b>",
            f"• Модель: {html.escape(meta.model)}; членов ансамбля: "
            f"{meta.member_count}.",
            f"• Полностью оценено суток: {outlook.valid_days} из "
            f"{outlook.forecast_days}; исключено из-за неполных данных: "
            f"{outlook.incomplete_days}.",
            f"• Данные получены: {retrieved_at:%d.%m.%Y %H:%M UTC}; "
            f"источник: {html.escape(meta.source)}.",
            "• Доля ансамбля — сырая доля модельных сценариев, а не "
            "откалиброванная вероятность события или ущерба.",
            "• После 7–10 суток положение и интенсивность явлений могут "
            "существенно измениться между запусками модели.",
        ]
    )

    if outlook.events:
        lines.extend(["", "<b>Что делать сейчас</b>"])
        for action in _unique_actions(outlook.events):
            lines.append(f"• {html.escape(action)}")
    else:
        lines.extend(
            [
                "",
                "<b>Что делать сейчас</b>",
                "• Продолжайте обычный контроль поля и официальных "
                "предупреждений; отсутствие сигнала не исключает локальное явление.",
            ]
        )

    lines.extend(
        [
            "",
            "<b>Когда проверить снова</b>",
            "• После следующего обновления модели, изменения фазы культуры или "
            "появления официального предупреждения.",
            "",
            "CAPE показывается только как конвективная среда и не является "
            "прогнозом грозы или града. Решения с затратами сверяйте с локальной "
            "метеостанцией, официальным прогнозом и фактическим состоянием поля.",
        ]
    )
    text = "\n".join(lines)
    if len(text) > 4096:
        raise ValueError("Risk overview exceeds Telegram message limit")
    return text
