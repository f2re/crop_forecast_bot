from __future__ import annotations

import asyncio

import pytest

from src.infrastructure.coordination import (
    Lease,
    LeaseLostError,
    MemoryCoordination,
    RedisCoordination,
    RenewingLease,
)


@pytest.mark.asyncio
async def test_memory_lease_is_exclusive_renewable_and_releasable() -> None:
    now = [100.0]
    backend = MemoryCoordination(clock=lambda: now[0])

    lease = await backend.acquire("notification:user:1", ttl_seconds=10)
    assert lease is not None
    assert await backend.acquire("notification:user:1", ttl_seconds=10) is None

    now[0] += 5
    assert await backend.renew(lease, ttl_seconds=20)
    assert not await backend.release(Lease(key=lease.key, token="wrong-token"))
    assert await backend.release(lease)
    assert await backend.acquire("notification:user:1", ttl_seconds=10) is not None


@pytest.mark.asyncio
async def test_memory_lease_can_be_reacquired_after_expiry() -> None:
    now = [10.0]
    backend = MemoryCoordination(clock=lambda: now[0])

    first = await backend.acquire("job:frost", ttl_seconds=3)
    assert first is not None
    now[0] += 4

    second = await backend.acquire("job:frost", ttl_seconds=3)
    assert second is not None
    assert second.token != first.token
    assert not await backend.renew(first, ttl_seconds=3)


@pytest.mark.asyncio
async def test_invalid_lease_ttl_is_rejected() -> None:
    backend = MemoryCoordination()
    with pytest.raises(ValueError, match="TTL"):
        await backend.acquire("job:test", ttl_seconds=0)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.closed = False

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        assert ex > 0
        assert nx is True
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script: str, keys: int, key: str, token: str, *args: int) -> int:
        assert keys == 1
        if self.values.get(key) != token:
            return 0
        if "DEL" in script:
            self.values.pop(key, None)
        else:
            assert args and args[0] > 0
        return 1

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_redis_backend_uses_namespaced_token_checked_leases() -> None:
    redis = FakeRedis()
    backend = RedisCoordination(redis=redis, namespace="test-bot")  # type: ignore[arg-type]

    lease = await backend.acquire("job:digest", ttl_seconds=30)
    assert lease is not None
    assert lease.key == "test-bot:job:digest"
    assert await backend.acquire("job:digest", ttl_seconds=30) is None
    assert await backend.renew(lease, ttl_seconds=60)
    assert await backend.release(lease)

    await backend.close()
    assert redis.closed


class ScriptedCoordination:
    def __init__(self, renew_results: list[bool]) -> None:
        self.renew_results = renew_results
        self.acquire_calls = 0
        self.renew_calls = 0
        self.release_calls = 0
        self.lease = Lease(key="test:job", token="owner-token")

    async def acquire(self, key: str, ttl_seconds: int) -> Lease | None:
        assert key == "job"
        assert ttl_seconds > 0
        self.acquire_calls += 1
        return self.lease

    async def renew(self, lease: Lease, ttl_seconds: int) -> bool:
        assert lease == self.lease
        assert ttl_seconds > 0
        self.renew_calls += 1
        if self.renew_results:
            return self.renew_results.pop(0)
        return True

    async def release(self, lease: Lease) -> bool:
        assert lease == self.lease
        self.release_calls += 1
        return True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_renewing_lease_keeps_long_operation_owned() -> None:
    backend = ScriptedCoordination([True, True, True])
    guard = await RenewingLease.acquire(
        backend,
        "job",
        ttl_seconds=1,
        renew_interval_seconds=0.01,
    )
    assert guard is not None

    async with guard:
        result = await guard.run(asyncio.sleep(0.04, result="done"))
        assert result == "done"
        guard.ensure_owned()

    assert backend.renew_calls >= 2
    assert backend.release_calls == 1


@pytest.mark.asyncio
async def test_renewing_lease_cancels_operation_when_token_is_lost() -> None:
    backend = ScriptedCoordination([False])
    guard = await RenewingLease.acquire(
        backend,
        "job",
        ttl_seconds=1,
        renew_interval_seconds=0.01,
    )
    assert guard is not None
    cancelled = asyncio.Event()

    async def operation() -> None:
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    async with guard:
        with pytest.raises(LeaseLostError, match="no longer owns"):
            await guard.run(operation())
        assert guard.lost is True

    assert cancelled.is_set()
    assert backend.release_calls == 1


@pytest.mark.asyncio
async def test_renewing_lease_rejects_interval_not_shorter_than_ttl() -> None:
    backend = ScriptedCoordination([])
    with pytest.raises(ValueError, match="shorter"):
        await RenewingLease.acquire(
            backend,
            "job",
            ttl_seconds=1,
            renew_interval_seconds=1,
        )
    assert backend.acquire_calls == 0


@pytest.mark.asyncio
async def test_renewing_lease_cancels_operation_when_caller_is_cancelled() -> None:
    backend = ScriptedCoordination([True])
    guard = await RenewingLease.acquire(
        backend,
        "job",
        ttl_seconds=1,
        renew_interval_seconds=0.2,
    )
    assert guard is not None
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def operation() -> None:
        started.set()
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    async with guard:
        task = asyncio.create_task(guard.run(operation()))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert cancelled.is_set()
