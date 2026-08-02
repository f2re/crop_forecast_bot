from aiogram.methods import SendMessage

from src.bot.telegram_text import (
    _prepare_method_text,
    _uses_default_or_explicit_html,
    html_to_plain_text,
    sanitize_telegram_html,
)


def test_sanitizer_preserves_supported_markup_and_escapes_comparisons() -> None:
    raw = (
        "<b>Сухая серия</b>: осадки <1 мм/сут, A & B; "
        "<script>не тег Telegram</script>"
    )

    safe = sanitize_telegram_html(raw)

    assert "<b>Сухая серия</b>" in safe
    assert "&lt;1 мм/сут" in safe
    assert "A &amp; B" in safe
    assert "&lt;script&gt;" in safe
    assert "<script>" not in safe
    assert sanitize_telegram_html(safe) == safe


def test_plain_fallback_removes_markup_without_losing_comparison_sign() -> None:
    assert html_to_plain_text("<b>Осадки</b>: &lt;1 мм") == "Осадки: <1 мм"


def test_aiogram_method_copy_is_safe_and_does_not_mutate_source() -> None:
    method = SendMessage(chat_id=1001, text="<b>Отчёт</b>: осадки <1 мм")

    assert _uses_default_or_explicit_html(method) is True
    prepared = _prepare_method_text(method)
    plain = _prepare_method_text(method, plain=True)

    assert method.text == "<b>Отчёт</b>: осадки <1 мм"
    assert prepared.text == "<b>Отчёт</b>: осадки &lt;1 мм"
    assert plain.text == "Отчёт: осадки <1 мм"
    assert plain.parse_mode is None
