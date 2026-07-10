from __future__ import annotations

import re
import unicodedata

_MIN_FIELD_NAME_LENGTH = 2
_MAX_FIELD_NAME_LENGTH = 60
_WHITESPACE = re.compile(r"\s+")


def normalize_field_name(raw_value: str) -> str:
    """Normalize a user supplied field name or raise a user-facing error."""
    value = unicodedata.normalize("NFKC", raw_value)
    value = _WHITESPACE.sub(" ", value).strip()
    if len(value) < _MIN_FIELD_NAME_LENGTH:
        raise ValueError("Название поля должно содержать не менее двух символов.")
    if len(value) > _MAX_FIELD_NAME_LENGTH:
        raise ValueError(
            f"Название поля должно быть не длиннее {_MAX_FIELD_NAME_LENGTH} символов."
        )
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError("Название поля содержит недопустимые управляющие символы.")
    if any(character in "<>\u0000" for character in value):
        raise ValueError("В названии поля нельзя использовать символы < и >.")
    return value
