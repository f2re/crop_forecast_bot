from datetime import date, timedelta

import pytest

from src.bot.pest_calendar import (
    build_pest_calendar,
    oldest_allowed_biofix,
    parse_pest_calendar_date,
    parse_pest_calendar_month,
    validate_biofix_date,
)


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_pest_calendar_marks_day_and_disables_future() -> None:
    today = date(2026, 8, 3)
    markup = build_pest_calendar(
        today,
        today=today,
        selected=date(2026, 8, 1),
    )
    buttons = _buttons(markup)

    assert any(
        button.text == "✅ 1"
        and button.callback_data == "pest_calendar:pick:2026-08-01"
        for button in buttons
    )
    assert any(
        button.text == "Сегодня"
        and button.callback_data == "pest_calendar:pick:2026-08-03"
        for button in buttons
    )
    assert any(button.text == "·" for button in buttons)


def test_pest_biofix_is_limited_to_current_cycle() -> None:
    today = date(2026, 8, 3)
    assert oldest_allowed_biofix(today) == today - timedelta(days=365)
    assert validate_biofix_date(today, today=today) == today

    with pytest.raises(ValueError, match="будущем"):
        validate_biofix_date(today + timedelta(days=1), today=today)
    with pytest.raises(ValueError, match="365"):
        validate_biofix_date(today - timedelta(days=366), today=today)


def test_pest_calendar_parsers_are_strict() -> None:
    assert parse_pest_calendar_month("pest_calendar:nav:2026-06-01") == date(
        2026,
        6,
        1,
    )
    assert parse_pest_calendar_date("pest_calendar:pick:2026-06-15") == date(
        2026,
        6,
        15,
    )

    with pytest.raises(ValueError):
        parse_pest_calendar_month("pest_calendar:pick:2026-06-01")
    with pytest.raises(ValueError):
        parse_pest_calendar_date("pest_calendar:nav:not-a-date")
