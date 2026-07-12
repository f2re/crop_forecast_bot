from __future__ import annotations

import os
from uuid import uuid4

import pytest
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.bot.main import build_dispatcher
from src.database.crud import get_field_context
from src.database.models import Base
from src.infrastructure.coordination import MemoryCoordination
from tests.bot_harness import callback_update, make_bot, message_update


def _test_redis_url() -> str:
    value = os.getenv("TEST_REDIS_URL", "").strip()
    if not value:
        pytest.skip("TEST_REDIS_URL is not configured")
    return value


def _storage(redis_url: str, prefix: str) -> RedisStorage:
    return RedisStorage.from_url(
        redis_url,
        key_builder=DefaultKeyBuilder(prefix=prefix, with_bot_id=True),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_core_fsm_branches_continue_after_storage_reopen(tmp_path) -> None:
    redis_url = _test_redis_url()
    prefix = f"cropbot-dispatcher-{uuid4().hex}"
    cleanup = Redis.from_url(redis_url, decode_responses=True)
    await cleanup.flushdb()

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'dispatcher-restart.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    current_storage = _storage(redis_url, prefix)
    coordination = MemoryCoordination(namespace=prefix)
    dispatcher = build_dispatcher(
        storage=current_storage,
        session_factory=sessions,
        coordination=coordination,
    )
    bot = make_bot()

    async def reopen_storage() -> None:
        nonlocal current_storage
        await current_storage.close()
        current_storage = _storage(redis_url, prefix)
        dispatcher.fsm.storage = current_storage

    try:
        await dispatcher.feed_update(bot, message_update(1, text="/start"))
        await dispatcher.feed_update(bot, callback_update(2, data="field_add"))

        # waiting_for_name survives a storage/client restart.
        await reopen_storage()
        await dispatcher.feed_update(bot, message_update(3, text="Северное"))

        # waiting_for_coordinates and its action payload survive another restart.
        await reopen_storage()
        await dispatcher.feed_update(bot, message_update(4, text="55.75, 37.62"))

        async with sessions() as session:
            context = await get_field_context(session, 1001)
        assert context is not None
        field_id = context.field_id

        await dispatcher.feed_update(
            bot,
            callback_update(5, data=f"field_rename:{field_id}"),
        )

        # waiting_for_rename and field_id survive restart.
        await reopen_storage()
        await dispatcher.feed_update(bot, message_update(6, text="Северное поле"))
        await dispatcher.feed_update(bot, callback_update(7, data="crop_pick:sunflower"))
        await dispatcher.feed_update(bot, callback_update(8, data="season_start_set"))

        # waiting_for_start_date survives restart.
        await reopen_storage()
        await dispatcher.feed_update(bot, message_update(9, text="15.04.2026"))

        async with sessions() as session:
            restored = await get_field_context(session, 1001)
        assert restored is not None
        assert restored.field_name == "Северное поле"
        assert restored.crop_key == "sunflower"
        assert restored.season_start_date.isoformat() == "2026-04-15"
    finally:
        await current_storage.close()
        await coordination.close()
        await bot.session.close()
        await engine.dispose()
        await cleanup.flushdb()
        await cleanup.aclose()
