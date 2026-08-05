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
    """Render only material changes in the recommended scouting date."""

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
    context = (
        f"🗺 {html.escape(field_name)} · "
        f"{html.escape(get_crop_name(crop_key))}"
    )
    stage = html.escape(notification.stage.label)
    previous = _date_label(notification.previous_expected_date)
    current = _date_label(notification.expected_date)
    action = html.escape(notification.stage.scouting_action)

    if notification.change == "earlier":
        heading = (
            f"🐛 <b>Осмотр поля лучше провести раньше: "
            f"{html.escape(model.name_ru)}</b>"
        )
        change_text = (
            f"Окно «{stage}» теперь ожидается около <b>{current}</b>, "
            f"раньше было {previous}."
        )
        action_text = f"Что лучше сделать: {action}"
    elif notification.change == "later":
        heading = (
            f"🐛 <b>Срок осмотра поля сдвинулся: "
            f"{html.escape(model.name_ru)}</b>"
        )
        change_text = (
            f"Окно «{stage}» теперь ожидается около <b>{current}</b>, "
            f"раньше было {previous}."
        )
        action_text = (
            "Срочного осмотра не требуется; ориентируйтесь на новую дату."
        )
    elif notification.change == "withdrawn":
        heading = (
            f"✅ <b>Плановый осмотр пока можно отложить: "
            f"{html.escape(model.name_ru)}</b>"
        )
        change_text = (
            f"Ранее ожидавшееся окно «{stage}» около <b>{previous}</b> "
            "больше не подтверждается температурным прогнозом."
        )
        action_text = "Вернитесь к обычному наблюдению за полем."
    else:
        heading = (
            f"🐛 <b>Окно осмотра снова ожидается: "
            f"{html.escape(model.name_ru)}</b>"
        )
        change_text = (
            f"Окно «{stage}» снова ожидается около <b>{current}</b>."
        )
        action_text = f"Что лучше сделать: {action}"

    return "\n".join(
        [
            heading,
            context,
            "",
            change_text,
            action_text,
            "",
            "Это ориентир для осмотра, а не признак наличия вредителя.",
        ]
    )
