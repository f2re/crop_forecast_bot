from pathlib import Path

import pytest


FARMER_FACING_FILES = (
    "src/bot/risk_language.py",
    "src/bot/risk_alerts.py",
    "src/bot/risk_overview.py",
    "src/bot/handlers/settings.py",
    "src/bot/pest_notification_messages.py",
)

FORBIDDEN_PHRASES = (
    "пока наблюдаем",
    "уровни наблюдения",
    "нужна проверка",
    "Вернитесь к обычному наблюдению",
)


@pytest.mark.parametrize("relative_path", FARMER_FACING_FILES)
def test_farmer_facing_copy_has_no_internal_or_robotic_phrases(relative_path: str) -> None:
    text = Path(relative_path).read_text(encoding="utf-8")
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text, f"{relative_path}: forbidden farmer-facing phrase {phrase!r}"
