from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from redis.asyncio import Redis

import src.bot.scheduler as scheduler_module
from src.bot.scheduler import send_daily_digest
from src.database.crud import NotificationTarget
from src.infrastructure.coordination import create_coordination


def _test_redis_url() -> str:
    value = os.getenv("TEST_REDIS_URL", "").strip()
    if not value:
        pytest.skip("TEST_REDIS_URL is not configured")
    return value


def _target() -> NotificationTarget:
    return NotificationTarget(
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
        daily_digest_enabled=True,
        frost_alerts_enabled=True,
    )


async def _install_digest_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_targets(
        session_factory,
        *,
        daily_digest_only=False,
        frost_alerts_only=False,
    ):
        assert daily_digest_only is True
        assert frost_alerts_only is False
        await asyncio.sleep(0.05)
        return [_target()]

    async def fake_report(*args, **kwargs):
        return SimpleNamespace(text="daily digest")

    monkeypatch.setattr(scheduler_module, "_targets", fake_targets)
    monkeypatch.setattr(scheduler_module, "generate_agro_report", fake_report)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_two_scheduler_workers_send_one_daily_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_url = _test_redis_url()
    namespace = f"cropbot-digest-workers-{uuid4().hex}"
    cleanup = Redis.from_url(redis_url, decode_responses=True)
    await cleanup.flushdb()
    first = await create_coordination(redis_url, namespace=namespace)
    second = await create_coordination(redis_url, namespace=namespace)
    await _install_digest_fakes(monkeypatch)

    class FakeBot:
        def __init__(self) -> None:
            self.messages: list[tuple[int, str]] = []

        async def send_message(self, chat_id: int, text: str) -> object:
            self.messages.append((chat_id, text))
            await asyncio.sleep(0.02)
            return object()

    bot = FakeBot()
    try:
        await asyncio.gather(
            send_daily_digest(bot, object(), first),
            send_daily_digest(bot, object(), second),
        )
        assert bot.messages == [(1001, "daily digest")]

        # The job lock is free after the run, but the per-field/day delivery
        # lease remains committed and suppresses another digest.
        await send_daily_digest(bot, object(), first)
        assert bot.messages == [(1001, "daily digest")]
    finally:
        await first.close()
        await second.close()
        await cleanup.flushdb()
        await cleanup.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_digest_retries_after_telegram_send_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_url = _test_redis_url()
    namespace = f"cropbot-digest-retry-{uuid4().hex}"
    cleanup = Redis.from_url(redis_url, decode_responses=True)
    await cleanup.flushdb()
    coordination = await create_coordination(redis_url, namespace=namespace)
    await _install_digest_fakes(monkeypatch)

    class FailingBot:
        async def send_message(self, chat_id: int, text: str) -> object:
            raise RuntimeError("Telegram unavailable")

    class SuccessfulBot:
        def __init__(self) -> None:
            self.messages: list[tuple[int, str]] = []

        async def send_message(self, chat_id: int, text: str) -> object:
            self.messages.append((chat_id, text))
            return object()

    successful = SuccessfulBot()
    try:
        # send_daily_digest logs and contains the provider/Telegram exception.
        # _send_once releases the temporary notification reservation.
        await send_daily_digest(FailingBot(), object(), coordination)
        await send_daily_digest(successful, object(), coordination)
        assert successful.messages == [(1001, "daily digest")]
    finally:
        await coordination.close()
        await cleanup.flushdb()
        await cleanup.aclose()
