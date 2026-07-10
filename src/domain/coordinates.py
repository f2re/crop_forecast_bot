from __future__ import annotations

import re
from dataclasses import dataclass

_COORDINATE_PATTERN = re.compile(
    r"^\s*([-+]?\d+(?:[.,]\d+)?)\s*[,;\s]\s*([-+]?\d+(?:[.,]\d+)?)\s*$"
)


@dataclass(frozen=True, slots=True)
class Coordinates:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError("Широта должна находиться в диапазоне от -90 до 90°")
        if not -180 <= self.longitude <= 180:
            raise ValueError("Долгота должна находиться в диапазоне от -180 до 180°")


def parse_coordinates(value: str) -> Coordinates:
    """Parse decimal coordinates in ``lat, lon`` or ``lat lon`` form."""
    match = _COORDINATE_PATTERN.match(value)
    if match is None:
        raise ValueError("Используйте формат: 55.7558, 37.6173")
    latitude = float(match.group(1).replace(",", "."))
    longitude = float(match.group(2).replace(",", "."))
    return Coordinates(latitude=latitude, longitude=longitude)
