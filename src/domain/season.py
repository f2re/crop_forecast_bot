from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y")
_MIN_SEASON_DATE = date(1940, 1, 1)


def validate_timezone(timezone_name: str) -> str:
    """Return a valid IANA timezone name or raise a user-facing ValueError."""
    value = timezone_name.strip()
    if not value:
        raise ValueError("Часовой пояс не указан.")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Неизвестный часовой пояс: {value}") from exc
    return value


def local_today(timezone_name: str) -> date:
    """Return the current local date, falling back to UTC for legacy records."""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return datetime.now(zone).date()


def parse_season_date(raw_value: str, *, today: date | None = None) -> date:
    """Parse an active-season date in ISO or Russian dotted notation.

    Active seasons may start in a previous calendar year (for example winter
    crops), but cannot start in the future. Dates before the beginning of the
    supported reanalysis era are rejected as likely input errors.
    """
    value = raw_value.strip()
    parsed: date | None = None
    for pattern in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, pattern).date()
            break
        except ValueError:
            continue

    if parsed is None:
        raise ValueError("Введите дату в формате ДД.ММ.ГГГГ или ГГГГ-ММ-ДД.")

    current = today or date.today()
    if parsed > current:
        raise ValueError("Дата начала активного сезона не может быть в будущем.")
    if parsed < _MIN_SEASON_DATE:
        raise ValueError("Дата слишком ранняя. Проверьте год.")
    return parsed
