import pytest

from src.domain.coordinates import Coordinates, parse_coordinates


def test_parse_decimal_coordinates_with_comma_separator() -> None:
    coords = parse_coordinates("55.7558, 37.6173")
    assert coords == Coordinates(55.7558, 37.6173)


def test_parse_decimal_coordinates_with_space_separator() -> None:
    coords = parse_coordinates("-33.8688 151.2093")
    assert coords.latitude == pytest.approx(-33.8688)
    assert coords.longitude == pytest.approx(151.2093)


@pytest.mark.parametrize(
    "value",
    ["91, 0", "0, 181", "coordinates", "55.7"],
)
def test_invalid_coordinates_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        parse_coordinates(value)
