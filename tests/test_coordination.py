from __future__ import annotations

import pytest

from src.infrastructure.coordination import Lease, MemoryCoordination, RedisCoordination


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
