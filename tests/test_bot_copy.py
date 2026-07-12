from pathlib import Path

from src.bot.handlers.core import _HELP_TEXT


ROOT = Path(__file__).resolve().parents[1]


def test_help_and_field_list_describe_all_field_background_monitoring() -> None:
    source = (ROOT / "src/bot/handlers/core.py").read_text(encoding="utf-8")

    assert "Отчёты и алерты формируются только для активного поля" not in source
    assert "Отчёт, сезон и уведомления относятся к нему" not in source
    assert "фоновые уведомления — ко всем" in _HELP_TEXT
    assert "Фоновые уведомления работают для каждого поля" in source
