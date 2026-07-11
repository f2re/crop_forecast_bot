from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from src.bot.scheduler import _send_once
from src.infrastructure.coordination import Lease, create_coordination


def _test_redis_url() -> str:
    value = os.getenv("TEST_REDIS_URL", "").strip()
    if not value:
        pytest.skip("TEST_REDIS_URL is not configured")
    return value


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
