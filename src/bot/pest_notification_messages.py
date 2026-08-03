from __future__ import annotations

import html
from datetime import date

from src.agro.crop_catalog import get_crop_name
from src.application.pest_notification_policy import SemanticPestNotification
from src.bot.pest_messages import format_pest_notification
from src.domain.pests import PestNotification, PestOutlook


def _date_label(value: date | None) -> str:
    return "не определена" if value is None else value.strftime("%d.%m.%Y")


def format_semantic_pest_notification(
    notification: PestNotification,
    outlook: PestOutlook,
    *,
    field_name: str,
    crop_key: str,
) -> str:
    """Render explicit forecast-window changes while preserving old messages."""

    if not isinstance(notification, SemanticPestNotification):
        return format_pest_notification(
            notification,
            outlook,
            field_name=field_name,
            crop_key=crop_key,
        )
    if notification.change in {None, "initial"}:
        return format_pest_notification(
            notification,
            outlook,
            field_name=field_name,
            crop_key=crop_key,
        )

    model = outlook.model
    heading = (
        f"🐛 <b>Уточнение окна осмотра: {html.escape(model.name_ru)}</b>"
    )
    context = (
        f"🗺 {html.escape(field_name)} · "
        f"{html.escape(get_crop_name(crop_key))}"
    )
    stage = html.escape(notification.stage.label)
    previous = _date_label(notification.previous_expected_date)
    current = _date_label(notification.expected_date)

    if notification.change == "earlier":
        change_text = (
            f"Расчётное окно «{stage}» ожидается раньше: "
            f"<b>{current}</b> вместо {previous}."
        )
    elif notification.change == "later":
        change_text = (
            f"Расчётное окно «{stage}» ожидается позже: "
            f"<b>{current}</b> вместо {previous}."
        )
    elif notification.change == "withdrawn":
        change_text = (
            f"Ранее ожидавшийся вход в окно «{stage}» около "
            f"<b>{previous}</b> больше не подтверждается текущим "
            "температурным прогнозом."
        )
    else:
        change_text = (
            f"После предыдущего снятия окно «{stage}» снова подтверждается. "
            f"Новая ориентировочная дата: <b>{current}</b>."
        )

    return "\n".join(
        [
            heading,
            context,
            "",
            change_text,
            "",
            f"Что сделать: {html.escape(notification.stage.scouting_action)}",
            "",
            "Это уточнение времени обследования, а не доказательство наличия "
            "вредителя и не команда на обработку. Проверьте вид, численность и "
            "повреждение непосредственно на поле.",
        ]
    )
