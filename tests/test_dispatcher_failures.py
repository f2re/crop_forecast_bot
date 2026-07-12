from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.bot.main import build_dispatcher
from src.database.models import Base
from src.infrastructure.coordination import MemoryCoordination
from tests.bot_harness import RecordingSession, callback_update, make_bot, message_update


class FailingRedisStorage(BaseStorage):
    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        raise RedisError("redis offline")

    async def get_state(self, key: StorageKey) -> str | None:
        raise RedisError("redis offline")

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        raise RedisError("redis offline")

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        raise RedisError("redis offline")

    async def close(self) -> None:
        return None


class FailingSessionContext:
    async def __aenter__(self):
        raise SQLAlchemyError("database offline")

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def failing_session_factory() -> FailingSessionContext:
    return FailingSessionContext()


async def _session_factory(tmp_path, filename: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / filename}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, sessions


@pytest.mark.asyncio
async def test_database_outage_returns_controlled_message() -> None:
    storage = MemoryStorage()
    coordination = MemoryCoordination(namespace="database-outage")
    telegram = RecordingSession()
    bot = make_bot(telegram)
    dispatcher = build_dispatcher(
        storage=storage,
        session_factory=failing_session_factory,
        coordination=coordination,
    )

    try:
        await dispatcher.feed_update(bot, message_update(1, text="/start"))
        assert any(
            "Хранилище данных временно недоступно" in text
            for text in telegram.texts
        )
        assert any("Код ошибки" in text for text in telegram.texts)
    finally:
        await storage.close()
        await coordination.close()
        await bot.session.close()


@pytest.mark.asyncio
async def test_redis_outage_before_handler_returns_controlled_message(tmp_path) -> None:
    engine, sessions = await _session_factory(tmp_path, "redis-outage.sqlite")
    storage = FailingRedisStorage()
    coordination = MemoryCoordination(namespace="redis-outage")
    telegram = RecordingSession()
    bot = make_bot(telegram)
    dispatcher = build_dispatcher(
        storage=storage,
        session_factory=sessions,
        coordination=coordination,
    )

    try:
        await dispatcher.feed_update(bot, message_update(1, text="/start"))
        assert any(
            "Не удалось прочитать состояние диалога" in text
            for text in telegram.texts
        )
    finally:
        await storage.close()
        await coordination.close()
        await bot.session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_deleted_callback_message_reopens_menu(tmp_path) -> None:
    engine, sessions = await _session_factory(tmp_path, "deleted-message.sqlite")
    storage = MemoryStorage()
    coordination = MemoryCoordination(namespace="deleted-message")
    telegram = RecordingSession(fail_edit_message=True)
    bot = make_bot(telegram)
    dispatcher = build_dispatcher(
        storage=storage,
        session_factory=sessions,
        coordination=coordination,
    )

    try:
        await dispatcher.feed_update(bot, callback_update(1, data="fields"))
        assert any(
            "Исходное сообщение было удалено или устарело" in text
            for text in telegram.texts
        )
    finally:
        await storage.close()
        await coordination.close()
        await bot.session.close()
        await engine.dispose()
