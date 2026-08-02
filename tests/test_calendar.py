from datetime import date

import pytest

from src.bot.calendar import (
    build_season_calendar,
    parse_calendar_date,
    parse_calendar_month,
    shift_month,
)


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_shift_month_crosses_year_boundary() -> None:
    assert shift_month(date(2026, 1, 15), -1) == date(2025, 12, 1)
    assert shift_month(date(2026, 12, 31), 2) == date(2027, 2, 1)


def test_calendar_marks_selected_day_and_disables_future_dates() -> None:
    today = date(2026, 8, 2)
    markup = build_season_calendar(
        date(2026, 8, 1),
        today=today,
        selected=date(2026, 8, 1),
    )
    buttons = _buttons(markup)

    selected = next(button for button in buttons if button.text == "✅ 1")
    assert selected.callback_data == "season_calendar:pick:2026-08-01"
    assert any(
        button.text == "Сегодня"
        and button.callback_data == "season_calendar:pick:2026-08-02"
        for button in buttons
    )
    assert any(button.text == "·" for button in buttons)
    assert next(button for button in buttons if button.text == "›").callback_data == (
        "season_calendar:noop"
    )


def test_calendar_allows_previous_year_for_winter_crops() -> None:
    markup = build_season_calendar(
        date(2025, 9, 1),
        today=date(2026, 8, 2),
    )
    buttons = _buttons(markup)

    assert any(button.text == "Сентябрь 2025" for button in buttons)
    assert any(
        button.callback_data == "season_calendar:pick:2025-09-15"
        for button in buttons
    )


def test_calendar_callback_parsers_are_strict() -> None:
    assert parse_calendar_month("season_calendar:nav:2025-09-01") == date(
        2025, 9, 1
    )
    assert parse_calendar_date("season_calendar:pick:2025-09-15") == date(
        2025, 9, 15
    )

    with pytest.raises(ValueError):
        parse_calendar_month("season_calendar:pick:2025-09-01")
    with pytest.raises(ValueError):
        parse_calendar_date("season_calendar:nav:not-a-date")
