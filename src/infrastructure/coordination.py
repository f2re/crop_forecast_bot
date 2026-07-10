from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis

_RENEW_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


@dataclass(frozen=True, slots=True)
class Lease:
    key: str
    token: str


class CoordinationBackend(Protocol):
    async def acquire(self, key: str, ttl_seconds: int) -> Lease | None: ...

    async def renew(self, lease: Lease, ttl_seconds: int) -> bool: ...

    async def release(self, lease: Lease) -> bool: ...

    async def close(self) -> None: ...


class RedisCoordination:
    """Atomic leases backed by Redis ``SET NX EX`` and token-checked Lua."""

    def __init__(self, redis: Redis, namespace: str = "crop-forecast-bot"):
        self._redis = redis
        self._namespace = namespace.strip(":")

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key.lstrip(':')}"

    async def acquire(self, key: str, ttl_seconds: int) -> Lease | None:
        _validate_ttl(ttl_seconds)
        redis_key = self._key(key)
        token = secrets.token_urlsafe(24)
        acquired = await self._redis.set(
            redis_key,
            token,
            ex=ttl_seconds,
            nx=True,
        )
        if not acquired:
            return None
        return Lease(key=redis_key, token=token)

    async def renew(self, lease: Lease, ttl_seconds: int) -> bool:
        _validate_ttl(ttl_seconds)
        result = await self._redis.eval(
            _RENEW_SCRIPT,
            1,
            lease.key,
            lease.token,
            ttl_seconds,
        )
        return bool(result)

    async def release(self, lease: Lease) -> bool:
        result = await self._redis.eval(
            _RELEASE_SCRIPT,
            1,
            lease.key,
            lease.token,
        )
        return bool(result)

    async def close(self) -> None:
        await self._redis.aclose()


class MemoryCoordination:
    """Process-local development fallback with the same lease semantics."""

    def __init__(
        self,
        namespace: str = "crop-forecast-bot",
        clock: Callable[[], float] = time.monotonic,
    ):
        self._namespace = namespace.strip(":")
        self._clock = clock
        self._values: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key.lstrip(':')}"

    def _purge_expired(self, now: float) -> None:
        expired = [key for key, (_, expiry) in self._values.items() if expiry <= now]
        for key in expired:
            self._values.pop(key, None)

    async def acquire(self, key: str, ttl_seconds: int) -> Lease | None:
        _validate_ttl(ttl_seconds)
        full_key = self._key(key)
        token = secrets.token_urlsafe(24)
        async with self._lock:
            now = self._clock()
            self._purge_expired(now)
            if full_key in self._values:
                return None
            self._values[full_key] = (token, now + ttl_seconds)
        return Lease(key=full_key, token=token)

    async def renew(self, lease: Lease, ttl_seconds: int) -> bool:
        _validate_ttl(ttl_seconds)
        async with self._lock:
            now = self._clock()
            self._purge_expired(now)
            stored = self._values.get(lease.key)
            if stored is None or stored[0] != lease.token:
                return False
            self._values[lease.key] = (lease.token, now + ttl_seconds)
            return True

    async def release(self, lease: Lease) -> bool:
        async with self._lock:
            now = self._clock()
            self._purge_expired(now)
            stored = self._values.get(lease.key)
            if stored is None or stored[0] != lease.token:
                return False
            self._values.pop(lease.key, None)
            return True

    async def close(self) -> None:
        async with self._lock:
            self._values.clear()


def _validate_ttl(ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        raise ValueError("Lease TTL must be greater than zero")


async def create_coordination(
    redis_url: str | None,
    namespace: str = "crop-forecast-bot",
) -> CoordinationBackend:
    if not redis_url:
        return MemoryCoordination(namespace=namespace)

    redis = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        health_check_interval=30,
    )
    try:
        await redis.ping()
    except Exception:
        await redis.aclose()
        raise
    return RedisCoordination(redis=redis, namespace=namespace)
