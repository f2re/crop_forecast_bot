import pytest

from src.domain.fields import normalize_field_name


def test_field_name_is_normalized_for_display_and_comparison() -> None:
    assert normalize_field_name("  Северное   поле  ") == "Северное поле"
    assert normalize_field_name("Ｐｏｌｅ １２") == "Pole 12"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("A", "не менее двух"),
        ("x" * 61, "не длиннее 60"),
        ("Поле <1>", "символы < и >"),
        ("Поле\u0007", "управляющие символы"),
    ],
)
def test_invalid_field_names_are_rejected(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_field_name(value)
