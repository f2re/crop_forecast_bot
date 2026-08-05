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
    "frost": ("🌡", "опасное похолодание"),
    "heat": ("🔥", "жара"),
    "heavy_rain": ("🌧", "сильный дождь"),
    "strong_wind": ("💨", "сильный ветер"),
    "convection": ("⛈", "грозовые условия"),
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
        return _date_label(episode.start_date)
    if episode.start_date.month == episode.end_date.month:
        return (
            f"{episode.start_date.day}–{episode.end_date.day} "
            f"{_MONTHS[episode.start_date.month]}"
        )
    return f"{_date_label(episode.start_date)} — {_date_label(episode.end_date)}"


def _episodes_label(episodes: tuple[RiskEpisodeState, ...]) -> str:
    return "; ".join(_episode_label(episode) for episode in episodes)


def _all_withdrawn(changes: tuple[RiskStateChange, ...]) -> bool:
    return bool(changes) and all(
        change.previous and not change.current for change in changes
    )


def _format_change(change: RiskStateChange) -> str:
    emoji, name = _RISK_NAMES[change.risk_type]
    previous = change.previous
    current = change.current

    if not previous:
        return (
            f"• {emoji} Появился новый период: "
            f"<b>{html.escape(_episodes_label(current))}</b>."
        )
    if not current:
        return (
            f"• {emoji} Ранее ожидавшиеся условия «{html.escape(name)}» "
            f"на {html.escape(_episodes_label(previous))} больше не ожидаются."
        )

    if len(previous) == 1 and len(current) == 1:
        old = previous[0]
        new = current[0]
        details: list[str] = []
        if new.highest_level != old.highest_level:
            if new.highest_level == "high":
                details.append("сигнал усилился")
            elif old.highest_level == "high":
                details.append("сигнал ослаб")
            else:
                details.append("уровень изменился")
        if new.start_date < old.start_date:
            details.append(
                f"начало раньше: {_date_label(new.start_date)} "
                f"вместо {_date_label(old.start_date)}"
            )
        elif new.start_date > old.start_date:
            details.append(
                f"начало позже: {_date_label(new.start_date)} "
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
        if details:
            return (
                f"• {emoji} {html.escape(name.capitalize())}: "
                + html.escape("; ".join(details))
                + "."
            )

    return (
        f"• {emoji} Период «{html.escape(name)}» заметно изменился: "
        f"было {html.escape(_episodes_label(previous))}, "
        f"теперь <b>{html.escape(_episodes_label(current))}</b>."
    )


def _header(field_name: str, *, improved: bool = False) -> list[str]:
    icon = "✅" if improved else "⚠️"
    title = "Прогноз улучшился" if improved else "Погода требует внимания"
    return [f"{icon} <b>{title}: {html.escape(field_name)}</b>"]


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
    improved = not periods and _all_withdrawn(changes)
    lines = _header(field_name, improved=improved)
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

    if periods:
        lines.append("")
        for index, period in enumerate(periods[:5]):
            if index:
                lines.append("")
            lines.append(format_risk_period(period))
        hidden = max(0, len(periods) - 5)
        if hidden:
            lines.append(f"\nЕщё периодов: {hidden}.")
    elif improved:
        lines.extend(
            [
                "",
                "Можно вернуться к обычному контролю поля.",
            ]
        )

    text = "\n".join(lines)
    if len(text) > 4096:
        raise ValueError("Risk digest exceeds Telegram message limit")
    return text


def format_ensemble_data_unavailable(field_name: str, reason: str) -> str:
    return (
        "⚪ <b>Погодные риски пока не рассчитаны</b>\n"
        f"🗺 {html.escape(field_name)}\n"
        f"Причина: {html.escape(reason)}.\n"
        "Бот повторит проверку после обновления данных."
    )
