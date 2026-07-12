from __future__ import annotations

import asyncio
import os
import sys
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


async def _fake_targets(
    session_factory,
    *,
    daily_digest_only: bool = False,
    frost_alerts_only: bool = False,
):
    assert daily_digest_only is True
    assert frost_alerts_only is False
    return [_target()]


class RecordingBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        self.messages.append((chat_id, text))
        return object()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_job_lease_is_renewed_during_long_provider_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_url = _test_redis_url()
    namespace = f"cropbot-job-heartbeat-{uuid4().hex}"
    cleanup = Redis.from_url(redis_url, decode_responses=True)
    await cleanup.flushdb()
    first = await create_coordination(redis_url, namespace=namespace)
    second = await create_coordination(redis_url, namespace=namespace)
    report_started = asyncio.Event()
    release_report = asyncio.Event()
    report_calls = 0

    async def slow_report(*args, **kwargs):
        nonlocal report_calls
        report_calls += 1
        report_started.set()
        await release_report.wait()
        return SimpleNamespace(text="daily digest")

    monkeypatch.setattr(scheduler_module, "_targets", _fake_targets)
    monkeypatch.setattr(scheduler_module, "generate_agro_report", slow_report)
    bot = RecordingBot()

    try:
        first_run = asyncio.create_task(
            send_daily_digest(
                bot,
                object(),
                first,
                job_lock_ttl_seconds=2,
                renew_interval_seconds=0.25,
            )
        )
        await asyncio.wait_for(report_started.wait(), timeout=2)

        # Wait longer than the original Redis TTL. The heartbeat must keep the
        # first worker's token alive, so the second worker cannot enter.
        await asyncio.sleep(2.3)
        await send_daily_digest(
            bot,
            object(),
            second,
            job_lock_ttl_seconds=2,
            renew_interval_seconds=0.25,
        )
        assert report_calls == 1
        assert bot.messages == []

        release_report.set()
        await asyncio.wait_for(first_run, timeout=2)
        assert bot.messages == [(1001, "daily digest")]
    finally:
        release_report.set()
        await first.close()
        await second.close()
        await cleanup.flushdb()
        await cleanup.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lost_job_lease_cancels_read_and_next_worker_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_url = _test_redis_url()
    namespace = f"cropbot-job-loss-{uuid4().hex}"
    cleanup = Redis.from_url(redis_url, decode_responses=True)
    await cleanup.flushdb()
    first = await create_coordination(redis_url, namespace=namespace)
    second = await create_coordination(redis_url, namespace=namespace)
    first_report_started = asyncio.Event()
    first_report_cancelled = asyncio.Event()
    report_calls = 0

    async def report(*args, **kwargs):
        nonlocal report_calls
        report_calls += 1
        if report_calls == 1:
            first_report_started.set()
            try:
                await asyncio.sleep(10)
            finally:
                first_report_cancelled.set()
        return SimpleNamespace(text="daily digest")

    monkeypatch.setattr(scheduler_module, "_targets", _fake_targets)
    monkeypatch.setattr(scheduler_module, "generate_agro_report", report)
    bot = RecordingBot()

    try:
        first_run = asyncio.create_task(
            send_daily_digest(
                bot,
                object(),
                first,
                job_lock_ttl_seconds=2,
                renew_interval_seconds=0.1,
            )
        )
        await asyncio.wait_for(first_report_started.wait(), timeout=2)

        # Simulate Redis losing the owner's key while a provider read is in
        # progress. The guard must cancel the read and stop before Telegram.
        await cleanup.delete(f"{namespace}:job:daily-digest")
        await asyncio.wait_for(first_run, timeout=2)
        assert first_report_cancelled.is_set()
        assert bot.messages == []

        await send_daily_digest(
            bot,
            object(),
            second,
            job_lock_ttl_seconds=2,
            renew_interval_seconds=0.1,
        )
        assert report_calls == 2
        assert bot.messages == [(1001, "daily digest")]
    finally:
        await first.close()
        await second.close()
        await cleanup.flushdb()
        await cleanup.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crashed_worker_job_lease_recovers_after_ttl() -> None:
    redis_url = _test_redis_url()
    namespace = f"cropbot-job-crash-{uuid4().hex}"
    cleanup = Redis.from_url(redis_url, decode_responses=True)
    await cleanup.flushdb()

    child_code = """
import asyncio
import os
from src.infrastructure.coordination import create_coordination

async def main():
    backend = await create_coordination(os.environ['TEST_REDIS_URL'], namespace=os.environ['LEASE_NAMESPACE'])
    lease = await backend.acquire('job:crash-test', ttl_seconds=2)
    print('ACQUIRED' if lease is not None else 'FAILED', flush=True)
    os._exit(0)

asyncio.run(main())
"""
    env = os.environ.copy()
    env["TEST_REDIS_URL"] = redis_url
    env["LEASE_NAMESPACE"] = namespace
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        child_code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
    assert process.returncode == 0, stderr.decode()
    assert stdout.decode().strip() == "ACQUIRED"

    replacement = await create_coordination(redis_url, namespace=namespace)
    try:
        assert await replacement.acquire("job:crash-test", ttl_seconds=2) is None
        recovered = None
        for _ in range(40):
            await asyncio.sleep(0.1)
            recovered = await replacement.acquire("job:crash-test", ttl_seconds=2)
            if recovered is not None:
                break
        assert recovered is not None
    finally:
        await replacement.close()
        await cleanup.flushdb()
        await cleanup.aclose()
