from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

import src.bot.handlers.settings as settings_handler
from src.bot.handlers.settings import parse_setting_callback
from src.bot.keyboards import get_settings_keyboard
from src.bot.middlewares import CallbackIdempotencyMiddleware
from src.infrastructure.coordination import MemoryCoordination


def _callback(callback_id: str, data: str = "field_activate:42") -> CallbackQuery:
    return CallbackQuery(
        id=callback_id,
        from_user=User(id=1001, is_bot=False, first_name="Farmer"),
        chat_instance="test-instance",
        message=Message(
            message_id=77,
            date=datetime.now(timezone.utc),
            chat=Chat(id=1001, type="private"),
            text="settings",
        ),
        data=data,
    )


class _FakeMessage:
    def __init__(self) -> None:
        self.edits: list[tuple[str, object | None]] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edits.append((text, reply_markup))


class _FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=1001)
        self.message = _FakeMessage()
        self.answers: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append((text, show_alert))


@pytest.mark.asyncio
async def test_exact_callback_redelivery_runs_handler_once() -> None:
    coordination = MemoryCoordination(namespace="test")
    middleware = CallbackIdempotencyMiddleware(coordination)
    callback = _callback("delivery-1")
    calls = 0

    async def handler(event, data):
        nonlocal calls
        calls += 1
        return "done"

    assert await middleware(handler, callback, {}) == "done"
    assert await middleware(handler, callback, {}) is None
    assert calls == 1


@pytest.mark.asyncio
async def test_concurrent_button_presses_share_semantic_action_key() -> None:
    coordination = MemoryCoordination(namespace="test")
    middleware = CallbackIdempotencyMiddleware(coordination)
    first = _callback("delivery-1")
    second = _callback("delivery-2")
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def handler(event, data):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "done"

    first_task = asyncio.create_task(middleware(handler, first, {}))
    await started.wait()
    assert await middleware(handler, second, {}) is None
    release.set()
    assert await first_task == "done"
    assert calls == 1


@pytest.mark.asyncio
async def test_handler_failure_releases_callback_reservations() -> None:
    coordination = MemoryCoordination(namespace="test")
    middleware = CallbackIdempotencyMiddleware(coordination)
    callback = _callback("delivery-1")

    async def failing_handler(event, data):
        raise RuntimeError("temporary failure")

    with pytest.raises(RuntimeError, match="temporary failure"):
        await middleware(failing_handler, callback, {})

    calls = 0

    async def successful_handler(event, data):
        nonlocal calls
        calls += 1
        return "done"

    assert await middleware(successful_handler, callback, {}) == "done"
    assert calls == 1


def test_settings_keyboard_encodes_field_and_desired_state() -> None:
    keyboard = get_settings_keyboard(
        field_id=42,
        daily_digest_enabled=False,
        frost_alerts_enabled=True,
    )
    callback_data = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "set_digest:42:1" in callback_data
    assert "set_frost:42:0" in callback_data
    assert "toggle_digest" not in callback_data
    assert "toggle_frost" not in callback_data


def test_setting_callback_parser_is_strict() -> None:
    assert parse_setting_callback("set_digest:42:1", "set_digest") == (42, True)
    assert parse_setting_callback("set_frost:42:0", "set_frost") == (42, False)
    with pytest.raises(ValueError):
        parse_setting_callback("set_digest:42:toggle", "set_digest")
    with pytest.raises(ValueError):
        parse_setting_callback("set_digest:-1:1", "set_digest")


@pytest.mark.asyncio
async def test_digest_callback_sets_explicit_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = SimpleNamespace(
        field_id=42,
        field_name="Северное",
        daily_digest=False,
        frost_alerts=True,
    )
    after = SimpleNamespace(
        field_id=42,
        field_name="Северное",
        daily_digest=True,
        frost_alerts=True,
    )
    preferences = SimpleNamespace(
        mode="immediate",
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    saved: list[dict[str, bool]] = []

    async def fake_context(session, telegram_id):
        return before

    async def fake_save(session, telegram_id, **kwargs):
        saved.append(kwargs)
        return after

    async def fake_preferences(session, callback, field_id):
        assert field_id == 42
        return preferences

    monkeypatch.setattr(settings_handler, "get_field_context", fake_context)
    monkeypatch.setattr(settings_handler, "set_field_notifications", fake_save)
    monkeypatch.setattr(settings_handler, "_preferences", fake_preferences)
    callback = _FakeCallback("set_digest:42:1")

    await settings_handler.set_digest(callback, object())

    assert saved == [{"daily_digest": True}]
    assert callback.answers[-1] == ("Ежедневный агроотчёт включён", False)
    markup = callback.message.edits[-1][1]
    callback_data = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]
    assert "set_digest:42:0" in callback_data


@pytest.mark.asyncio
async def test_stale_field_callback_does_not_change_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = SimpleNamespace(
        field_id=42,
        field_name="Северное",
        daily_digest=False,
        frost_alerts=True,
    )
    save_called = False

    async def fake_context(session, telegram_id):
        return context

    async def fake_save(session, telegram_id, **kwargs):
        nonlocal save_called
        save_called = True
        return context

    monkeypatch.setattr(settings_handler, "get_field_context", fake_context)
    monkeypatch.setattr(settings_handler, "set_field_notifications", fake_save)
    callback = _FakeCallback("set_digest:41:1")

    await settings_handler.set_digest(callback, object())

    assert save_called is False
    assert callback.answers[-1][1] is True
    assert "другому полю" in (callback.answers[-1][0] or "")
    assert callback.message.edits == []
