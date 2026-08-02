from __future__ import annotations

import calendar
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_MIN_DATE = date(1940, 1, 1)
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
_NOOP = "season_calendar:noop"


def shift_month(value: date, months: int) -> date:
    """Return the first day of a month shifted by ``months``."""

    absolute = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(absolute, 12)
    return date(year, month_index + 1, 1)


def _month_is_available(month: date, *, today: date) -> bool:
    current_month = date(today.year, today.month, 1)
    return date(_MIN_DATE.year, _MIN_DATE.month, 1) <= month <= current_month


def _nav_button(label: str, target: date, *, today: date) -> InlineKeyboardButton:
    callback = (
        f"season_calendar:nav:{target.isoformat()}"
        if _month_is_available(target, today=today)
        else _NOOP
    )
    return InlineKeyboardButton(text=label, callback_data=callback)


def build_season_calendar(
    display_month: date,
    *,
    today: date,
    selected: date | None = None,
) -> InlineKeyboardMarkup:
    """Build an inline calendar without a Mini App or external web service."""

    month = date(display_month.year, display_month.month, 1)
    if not _month_is_available(month, today=today):
        month = date(today.year, today.month, 1)

    rows: list[list[InlineKeyboardButton]] = [
        [
            _nav_button("« год", shift_month(month, -12), today=today),
            _nav_button("‹", shift_month(month, -1), today=today),
            InlineKeyboardButton(
                text=f"{_MONTHS_RU[month.month]} {month.year}",
                callback_data=_NOOP,
            ),
            _nav_button("›", shift_month(month, 1), today=today),
            _nav_button("год »", shift_month(month, 12), today=today),
        ],
        [
            InlineKeyboardButton(text=weekday, callback_data=_NOOP)
            for weekday in _WEEKDAYS_RU
        ],
    ]

    month_calendar = calendar.Calendar(firstweekday=0)
    for week in month_calendar.monthdayscalendar(month.year, month.month):
        row: list[InlineKeyboardButton] = []
        for day_number in week:
            if day_number == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data=_NOOP))
                continue
            value = date(month.year, month.month, day_number)
            if value > today or value < _MIN_DATE:
                row.append(InlineKeyboardButton(text="·", callback_data=_NOOP))
                continue
            marker = "✅ " if selected == value else ""
            row.append(
                InlineKeyboardButton(
                    text=f"{marker}{day_number}",
                    callback_data=f"season_calendar:pick:{value.isoformat()}",
                )
            )
        rows.append(row)

    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Сегодня",
                    callback_data=f"season_calendar:pick:{today.isoformat()}",
                ),
                InlineKeyboardButton(
                    text="⌨️ Ввести вручную",
                    callback_data="season_calendar:manual",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="◀️ К сезону",
                    callback_data="season_calendar:cancel",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_calendar_month(callback_data: str) -> date:
    prefix = "season_calendar:nav:"
    if not callback_data.startswith(prefix):
        raise ValueError("Некорректная команда календаря.")
    value = date.fromisoformat(callback_data.removeprefix(prefix))
    return date(value.year, value.month, 1)


def parse_calendar_date(callback_data: str) -> date:
    prefix = "season_calendar:pick:"
    if not callback_data.startswith(prefix):
        raise ValueError("Некорректная дата календаря.")
    return date.fromisoformat(callback_data.removeprefix(prefix))
