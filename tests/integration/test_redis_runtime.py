from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import CallbackQuery, Chat, Message, User
from redis.asyncio import Redis

import src.bot.scheduler as scheduler_module
from src.bot.middlewares import CallbackIdempotencyMiddleware
from src.bot.scheduler import _send_once, check_frost_alerts
from src.database.crud import NotificationTarget
from src.infrastructure.coordination import Lease, create_coordination


def _test_redis_url() -> str:
    value = os.getenv("TEST_REDIS_URL", "").strip()
    if not value:
        pytest.skip("TEST_REDIS_URL is not configured")
    return value


def _callback(callback_id: str) -> CallbackQuery:
    return CallbackQuery(
        id=callback_id,
        from_user=User(id=1001, is_bot=False, first_name="Farmer"),
        chat_instance="integration-test",
        message=Message(
            message_id=77,
            date=datetime.now(timezone.utc),
            chat=Chat(id=1001, type="private"),
            text="settings",
        ),
        data="set_digest:42:1",
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_redis_leases_are_atomic_across_clients() -> None:
    redis_url = _test_redis_url()
    namespace = f"cropbot-test-{uuid4().hex}"
    cleanup = Redis.from_url(redis_url, decode_responses=True)
    await cleanup.flushdb()

    first = await create_coordination(redis_url, namespace=namespace)
    second = await create_coordination(redis_url, namespace=namespace)
    calls: list[str] = []

    async def sender() -> object:
        calls.append("sent")
        await asyncio.sleep(0.05)
        return object()

    try:
        results = await asyncio.gather(
            _send_once(first, "notification:field:1", 30, sender),
            _send_once(second, "notification:field:1", 30, sender),
        )
        assert sum(bool(result) for result in results) == 1
        assert calls == ["sent"]

        lease = await first.acquire("job:daily-digest", ttl_seconds=30)
        assert lease is not None
        assert await second.acquire("job:daily-digest", ttl_seconds=30) is None
        assert not await second.release(Lease(key=lease.key, token="wrong-token"))
        assert await first.renew(lease, ttl_seconds=60)
        assert await first.release(lease)
        assert await second.acquire("job:daily-digest", ttl_seconds=30) is not None
    finally:
        await first.close()
        await second.close()
        await cleanup.flushdb()
        await cleanup.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_callback_action_is_idempotent_across_runtime_workers() -> None:
    redis_url = _test_redis_url()
    namespace = f"cropbot-callback-{uuid4().hex}"
    cleanup = Redis.from_url(redis_url, decode_responses=True)
    await cleanup.flushdb()

    first_backend = await create_coordination(redis_url, namespace=namespace)
    second_backend = await create_coordination(redis_url, namespace=namespace)
    first = CallbackIdempotencyMiddleware(first_backend)
    second = CallbackIdempotencyMiddleware(second_backend)
    calls: list[str] = []

    async def handler(event, data):
        calls.append(event.id)
        await asyncio.sleep(0.05)
        return "done"

    try:
        results = await asyncio.gather(
            first(handler, _callback("callback-1"), {}),
            second(handler, _callback("callback-2"), {}),
        )
        assert results.count("done") == 1
        assert results.count(None) == 1
        assert len(calls) == 1
    finally:
        await first_backend.close()
        await second_backend.close()
        await cleanup.flushdb()
        await cleanup.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_two_scheduler_workers_send_one_frost_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_url = _test_redis_url()
    namespace = f"cropbot-scheduler-{uuid4().hex}"
    cleanup = Redis.from_url(redis_url, decode_responses=True)
    await cleanup.flushdb()

    first = await create_coordination(redis_url, namespace=namespace)
    second = await create_coordination(redis_url, namespace=namespace)
    target = NotificationTarget(
        telegram_id=1001,
        field_id=42,
        field_name="Северное",
        latitude=55.75,
        longitude=37.62,
        timezone="Europe/Moscow",
        elevation_m=120.0,
        elevation_source="Open-Meteo Forecast API",
        selected_crop="wheat",
        season_start_date=None,
        phenological_phase="Кущение",
        daily_digest_enabled=False,
        frost_alerts_enabled=True,
    )

    async def fake_targets(
        session_factory,
        *,
        daily_digest_only=False,
        frost_alerts_only=False,
    ):
        assert frost_alerts_only is True
        assert daily_digest_only is False
        await asyncio.sleep(0.05)
        return [target]

    async def fake_weather(latitude: float, longitude: float):
        return SimpleNamespace(
            daily=object(),
            meta=SimpleNamespace(
                utc_offset_seconds=3 * 3600,
                elevation_m=120.0,
            ),
        )

    risk = {
        "alerts": [
            {
                "event_date": "2026-07-12",
                "date_local": "12.07.2026",
                "t_min": -1.0,
                "level": "critical",
                "lead_days": 1,
                "elevation_m": 120.0,
            }
        ]
    }

    class FakeBot:
        def __init__(self) -> None:
            self.messages: list[tuple[int, str]] = []

        async def send_message(self, chat_id: int, text: str) -> object:
            self.messages.append((chat_id, text))
            await asyncio.sleep(0.02)
            return object()

    bot = FakeBot()
    monkeypatch.setattr(scheduler_module, "_targets", fake_targets)
    monkeypatch.setattr(scheduler_module, "fetch_agro_data", fake_weather)
    monkeypatch.setattr(
        scheduler_module,
        "calc_frost_risk",
        lambda daily, **kwargs: risk,
    )
    monkeypatch.setattr(
        scheduler_module,
        "format_frost_alert",
        lambda event, crop, **kwargs: "frost alert",
    )

    try:
        await asyncio.gather(
            check_frost_alerts(bot, object(), first),
            check_frost_alerts(bot, object(), second),
        )
        assert bot.messages == [(1001, "frost alert")]

        # The distributed job lock is released, but the field/event
        # notification lease remains committed and prevents a second send.
        await check_frost_alerts(bot, object(), first)
        assert bot.messages == [(1001, "frost alert")]
    finally:
        await first.close()
        await second.close()
        await cleanup.flushdb()
        await cleanup.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_fsm_state_survives_storage_restart() -> None:
    redis_url = _test_redis_url()
    cleanup = Redis.from_url(redis_url, decode_responses=True)
    await cleanup.flushdb()
    key = StorageKey(bot_id=101, chat_id=202, user_id=303)

    first = RedisStorage.from_url(redis_url)
    try:
        await first.set_state(key, "FieldStates:waiting_for_coordinates")
        await first.set_data(
            key,
            {
                "field_action": "create",
                "field_name": "Северное",
            },
        )
    finally:
        await first.close()

    second = RedisStorage.from_url(redis_url)
    try:
        assert await second.get_state(key) == "FieldStates:waiting_for_coordinates"
        assert await second.get_data(key) == {
            "field_action": "create",
            "field_name": "Северное",
        }
        await second.set_state(key, None)
        await second.set_data(key, {})
        assert await second.get_state(key) is None
        assert await second.get_data(key) == {}
    finally:
        await second.close()
        await cleanup.flushdb()
        await cleanup.aclose()
