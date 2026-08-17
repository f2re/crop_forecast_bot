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

_NOTIFICATION_DISPLAY_LEAD_DAYS = 3
_RISK_NAMES: dict[RiskType, tuple[str, str]] = {
    "frost": ("🌡", "похолодание к нулю"),
    "heat": ("🔥", "жара"),
    "heavy_rain": ("🌧", "сильный дождь"),
    "strong_wind": ("💨", "сильный ветер"),
    "convection": ("⛈", "условия для грозовых облаков"),
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


def _visible_events(events: tuple[RiskEvent, ...]) -> tuple[RiskEvent, ...]:
    return tuple(
        event
        for event in events
        if 0 <= event.lead_days <= _NOTIFICATION_DISPLAY_LEAD_DAYS
    )


def _is_urgent(events: tuple[RiskEvent, ...]) -> bool:
    return any(
        event.level == "high" and 0 <= event.lead_days <= 1
        for event in events
    )


def _format_change(change: RiskStateChange) -> str:
    emoji, name = _RISK_NAMES[change.risk_type]
    previous = change.previous
    current = change.current

    if not previous:
        return f"• {emoji} Появился новый период, к которому нужно подготовиться."
    if not current:
        return (
            f"• {emoji} Ранее ожидавшиеся условия «{html.escape(name)}» "
            "больше не ожидаются."
        )

    if len(previous) == 1 and len(current) == 1:
        old = previous[0]
        new = current[0]
        details: list[str] = []
        if new.highest_level != old.highest_level:
            if new.highest_level == "high":
                details.append("условия стали выраженнее")
            elif old.highest_level == "high":
                details.append("условия стали слабее")
            else:
                details.append("оценка изменилась")
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

    return f"• {emoji} Прогноз для условий «{html.escape(name)}» заметно изменился."


def _header(
    field_name: str,
    *,
    improved: bool = False,
    urgent: bool = False,
) -> list[str]:
    if improved:
        return [f"✅ <b>Прогноз улучшился: {html.escape(field_name)}</b>"]
    if urgent:
        return [f"⚠️ <b>Важно на ближайшие сутки: {html.escape(field_name)}</b>"]
    return [f"🌤 <b>Погода: {html.escape(field_name)}</b>"]


def _append_periods(
    lines: list[str],
    events: tuple[RiskEvent, ...],
) -> None:
    visible = _visible_events(events)
    periods = group_risk_events(visible)
    if not periods:
        return

    hidden_future = any(
        event.lead_days > _NOTIFICATION_DISPLAY_LEAD_DAYS for event in events
    )
    if hidden_future:
        lines.extend(["", "<b>Ближайшие 3 суток</b>"])
    else:
        lines.append("")

    for index, period in enumerate(periods[:5]):
        if index:
            lines.append("")
        lines.append(format_risk_period(period))


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
    events = (event,)
    lines = _header(field_name, urgent=_is_urgent(events))
    lines.extend(
        crop_context_lines(
            crops=crops,
            selected_crop=crop,
            phase=phase,
        )
    )
    _append_periods(lines, events)

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

    visible_events = _visible_events(events)
    visible_periods = group_risk_events(visible_events)
    improved = not visible_periods and _all_withdrawn(changes)
    lines = _header(
        field_name,
        improved=improved,
        urgent=_is_urgent(visible_events),
    )
    lines.extend(
        crop_context_lines(
            crops=crops,
            selected_crop=crop,
            phase=phase,
        )
    )

    # A first confirmed warning already explains itself in the risk card. A
    # separate "what changed" block only adds stress and duplicates dates.
    update_changes = tuple(change for change in changes if change.previous)
    if update_changes:
        lines.extend(["", "<b>Что изменилось</b>"])
        lines.extend(_format_change(change) for change in update_changes)

    if visible_periods:
        _append_periods(lines, events)
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
