from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_night_moisture_document_keeps_temperature_drop_non_triggering() -> None:
    text = (
        PROJECT_ROOT / "docs/LATE_BLIGHT_NIGHT_MOISTURE.md"
    ).read_text(encoding="utf-8")

    assert "перепад температуры сам по себе" in text
    assert "не меняют" in text
    assert "не создают самостоятельное Telegram-предупреждение" in text
    assert "Открытый грунт" in text
    assert "greenhouse" in text
    assert "не показывает вероятность заражения" in text
