import pytest

from config.settings import _env_bool, _env_int


def test_env_bool_accepts_explicit_values(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_FLAG", "true")
    assert _env_bool("FEATURE_FLAG") is True
    monkeypatch.setenv("FEATURE_FLAG", "0")
    assert _env_bool("FEATURE_FLAG") is False


def test_env_bool_rejects_ambiguous_values(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_FLAG", "sometimes")
    with pytest.raises(RuntimeError, match="boolean"):
        _env_bool("FEATURE_FLAG")


def test_env_int_accepts_integer_and_rejects_text(monkeypatch) -> None:
    monkeypatch.setenv("RETENTION", "120")
    assert _env_int("RETENTION", 90) == 120
    monkeypatch.setenv("RETENTION", "many")
    with pytest.raises(RuntimeError, match="integer"):
        _env_int("RETENTION", 90)


def test_rag_button_is_hidden_by_default(monkeypatch) -> None:
    from config.settings import get_settings
    from src.bot.keyboards import get_main_keyboard

    monkeypatch.setenv("RAG_ENABLED", "false")
    get_settings.cache_clear()
    keyboard = get_main_keyboard()
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "🤖 Агросоветник" not in labels
    assert "🕘 История предупреждений" in labels

    monkeypatch.setenv("RAG_ENABLED", "true")
    get_settings.cache_clear()
    keyboard = get_main_keyboard()
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "🤖 Агросоветник" in labels
    get_settings.cache_clear()
