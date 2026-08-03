from __future__ import annotations

import html
from datetime import date

from src.bot.risk_language import (
    crop_context_lines,
    format_risk_period,
    group_risk_events,
    model_label,
    unique_actions,
)
from src.domain.risk import RiskEvent, RiskOutlook, RiskType
from src.domain.risk_delivery import (
    RiskEpisodeState,
    RiskStateChange,
    risk_delivery_mode_label,
)

_RISK_NAMES: dict[RiskType, tuple[str, str]] = {
    "frost": ("🌡", "Холод / возможный заморозок"),
    "heat": ("🔥", "Жара"),
    "heavy_rain": ("🌧", "Сильные осадки"),
    "strong_wind": ("💨", "Сильные порывы ветра"),
    "convection": ("⛈", "Неустойчивая атмосфера"),
}
_LEVEL_NAMES = {
    "watch": "наблюдение",
    "elevated": "повышенное внимание",
    "high": "высокий",
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


def _date_label(value: date) -> str:
    return f"{value.day} {_MONTHS[value.month]}"


def _episode_label(episode: RiskEpisodeState) -> str:
    if episode.start_date == episode.end_date:
        period = _date_label(episode.start_date)
    elif episode.start_date.month == episode.end_date.month:
        period = (
            f"{episode.start_date.day}–{episode.end_date.day} "
            f"{_MONTHS[episode.start_date.month]}"
        )
    else:
        period = (
            f"{_date_label(episode.start_date)} — "
            f"{_date_label(episode.end_date)}"
        )
    return f"{period}, уровень «{_LEVEL_NAMES[episode.highest_level]}»"


def _episodes_label(episodes: tuple[RiskEpisodeState, ...]) -> str:
    return "; ".join(_episode_label(episode) for episode in episodes)


def _format_change(change: RiskStateChange) -> str:
    emoji, name = _RISK_NAMES[change.risk_type]
    previous = change.previous
    current = change.current
    if not previous:
        return (
            f"• {emoji} <b>{name}</b>: новый период — "
            f"{html.escape(_episodes_label(current))}."
        )
    if not current:
        return (
            f"• {emoji} <b>{name}</b>: ранее ожидавшийся период "
            f"{html.escape(_episodes_label(previous))} больше не подтверждается."
        )

    if len(previous) == 1 and len(current) == 1:
        old = previous[0]
        new = current[0]
        details: list[str] = []
        if new.start_date < old.start_date:
            details.append(
                f"начнётся раньше: {_date_label(new.start_date)} "
                f"вместо {_date_label(old.start_date)}"
            )
        elif new.start_date > old.start_date:
            details.append(
                f"начнётся позже: {_date_label(new.start_date)} "
                f"вместо {_date_label(old.start_date)}"
            )
        if new.end_date < old.end_date:
            details.append(
                f"закончится раньше: {_date_label(new.end_date)} "
                f"вместо {_date_label(old.end_date)}"
            )
        elif new.end_date > old.end_date:
            details.append(
                f"продлится дольше: до {_date_label(new.end_date)} "
                f"вместо {_date_label(old.end_date)}"
            )
        if new.highest_level != old.highest_level:
            details.append(
                "уровень изменился с "
                f"«{_LEVEL_NAMES[old.highest_level]}» на "
                f"«{_LEVEL_NAMES[new.highest_level]}»"
            )
        if details:
            return (
                f"• {emoji} <b>{name}</b>: "
                f"{html.escape('; '.join(details))}."
            )

    return (
        f"• {emoji} <b>{name}</b>: периоды уточнены. Было: "
        f"{html.escape(_episodes_label(previous))}. Теперь: "
        f"{html.escape(_episodes_label(current))}."
    )


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
    text = "\n".join(lines)
    if len(text) > 4096:
        raise ValueError("Risk alert exceeds Telegram message limit")
    return text


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
    changes: tuple[RiskStateChange, ...] = (),
) -> str:
    if not events and not changes:
        raise ValueError("Risk digest requires events or a semantic change")

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

    if changes:
        lines.extend(["", "<b>Что изменилось</b>"])
        lines.extend(_format_change(change) for change in changes)
        lines.append(
            "• Изменения доли вариантов или отдельных чисел без смены периода "
            "не создают повторное сообщение."
        )

    if periods:
        lines.extend(["", "<b>Что ожидается</b>"])
        for period in periods[:5]:
            lines.extend([format_risk_period(period), ""])
        hidden = max(0, len(periods) - 5)
        if hidden:
            lines.append(f"• Дополнительных периодов: {hidden}.")

        lines.append("<b>Что делать сейчас</b>")
        for action in unique_actions(periods):
            lines.append(f"• {html.escape(action)}")
    else:
        lines.extend(
            [
                "",
                "✅ В текущем принятом запуске ранее отмеченные будущие условия "
                "выше порога больше не подтверждаются.",
                "Продолжайте следить за официальным прогнозом и фактическими "
                "условиями на поле.",
            ]
        )

    resolved_model = events[0].model if events else (outlook.model or "модель не указана")
    lines.extend(
        [
            "",
            "<b>Надёжность</b>",
            f"• Модель: {html.escape(model_label(resolved_model))}; полностью "
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
            "• Сообщение отправлено сразу из-за существенного изменения "
            "высокого модельного сигнала."
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
