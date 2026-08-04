from __future__ import annotations

import html
from datetime import date
from zoneinfo import ZoneInfo

from src.bot.late_blight_moisture_messages import format_night_moisture_section
from src.domain.late_blight import LateBlightDayAssessment, LateBlightOutlook


def _date_range(start: date, end: date) -> str:
    if start == end:
        return start.strftime("%d.%m")
    if start.year == end.year:
        return f"{start:%d.%m}–{end:%d.%m}"
    return f"{start:%d.%m.%Y}–{end:%d.%m.%Y}"


def _period_kind(value: str) -> str:
    return {
        "model_completed": "завершённые модельные сутки",
        "forecast": "прогноз",
        "mixed": "завершённые сутки и прогноз",
    }.get(value, value)


def _day_line(day: LateBlightDayAssessment) -> str:
    if not day.complete:
        return (
            f"• {day.local_date:%d.%m}: неполный ряд "
            f"({day.valid_hours}/{day.expected_hours} ч)"
        )
    marker = "✅" if day.qualifies else "—"
    minimum = (
        "нет"
        if day.minimum_temperature_c is None
        else f"{day.minimum_temperature_c:.1f} °C"
    )
    return (
        f"• {marker} {day.local_date:%d.%m}: Tmin {minimum}; "
        f"RH ≥90 % — {day.humid_hours} ч"
    )


def _diagnostic_days(outlook: LateBlightOutlook) -> tuple[LateBlightDayAssessment, ...]:
    complete = [day for day in outlook.days if day.complete]
    if len(complete) <= 6:
        return tuple(complete)
    qualifying = [day for day in complete if day.qualifies]
    selected = qualifying[-4:] + complete[-2:]
    unique: dict[date, LateBlightDayAssessment] = {
        day.local_date: day for day in selected
    }
    return tuple(unique[key] for key in sorted(unique))


def format_potato_late_blight_screening(
    outlook: LateBlightOutlook,
    *,
    field_name: str,
) -> str:
    lines = [
        "🦠 <b>Фитофтороз картофеля — погодное окно</b>",
        f"🗺 {html.escape(field_name)}",
        "",
    ]

    if not outlook.available:
        lines.extend(
            [
                "⚠️ <b>Расчёт не показан</b>",
                f"• {html.escape(outlook.status)}.",
                "• Пропуски не заменяются сухой погодой или нулевой влажностью.",
            ]
        )
    elif outlook.periods:
        lines.append(
            "⚠️ <b>Условия по критериям Hutton выполнены</b>"
        )
        for period in outlook.periods[:4]:
            lines.append(
                f"• {_date_range(period.start_date, period.end_date)} — "
                f"{html.escape(_period_kind(period.data_kind))}, "
                f"{period.day_count} сут."
            )
    elif any(day.qualifies for day in outlook.days):
        lines.extend(
            [
                "🟡 <b>Есть отдельные благоприятные сутки</b>",
                "Для предупреждения Hutton нужны два последовательных дня; "
                "сейчас это условие не выполнено.",
            ]
        )
    else:
        lines.extend(
            [
                "🟢 <b>Критерии Hutton в доступном окне не выполнены</b>",
                "Это не исключает уже существующую инфекцию или локальный очаг.",
            ]
        )

    diagnostic_days = _diagnostic_days(outlook)
    if diagnostic_days:
        lines.extend(["", "<b>Проверка по суткам</b>"])
        lines.extend(_day_line(day) for day in diagnostic_days)

    lines.extend(format_night_moisture_section(outlook))

    local_retrieved = outlook.retrieved_at.astimezone(ZoneInfo(outlook.timezone))
    timezone_label = local_retrieved.tzname() or outlook.timezone
    lines.extend(
        [
            "",
            "<b>Что означает критерий</b>",
            "Два последовательных местных дня, в каждый из которых Tmin не "
            "ниже 10 °C и не менее 6 часов RH ≥90 %.",
            "",
            "<b>Что проверить сейчас</b>",
            "• региональные сообщения об очагах и заражённом посадочном материале;",
            "• нижнюю сторону листьев и быстро увеличивающиеся водянистые пятна;",
            "• падалицу картофеля и места хранения отбракованных клубней.",
            "",
            "⚠️ Температура, RH, точка росы, видимость и осадки взяты из "
            "модельной сетки для открытого воздуха. Это не микроклимат внутри "
            "ботвы и не измерение увлажнения листа.",
            "Благоприятная погода без источника инфекции не доказывает заражение. "
            "Бот не назначает препарат, срок или дозу обработки.",
            "",
            f"Источник данных: {html.escape(outlook.source)} · "
            f"модель {html.escape(outlook.model)} · "
            f"{local_retrieved:%d.%m.%Y %H:%M} {html.escape(timezone_label)}.",
        ]
    )
    return "\n".join(lines)
