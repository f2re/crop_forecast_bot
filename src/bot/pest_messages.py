from __future__ import annotations

import html
from datetime import date

from src.agro.crop_catalog import get_crop_name
from src.domain.pests import PestModel, PestNotification, PestOutlook


def _format_date(value: date | None) -> str:
    return "не определена" if value is None else value.strftime("%d.%m.%Y")


def format_pest_overview(
    *,
    field_name: str,
    crop_key: str,
    models: tuple[PestModel, ...],
    active_pest_key: str | None,
) -> str:
    crop_name = html.escape(get_crop_name(crop_key))
    lines = [
        "🐛 <b>Наблюдение за вредителями</b>",
        f"🗺 Поле: {html.escape(field_name)}",
        f"🌱 Выбранная культура: <b>{crop_name}</b>",
        "",
    ]
    if not models:
        lines.extend(
            [
                "Для этой культуры пока нет включённой и проверяемой модели.",
                "",
                "Бот не переносит температурные пороги от другой культуры или "
                "другого вида вредителя. Сначала нужны точный вид, исходное "
                "наблюдение, метод расчёта и региональная проверка.",
            ]
        )
        return "\n".join(lines)

    lines.append("Доступно:")
    for model in models:
        marker = "✅ настроено" if model.key == active_pest_key else "не настроено"
        lines.append(
            f"• {html.escape(model.name_ru)} "
            f"(<i>{html.escape(model.scientific_name)}</i>) — {marker}."
        )
    lines.extend(
        [
            "",
            "Сначала пользователь отмечает реальную находку на поле. После "
            "этого бот считает только температурное развитие и напоминает, "
            "когда полезно повторить осмотр.",
            "",
            "Расчёт не подтверждает наличие вредителя, численность, ущерб или "
            "необходимость обработки.",
        ]
    )
    return "\n".join(lines)


def format_pest_model_intro(
    model: PestModel,
    *,
    field_name: str,
    crop_key: str,
    configured: bool,
    enabled: bool,
    biofix_date: date | None,
) -> str:
    status = (
        "включено"
        if configured and enabled
        else "выключено" if configured else "не настроено"
    )
    lines = [
        f"🐛 <b>{html.escape(model.name_ru)}</b>",
        f"🗺 Поле: {html.escape(field_name)}",
        f"🌱 Культура: {html.escape(get_crop_name(crop_key))}",
        f"🔔 Наблюдение: {status}",
    ]
    if biofix_date is not None:
        lines.append(
            f"📅 Точка отсчёта: {html.escape(model.biofix_label)}, "
            f"{_format_date(biofix_date)}"
        )
    lines.extend(
        [
            "",
            "Чтобы начать расчёт, отметьте дату первой реально найденной "
            "кладки яиц. Без этой находки бот не пытается угадать появление "
            "вредителя по одной погоде.",
        ]
    )
    return "\n".join(lines)


