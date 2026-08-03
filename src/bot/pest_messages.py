from __future__ import annotations

import html
from datetime import date

from src.agro.crop_catalog import get_crop_name
from src.domain.pests import PestModel, PestNotification, PestOutlook


def _format_date(value: date | None) -> str:
    return "не определена" if value is None else value.strftime("%d.%m.%Y")


def _method_label(model: PestModel) -> str:
    if model.calculation_method == "daily_average":
        return "среднее суточных минимума и максимума"
    if model.calculation_method == "single_sine_horizontal":
        return "одна синусоида с горизонтальным верхним пределом"
    return model.calculation_method


def _method_explanation(model: PestModel) -> list[str]:
    lower = str(model.lower_threshold_c).replace(".", ",")
    if model.calculation_method == "daily_average":
        lines = [
            "За каждые завершённые местные сутки:",
            f"<code>тепло = max(0, (Tмакс + Tмин) / 2 − {lower})</code>",
        ]
        if model.upper_threshold_c is not None:
            upper = str(model.upper_threshold_c).replace(".", ",")
            lines.append(
                f"Средняя температура предварительно ограничивается {upper} °C."
            )
        return lines

    if model.calculation_method == "single_sine_horizontal":
        upper = (
            "не задан"
            if model.upper_threshold_c is None
            else f"{model.upper_threshold_c:.1f} °C"
        )
        return [
            "Между суточными минимумом и максимумом строится одна условная "
            "синусоида. В расчёт входит площадь температурной кривой выше "
            f"{model.lower_threshold_c:.1f} °C.",
            f"Верхний предел: {upper}; тепло выше него не ускоряет развитие.",
            "Это метод Single Sine с горизонтальным отсечением, а не простое "
            "вычитание базовой температуры из среднего значения.",
        ]

    return ["Метод модели не поддерживается пользовательской справкой."]


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
                "Для этой культуры пока нет допущенной погодозависимой модели.",
                "",
                "Бот не связывает культуру с вредителем только потому, что он "
                "может на ней встречаться. Нужны точный вид, температурный или "
                "погодный метод, точка отсчёта, опубликованные пороги и понятные "
                "границы применимости.",
            ]
        )
        return "\n".join(lines)

    lines.append("Доступные расчёты:")
    for model in models:
        marker = "✅ включено" if model.key == active_pest_key else "не настроено"
        driver = (
            "температура почвы"
            if model.temperature_driver == "soil_0_to_7cm"
            else "температура воздуха"
        )
        lines.append(
            f"• {html.escape(model.name_ru)} "
            f"(<i>{html.escape(model.scientific_name)}</i>) — {marker}; {driver}."
        )
    lines.extend(
        [
            "",
            "Наблюдаемая точка отсчёта вводится пользователем. Календарная "
            "точка используется только там, где она прямо задана опубликованной "
            "моделью.",
            "",
            "Расчёт показывает окно обследования. Он не подтверждает наличие, "
            "численность, ущерб или необходимость обработки.",
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
        f"🌡 Данные: {html.escape(model.temperature_label)}",
    ]
    if biofix_date is not None:
        lines.append(
            f"📅 Точка отсчёта: {html.escape(model.biofix_label)}, "
            f"{_format_date(biofix_date)}"
        )
    lines.extend(["", html.escape(model.biofix_help)])
    if model.biofix_mode == "calendar":
        lines.append(
            "Календарная дата задаётся самой опубликованной моделью и "
            "обновляется для нового года."
        )
    else:
        lines.append(
            "Без этого полевого наблюдения бот не запускает расчёт по одной погоде."
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
        f"🌡 Используется: {html.escape(model.temperature_label)}",
        "",
    ]
    if not outlook.available:
        lines.extend(
            [
                "⚠️ <b>Расчёт не показан</b>",
                f"• {html.escape(outlook.status)}.",
                "• Пропуск не заменяется нулём. Проверьте точку отсчёта или "
                "повторите расчёт после обновления температурного ряда.",
            ]
        )
        return "\n".join(lines)

    assert outlook.current_stage is not None
    assert outlook.accumulated_dd_c is not None
    threshold_text = f"выше {model.lower_threshold_c:.1f} °C"
    if model.upper_threshold_c is not None:
        threshold_text += f", с верхним пределом {model.upper_threshold_c:.1f} °C"
    lines.extend(
        [
            "<b>Что показывает температурная модель</b>",
            f"• Накоплено: <b>{outlook.accumulated_dd_c:.1f} °C·сут</b> "
            f"({threshold_text}).",
            f"• Расчётное окно: <b>{html.escape(outlook.current_stage.label)}</b>.",
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
                float(outlook.next_stage.start_dd_c) - outlook.accumulated_dd_c,
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
            f"• Метод: {html.escape(_method_label(model))}.",
            f"• Версия правила: {html.escape(model.model_version)}.",
            "• Это расчёт скорости развития от заданной точки отсчёта, а не "
            "прогноз наличия, численности, ущерба или необходимости обработки.",
            "• Решение принимают после осмотра, учёта местного порога вреда и "
            "проверки действующих правил применения средств защиты растений.",
        ]
    )
    return "\n".join(lines)


def format_pest_help(model: PestModel) -> str:
    stage_lines: list[str] = []
    for stage in model.stages:
        end = "далее" if stage.end_dd_c is None else f"{stage.end_dd_c:.1f}"
        stage_lines.append(
            f"• {stage.start_dd_c:.1f}–{end} °C·сут: "
            f"{html.escape(stage.label)}"
        )

    return "\n".join(
        [
            f"ℹ️ <b>Как считается {html.escape(model.name_ru)}</b>",
            "",
            f"Точка отсчёта: <b>{html.escape(model.biofix_label)}</b>.",
            html.escape(model.biofix_help),
            f"Температурный ряд: <b>{html.escape(model.temperature_label)}</b>.",
            f"Нижний порог: <b>{model.lower_threshold_c:.1f} °C</b>.",
            *(
                [f"Верхний порог: <b>{model.upper_threshold_c:.1f} °C</b>."]
                if model.upper_threshold_c is not None
                else []
            ),
            "",
            *_method_explanation(model),
            "Будущий прогноз показывается отдельно и не входит в уже "
            "накопленное значение.",
            "",
            "<b>Опубликованные расчётные окна</b>",
            *stage_lines,
            "",
            f"Основной источник: {html.escape(model.source_title)}.",
            html.escape(model.validation_note),
            "",
            "Модель помогает выбрать время обследования. Она не заменяет "
            "определение вида, фактический учёт и экономический порог "
            "вредоносности. Бот не назначает препарат, срок обработки или дозу.",
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
            "По текущему температурному прогнозу около "
            f"<b>{_format_date(notification.expected_date)}</b> ожидается вход "
            f"в расчётное окно «{html.escape(notification.stage.label)}»."
        )
    else:
        lines.append(
            "Накопленная температура вошла в расчётное окно "
            f"«{html.escape(notification.stage.label)}»."
        )
    lines.extend(
        [
            "",
            f"Что сделать: {html.escape(notification.stage.scouting_action)}",
            "",
            "Это напоминание об обследовании, а не команда на обработку. "
            "Наличие, численность и необходимость мер подтверждаются на поле.",
        ]
    )
    return "\n".join(lines)
