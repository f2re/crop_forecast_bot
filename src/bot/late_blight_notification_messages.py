from __future__ import annotations

import html
from datetime import date

from src.domain.late_blight import LateBlightOutlook
from src.domain.late_blight_delivery import (
    InoculumContext,
    LateBlightDeliveryDecision,
    LateBlightEpisodeState,
)

_CONTEXT_LABELS: dict[InoculumContext, str] = {
    "unknown": "источник инфекции не подтверждён",
    "regional_alert_confirmed": "есть указанное региональное сообщение",
    "nearby_outbreak_confirmed": "рядом указан подтверждённый очаг",
    "field_source_suspected": "на поле отмечен возможный источник инфекции",
    "field_symptoms_observed": "на поле отмечены подозрительные симптомы",
}


def _date_range(start: date, end: date) -> str:
    if start == end:
        return start.strftime("%d.%m")
    if start.year == end.year:
        return f"{start:%d.%m}–{end:%d.%m}"
    return f"{start:%d.%m.%Y}–{end:%d.%m.%Y}"


def _periods_text(periods: tuple[LateBlightEpisodeState, ...]) -> str:
    return ", ".join(
        _date_range(item.start_date, item.end_date) for item in periods
    )


def _change_text(decision: LateBlightDeliveryDecision) -> str:
    change = decision.change
    if change is None:
        return ""
    previous = change.previous
    current = change.current
    old_text = _periods_text(previous)
    new_text = _periods_text(current)

    if change.kind == "new":
        return f"Погодное окно ожидается <b>{new_text}</b>."
    if change.kind == "restored":
        return f"Ранее снятое погодное окно снова ожидается: <b>{new_text}</b>."
    if change.kind == "withdrawn":
        return (
            f"Ранее ожидавшееся окно <b>{old_text}</b> больше не "
            "подтверждается прогнозом."
        )
    if change.kind == "extended" and previous and current:
        return (
            "Период может продлиться до "
            f"<b>{current[0].end_date:%d.%m}</b> "
            f"(ранее — до {previous[0].end_date:%d.%m})."
        )
    if change.kind == "shortened" and previous and current:
        return (
            "Период может закончиться "
            f"<b>{current[0].end_date:%d.%m}</b> "
            f"(ранее — {previous[0].end_date:%d.%m})."
        )
    if change.kind == "starts_earlier" and previous and current:
        return (
            "Условия могут начаться раньше: "
            f"<b>{current[0].start_date:%d.%m}</b> "
            f"вместо {previous[0].start_date:%d.%m}."
        )
    if change.kind == "starts_later" and previous and current:
        return (
            "Условия ожидаются позже: "
            f"<b>{current[0].start_date:%d.%m}</b> "
            f"вместо {previous[0].start_date:%d.%m}."
        )
    if change.kind == "context_confirmed":
        return (
            "К погодному окну добавлен важный контекст: "
            f"<b>{html.escape(_CONTEXT_LABELS[change.current_context])}</b>."
        )
    if change.kind == "context_cleared":
        return "Указанный источник инфекции снят; остаётся только погодный фактор."
    if change.kind == "context_changed":
        return (
            "Контекст поля уточнён: "
            f"<b>{html.escape(_CONTEXT_LABELS[change.current_context])}</b>."
        )
    return f"Погодное окно уточнилось: теперь <b>{new_text}</b>."


def format_late_blight_change_notification(
    decision: LateBlightDeliveryDecision,
    outlook: LateBlightOutlook,
    *,
    field_name: str,
) -> str:
    del outlook
    change = decision.change
    withdrawn = change is not None and change.kind == "withdrawn"

    if withdrawn:
        lines = [
            "✅ <b>Погодное окно фитофтороза больше не ожидается</b>",
            f"🗺 {html.escape(field_name)}",
            "",
            _change_text(decision),
            "Специальный осмотр по этому прогнозу пока не нужен.",
        ]
    else:
        context = decision.current_state.inoculum_context
        heading = (
            "🟠 <b>Фитофтороз картофеля: проверьте поле</b>"
            if context != "unknown"
            else "🦠 <b>Погода благоприятна для фитофтороза картофеля</b>"
        )
        lines = [
            heading,
            f"🗺 {html.escape(field_name)}",
            "",
            _change_text(decision),
            "Что сделать: осмотрите нижние листья и возможные источники инфекции.",
        ]
        if context == "unknown":
            lines.append(
                "Это только погодные условия: наличие инфекции не подтверждено."
            )
        else:
            lines.append(
                "Контекст указан пользователем; диагноз всё равно нужно подтвердить."
            )

    text = "\n".join(line for line in lines if line)
    if len(text) > 1200:
        raise ValueError("Late-blight notification is unexpectedly long")
    return text
