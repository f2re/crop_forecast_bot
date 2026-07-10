from datetime import date

import pytest

from src.domain.season import parse_season_date, validate_timezone


def test_parse_season_date_accepts_iso_and_russian_format() -> None:
    today = date(2026, 7, 10)
    assert parse_season_date("2026-04-15", today=today) == date(2026, 4, 15)
    assert parse_season_date("15.04.2026", today=today) == date(2026, 4, 15)


def test_parse_season_date_rejects_future_and_invalid_values() -> None:
    today = date(2026, 7, 10)
    with pytest.raises(ValueError, match="будущем"):
        parse_season_date("11.07.2026", today=today)
    with pytest.raises(ValueError, match="формате"):
        parse_season_date("15/04/2026", today=today)


def test_timezone_validation_uses_iana_database() -> None:
    assert validate_timezone("Europe/Moscow") == "Europe/Moscow"
    with pytest.raises(ValueError, match="Неизвестный"):
        validate_timezone("Mars/Field")
