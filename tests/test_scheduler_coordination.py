from __future__ import annotations

import pytest

from src.bot.scheduler import _send_once
from src.infrastructure.coordination import MemoryCoordination


@pytest.mark.asyncio
async def test_send_once_persists_deduplication_after_success() -> None:
    coordination = MemoryCoordination(namespace="test")
    calls: list[str] = []

    async def sender() -> object:
        calls.append("sent")
        return object()

    assert await _send_once(coordination, "notification:1", 3600, sender)
    assert not await _send_once(coordination, "notification:1", 3600, sender)
    assert calls == ["sent"]


@pytest.mark.asyncio
async def test_send_once_releases_reservation_after_failure() -> None:
    coordination = MemoryCoordination(namespace="test")
    calls = 0

    async def failing_sender() -> object:
        nonlocal calls
        calls += 1
        raise RuntimeError("Telegram unavailable")

    with pytest.raises(RuntimeError, match="Telegram unavailable"):
        await _send_once(coordination, "notification:2", 3600, failing_sender)

    async def successful_sender() -> object:
        nonlocal calls
        calls += 1
        return object()

    assert await _send_once(coordination, "notification:2", 3600, successful_sender)
    assert calls == 2
