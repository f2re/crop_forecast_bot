from __future__ import annotations

import calendar
from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_MONTHS_RU = (
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)
_WEEKDAYS_RU = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
_NOOP = "pest_calendar:noop"
_MAX_AGE_DAYS = 365


def _shift_month(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(absolute, 12)
    return date(year, month_index + 1, 1)


def oldest_allowed_biofix(today: date) -> date:
    return today - timedelta(days=_MAX_AGE_DAYS)


def validate_biofix_date(value: date, *, today: date) -> date:
    oldest = oldest_allowed_biofix(today)
    if value > today:
        raise ValueError("Дата первой находки не может быть в будущем.")
    if value < oldest:
        raise ValueError(
            "Для наблюдения выберите дату не старше 365 суток. "
            "Старый цикл следует начать заново по свежей находке."
        )
    return value


def _month_available(month: date, *, today: date) -> bool:
    oldest = oldest_allowed_biofix(today)
    first = date(oldest.year, oldest.month, 1)
    current = date(today.year, today.month, 1)
    return first <= month <= current


def _nav_button(label: str, target: date, *, today: date) -> InlineKeyboardButton:
    callback = (
        f"pest_calendar:nav:{target.isoformat()}"
        if _month_available(target, today=today)
        else _NOOP
    )
    return InlineKeyboardButton(text=label, callback_data=callback)


def build_pest_calendar(
    display_month: date,
    *,
    today: date,
    selected: date | None = None,
) -> InlineKeyboardMarkup:
    month = date(display_month.year, display_month.month, 1)
    if not _month_available(month, today=today):
        month = date(today.year, today.month, 1)
    oldest = oldest_allowed_biofix(today)

    rows: list[list[InlineKeyboardButton]] = [
        [
            _nav_button("« год", _shift_month(month, -12), today=today),
            _nav_button("‹", _shift_month(month, -1), today=today),
            InlineKeyboardButton(
                text=f"{_MONTHS_RU[month.month]} {month.year}",
                callback_data=_NOOP,
            ),
            _nav_button("›", _shift_month(month, 1), today=today),
            _nav_button("год »", _shift_month(month, 12), today=today),
        ],
        [
            InlineKeyboardButton(text=weekday, callback_data=_NOOP)
            for weekday in _WEEKDAYS_RU
        ],
    ]
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(
        month.year,
        month.month,
    ):
        row: list[InlineKeyboardButton] = []
        for day_number in week:
            if day_number == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data=_NOOP))
                continue
            value = date(month.year, month.month, day_number)
            if value > today or value < oldest:
                row.append(InlineKeyboardButton(text="·", callback_data=_NOOP))
                continue
            marker = "✅ " if selected == value else ""
            row.append(
                InlineKeyboardButton(
                    text=f"{marker}{day_number}",
                    callback_data=f"pest_calendar:pick:{value.isoformat()}",
                )
            )
        rows.append(row)

    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Сегодня",
                    callback_data=f"pest_calendar:pick:{today.isoformat()}",
                ),
                InlineKeyboardButton(
                    text="⌨️ Ввести вручную",
                    callback_data="pest_calendar:manual",
                ),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="pest_overview")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_pest_calendar_month(callback_data: str) -> date:
    prefix = "pest_calendar:nav:"
    if not callback_data.startswith(prefix):
        raise ValueError("Некорректная команда календаря.")
    value = date.fromisoformat(callback_data.removeprefix(prefix))
    return date(value.year, value.month, 1)


def parse_pest_calendar_date(callback_data: str) -> date:
    prefix = "pest_calendar:pick:"
    if not callback_data.startswith(prefix):
        raise ValueError("Некорректная дата календаря.")
    return date.fromisoformat(callback_data.removeprefix(prefix))