def format_pest_outlook(
    outlook: PestOutlook,
    *,
    field_name: str,
    crop_key: str,
    source: str,
) -> str:
    model = outlook.model
    lines = [
        f"🐛 <b>{html.escape(model.name_ru)} — окно осмотра</b>",
        f"🗺 Поле: {html.escape(field_name)}",
        f"🌱 Культура: {html.escape(get_crop_name(crop_key))}",
        f"📅 Отсчёт от: {html.escape(model.biofix_label)}, "
        f"{_format_date(outlook.biofix_date)}",
        "",
    ]
    if not outlook.available:
        lines.extend(
            [
                "⚠️ <b>Расчёт не показан</b>",
                f"• {html.escape(outlook.status)}.",
                "• Пропуск не заменяется нулём. Проверьте дату или повторите "
                "расчёт после обновления погодного ряда.",
            ]
        )
        return "\n".join(lines)

    assert outlook.current_stage is not None
    lines.extend(
        [
            "<b>Что показывает температура</b>",
            f"• Накоплено: <b>{outlook.accumulated_dd_c:.1f} °C·сут</b> "
            f"выше {model.lower_threshold_c:.1f} °C.",
            f"• Текущее расчётное окно: <b>{html.escape(outlook.current_stage.label)}</b>.",
            f"• Что проверить: {html.escape(outlook.current_stage.scouting_action)}",
        ]
    )
    if outlook.next_stage is not None:
        if outlook.projected_crossing_date is not None:
            lines.append(
                f"• Следующее окно — «{html.escape(outlook.next_stage.label)}»; "
                f"по текущему температурному прогнозу ориентировочно "
                f"{_format_date(outlook.projected_crossing_date)}."
            )
        else:
            remaining = max(
                0.0,
                float(outlook.next_stage.start_dd_c)
                - float(outlook.accumulated_dd_c or 0.0),
            )
            lines.append(
                f"• До следующего окна по шкале модели остаётся около "
                f"{remaining:.1f} °C·сут; ближайший прогноз порог не достигает."
            )
    lines.extend(
        [
            "",
            "<b>Надёжность и границы</b>",
            f"• Завершённый ряд: {outlook.completed_days} сут.; "
            f"пропусков: {outlook.missing_days}.",
            f"• Источник температуры: {html.escape(source)}.",
            f"• Версия правила: {html.escape(model.model_version)}.",
            "• Это расчёт скорости развития после подтверждённой находки, а "
            "не прогноз появления, численности, ущерба или необходимости "
            "обработки.",
            "• Решение принимают после осмотра, учёта местного порога вреда и "
            "проверки действующих правил применения средств защиты растений.",
        ]
    )
    return "\n".join(lines)


def format_pest_help(model: PestModel) -> str:
    stage_lines = [
        f"• {stage.start_dd_c:.0f}–"
        f"{stage.end_dd_c:.0f if stage.end_dd_c is not None else 'далее'} °C·сут: "
        f"{html.escape(stage.label)}"
        for stage in model.stages
    ]
    # Python's conditional formatting syntax is deliberately avoided below to
    # keep the generated text compatible with Python 3.10.
    stage_lines = []
    for stage in model.stages:
        end = "далее" if stage.end_dd_c is None else f"{stage.end_dd_c:.0f}"
        stage_lines.append(
            f"• {stage.start_dd_c:.0f}–{end} °C·сут: "
            f"{html.escape(stage.label)}"
        )

    return "\n".join(
        [
            f"ℹ️ <b>Как считается {html.escape(model.name_ru)}</b>",
            "",
            f"Точка отсчёта: <b>{html.escape(model.biofix_label)}</b>.",
            f"Нижний температурный порог: <b>{model.lower_threshold_c:.1f} °C</b>.",
            "За каждые завершённые местные сутки:",
            "<code>тепло = max(0, (Tмакс + Tмин) / 2 − 11,1)</code>",
            "Затем суточные значения складываются. Будущий прогноз показывается "
            "отдельно и не входит в уже накопленное значение.",
            "",
            "<b>Опубликованные окна после первой кладки</b>",
            *stage_lines,
            "",
            f"Источник: {html.escape(model.source_title)}.",
            html.escape(model.validation_note),
            "",
            "Модель помогает выбрать время повторного осмотра. Она не заменяет "
            "учёт вредителя и экономический порог вредоносности. Бот не "
            "назначает препарат, срок обработки или дозу.",
        ]
    )


def format_pest_notification(
    notification: PestNotification,
    outlook: PestOutlook,
    *,
    field_name: str,
    crop_key: str,
) -> str:
    model = outlook.model
    lines = [
        f"🐛 <b>Пора проверить поле: {html.escape(model.name_ru)}</b>",
        f"🗺 {html.escape(field_name)} · {html.escape(get_crop_name(crop_key))}",
        "",
    ]
    if notification.kind == "approaching_window":
        lines.append(
            f"По текущему температурному прогнозу около "
            f"<b>{_format_date(notification.expected_date)}</b> ожидается вход "
            f"в расчётное окно «{html.escape(notification.stage.label)}»."
        )
    else:
        lines.append(
            f"Накопленная температура вошла в расчётное окно "
            f"«{html.escape(notification.stage.label)}»."
        )
    lines.extend(
        [
            "",
            f"Что сделать: {html.escape(notification.stage.scouting_action)}",
            "",
            "Это напоминание об осмотре, а не команда на обработку. Наличие, "
            "численность и необходимость мер подтверждаются на поле.",
        ]
    )
    return "\n".join(lines)
