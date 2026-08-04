from __future__ import annotations

import html
from datetime import date

from src.bot.risk_language import (
    crop_context_lines,
    format_risk_period,
    group_risk_events,
)
from src.domain.risk import RiskEvent, RiskOutlook, RiskType
from src.domain.risk_delivery import RiskEpisodeState, RiskStateChange

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
    return period


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
            f"• {emoji} <b>{name}</b>: период "
            f"{html.escape(_episodes_label(previous))} больше не подтверждается."
        )

    if len(previous) == 1 and len(current) == 1:
        old = previous[0]
        new = current[0]
        details: list[str] = []
        if new.start_date < old.start_date:
            details.append(
                f"раньше: {_date_label(new.start_date)} вместо {_date_label(old.start_date)}"
            )
        elif new.start_date > old.start_date:
            details.append(
                f"позже: {_date_label(new.start_date)} вместо {_date_label(old.start_date)}"
            )
        if new.end_date < old.end_date:
            details.append(
                f"закончится {_date_label(new.end_date)} вместо {_date_label(old.end_date)}"
            )
        elif new.end_date > old.end_date:
            details.append(
                f"продлится до {_date_label(new.end_date)} вместо {_date_label(old.end_date)}"
            )
        if new.highest_level != old.highest_level:
            details.append("уровень сигнала изменился")
        if details:
            return f"• {emoji} <b>{name}</b>: {html.escape('; '.join(details))}."

    return (
        f"• {emoji} <b>{name}</b>: было "
        f"{html.escape(_episodes_label(previous))}; теперь "
        f"{html.escape(_episodes_label(current))}."
    )


def _header(field_name: str) -> list[str]:
    return [
        f"⚠️ <b>Погода: {html.escape(field_name)}</b>",
    ]


def format_ensemble_risk_alert(
    event: RiskEvent,
    outlook: RiskOutlook,
    *,
    field_name: str,
    crop: str | None = None,
    crops: tuple[str, ...] = (),
    phase: str | None = None,
) -> str:
    del outlook
    period = group_risk_events((event,))[0]
    lines = _header(field_name)
    lines.extend(
        crop_context_lines(
            crops=crops,
            selected_crop=crop,
            phase=phase,
        )
    )
    lines.extend(["", format_risk_period(period)])

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
    del outlook, delivery_mode, priority_bypass
    if not events and not changes:
        raise ValueError("Risk digest requires events or a semantic change")

    periods = group_risk_events(events)
    lines = _header(field_name)
    lines.extend(
        crop_context_lines(
            crops=crops,
            selected_crop=crop,
            phase=phase,
        )
    )

    if changes:
        lines.extend(["", "<b>Изменение прогноза</b>"])
        lines.extend(_format_change(change) for change in changes)

    if periods:
        lines.append("")
        for index, period in enumerate(periods[:5]):
            if index:
                lines.append("")
            lines.append(format_risk_period(period))
        hidden = max(0, len(periods) - 5)
        if hidden:
            lines.append(f"\nЕщё периодов: {hidden}.")
    else:
        lines.extend(
            [
                "",
                "🟢 <b>Ранее отмеченные риски больше не подтверждаются.</b>",
                "Действие: вернитесь к обычному контролю поля.",
            ]
        )

    text = "\n".join(lines)
    if len(text) > 4096:
        raise ValueError("Risk digest exceeds Telegram message limit")
    return text


def format_ensemble_data_unavailable(field_name: str, reason: str) -> str:
    return (
        "⚪ <b>Погодные риски не рассчитаны</b>\n"
        f"🗺 {html.escape(field_name)}\n"
        f"Причина: {html.escape(reason)}.\n"
        "Действие: проверьте официальный прогноз; бот повторит расчёт после обновления данных."
    )
