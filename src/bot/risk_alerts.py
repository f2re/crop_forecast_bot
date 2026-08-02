from __future__ import annotations

import html

from src.bot.risk_language import (
    crop_context_lines,
    format_risk_period,
    group_risk_events,
    model_label,
    unique_actions,
)
from src.domain.risk import RiskEvent, RiskOutlook
from src.domain.risk_delivery import risk_delivery_mode_label


def format_ensemble_risk_alert(
    event: RiskEvent,
    outlook: RiskOutlook,
    *,
    field_name: str,
    crop: str | None = None,
    crops: tuple[str, ...] = (),
    phase: str | None = None,
) -> str:
    period = group_risk_events((event,))[0]
    lines = [
        "⚠️ <b>Погодный сигнал для поля</b>",
        f"🗺 Поле: <b>{html.escape(field_name)}</b>",
    ]
    lines.extend(
        crop_context_lines(
            crops=crops,
            selected_crop=crop,
            phase=phase,
        )
    )
    lines.extend(
        [
            "",
            format_risk_period(period),
            "",
            "<b>Что делать</b>",
            f"• {html.escape(event.action)}",
            "",
            "<b>Что означает число вариантов</b>",
            f"• Модель: {html.escape(model_label(event.model))}; полностью "
            f"проверено суток {outlook.valid_days} из {outlook.forecast_days}.",
            "• Число вариантов показывает согласованность модельного сигнала. "
            "Это не откалиброванная вероятность события или ущерба.",
            f"• Ограничение: {html.escape(event.caveat)}",
        ]
    )
    return "\n".join(lines)


def format_ensemble_risk_digest(
    events: tuple[RiskEvent, ...],
    outlook: RiskOutlook,
    *,
    field_name: str,
    crop: str | None,
    phase: str | None,
    delivery_mode: str,
    priority_bypass: bool,
    crops: tuple[str, ...] = (),
) -> str:
    if not events:
        raise ValueError("Risk digest requires at least one event")

    periods = group_risk_events(events)
    lines = [
        "⚠️ <b>Погодные условия, требующие внимания</b>",
        f"🗺 Поле: <b>{html.escape(field_name)}</b>",
    ]
    lines.extend(
        crop_context_lines(
            crops=crops,
            selected_crop=crop,
            phase=phase,
        )
    )
    lines.extend(
        [
            "",
            "<b>Что ожидается</b>",
        ]
    )
    for period in periods[:5]:
        lines.extend([format_risk_period(period), ""])
    hidden = max(0, len(periods) - 5)
    if hidden:
        lines.append(f"• Дополнительных периодов: {hidden}.")

    lines.extend(["<b>Что делать сейчас</b>"])
    for action in unique_actions(periods):
        lines.append(f"• {html.escape(action)}")

    lines.extend(
        [
            "",
            "<b>Надёжность</b>",
            f"• Модель: {html.escape(model_label(events[0].model))}; полностью "
            f"проверено суток {outlook.valid_days} из {outlook.forecast_days}.",
            f"• Режим уведомлений: "
            f"{html.escape(risk_delivery_mode_label(delivery_mode))}.",
            "• Каждый вариант — отдельный расчёт модели с немного изменёнными "
            "начальными условиями. Их число показывает согласованность, а не "
            "вероятность повреждения растений.",
            "• Ближайшие дни надёжнее дальней части прогноза. Перед затратным "
            "решением проверьте официальный прогноз и состояние поля.",
        ]
    )
    if any(period.risk_type == "convection" for period in periods):
        lines.append(
            "• CAPE означает возможную неустойчивость атмосферы, но сам по себе "
            "не прогнозирует грозу или град."
        )
    if priority_bypass:
        lines.append(
            "• Сообщение отправлено сразу, потому что модельный сигнал устойчивый."
        )

    text = "\n".join(lines)
    if len(text) > 4096:
        raise ValueError("Risk digest exceeds Telegram message limit")
    return text


def format_ensemble_data_unavailable(field_name: str, reason: str) -> str:
    return (
        "⚠️ <b>Анализ погодных рисков не выполнен</b>\n"
        f"🗺 Поле: <b>{html.escape(field_name)}</b>\n"
        f"Причина: {html.escape(reason)}.\n\n"
        "Отсутствие ансамблевых данных не означает отсутствие опасного явления. "
        "Проверьте официальный локальный прогноз и повторите анализ после "
        "обновления данных."
    )
