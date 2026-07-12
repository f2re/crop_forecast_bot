from datetime import datetime, timezone

from src.bot.scheduler import _daily_digest_is_due, _local_date


def test_daily_digest_window_uses_field_timezone() -> None:
    now = datetime(2026, 7, 12, 4, 5, tzinfo=timezone.utc)

    assert _daily_digest_is_due("Europe/Moscow", now) is True
    assert _daily_digest_is_due("Europe/London", now) is False
    assert _local_date("Europe/Moscow", now) == "2026-07-12"


def test_daily_digest_window_allows_delayed_morning_retry() -> None:
    at_ten_local = datetime(2026, 7, 12, 7, 5, tzinfo=timezone.utc)
    at_eleven_local = datetime(2026, 7, 12, 8, 5, tzinfo=timezone.utc)

    assert _daily_digest_is_due("Europe/Moscow", at_ten_local) is True
    assert _daily_digest_is_due("Europe/Moscow", at_eleven_local) is False


def test_unknown_timezone_falls_back_to_utc() -> None:
    now = datetime(2026, 7, 12, 7, 5, tzinfo=timezone.utc)

    assert _daily_digest_is_due("Unknown/Timezone", now) is True
    assert _local_date("Unknown/Timezone", now) == "2026-07-12"
