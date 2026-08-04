from __future__ import annotations

import html
from datetime import date
from zoneinfo import ZoneInfo

from src.bot.late_blight_moisture_messages import format_compact_night_moisture
from src.domain.late_blight import LateBlightOutlook
from src.domain.late_blight_delivery import (
    InoculumContext,
    LateBlightDeliveryDecision,
    LateBlightEpisodeState,
)

_CONTEXT_LABELS: dict[InoculumContext, str] = {
    "unknown": "источник инфекции не подтверждён",
    "regional_alert_confirmed": "есть подтверждённое региональное сообщение",
    "nearby_outbreak_confirmed": "подтверждён близлежащий очаг",
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
    if not periods:
        return "нет"
    return ", ".join(_date_range(item.start_date, item.end_date) for item in periods)


def _change_lines(decision: LateBlightDeliveryDecision) -> list[str]:
    change = decision.change
    if change is None:
        return []
    previous = change.previous
    current = change.current
    old_text = _periods_text(previous)
    new_text = _periods_text(current)

    if change.kind == "new":
        return [f"Появилось новое погодное окно: <b>{new_text}</b>."]
    if change.kind == "restored":
        return [f"Ранее снятое окно снова подтверждается: <b>{new_text}</b>."]
    if change.kind == "withdrawn":
        return [
            f"Ранее ожидавшееся окно <b>{old_text}</b> больше не "
            "подтверждается прогнозом."
        ]
    if change.kind == "extended" and previous and current:
        return [
            "Погодное окно продлится дольше: до "
            f"<b>{current[0].end_date:%d.%m}</b> вместо "
            f"{previous[0].end_date:%d.%m}."
        ]
    if change.kind == "shortened" and previous and current:
        return [
            "Погодное окно закончится раньше: "
            f"<b>{current[0].end_date:%d.%m}</b> вместо "
            f"{previous[0].end_date:%d.%m}."
        ]
    if change.kind == "starts_earlier" and previous and current:
        return [
            "Погодное окно начнётся раньше: "
            f"<b>{current[0].start_date:%d.%m}</b> вместо "
            f"{previous[0].start_date:%d.%m}."
        ]
    if change.kind == "starts_later" and previous and current:
        return [
            "Погодное окно начнётся позже: "
            f"<b>{current[0].start_date:%d.%m}</b> вместо "
            f"{previous[0].start_date:%d.%m}."
        ]
    if change.kind == "split":
        return [f"Единый период разделился: теперь <b>{new_text}</b>."]
    if change.kind == "merged":
        return [f"Несколько периодов объединились: теперь <b>{new_text}</b>."]
    if change.kind == "context_confirmed":
        return [
            "Для действующего погодного окна появился дополнительный "
            f"контекст: <b>{html.escape(_CONTEXT_LABELS[change.current_context])}</b>."
        ]
    if change.kind == "context_cleared":
        return [
            "Подтверждение источника инфекции снято; остаётся только "
            "погодная благоприятность."
        ]
    if change.kind == "context_changed":
        return [
            "Контекст источника инфекции изменён: "
            f"<b>{html.escape(_CONTEXT_LABELS[change.current_context])}</b>."
        ]
    return [
        f"Границы погодного окна изменились: было {old_text}, "
        f"теперь <b>{new_text}</b>."
    ]


def format_late_blight_change_notification(
    decision: LateBlightDeliveryDecision,
    outlook: LateBlightOutlook,
    *,
    field_name: str,
) -> str:
    lines = [
        "🦠 <b>Фитофтороз картофеля — изменение погодного окна</b>",
        f"🗺 {html.escape(field_name)}",
        "",
        *_change_lines(decision),
    ]
    if decision.current_state.active_periods:
        lines.extend(
            [
                "",
                "<b>Текущее окно</b>",
                *(
                    f"• {_date_range(period.start_date, period.end_date)}"
                    for period in decision.current_state.active_periods
                ),
            ]
        )
        night_context = format_compact_night_moisture(
            outlook,
            periods=decision.current_state.active_periods,
        )
        if night_context is not None:
            lines.extend(["", night_context])

    lines.extend(
        [
            "",
            "<b>Что делать сейчас</b>",
            "• осмотреть нижнюю сторону листьев и водянистые быстро растущие пятна;",
            "• проверить падалицу и места хранения отбракованных клубней;",
            "• сверить региональные сообщения об очагах.",
            "",
            "Критерий Hutton означает два последовательных местных дня с "
            "Tmin не ниже 10 °C и не менее 6 часов RH ≥90 % в каждый день.",
            "Резкий перепад температуры не является отдельным критерием: он "
            "важен лишь когда сопровождается насыщением воздуха, росой, туманом "
            "или другим длительным увлажнением.",
            "Модельные параметры открытого воздуха не равны микроклимату ботвы "
            "или увлажнению листа. Погодное окно не подтверждает наличие "
            "возбудителя, заражение или необходимость обработки.",
        ]
    )
    if decision.current_state.inoculum_context != "unknown":
        lines.append(
            "Дополнительный контекст: "
            + html.escape(
                _CONTEXT_LABELS[decision.current_state.inoculum_context]
            )
            + "."
        )

    retrieved = outlook.retrieved_at.astimezone(ZoneInfo(outlook.timezone))
    timezone_label = retrieved.tzname() or outlook.timezone
    lines.extend(
        [
            "",
            f"Источник: {html.escape(outlook.source)} · "
            f"модель {html.escape(outlook.model)} · "
            f"{retrieved:%d.%m.%Y %H:%M} {html.escape(timezone_label)}.",
        ]
    )
    return "\n".join(lines)
