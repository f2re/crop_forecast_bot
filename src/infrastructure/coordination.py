from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol, TypeVar

from redis.asyncio import Redis

logger = logging.getLogger(__name__)
T = TypeVar("T")

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


class LeaseLostError(RuntimeError):
    """Raised when a worker no longer owns a distributed lease."""


class RenewingLease:
    """Keep a token-checked lease alive and cancel work when ownership is lost.

    The guard renews the lease independently of target iteration. This matters
    for provider and Telegram calls that can take longer than one scheduler
    checkpoint. ``run`` races the protected awaitable against the lease-loss
    signal and cancels the awaitable before allowing further side effects.
    """

    def __init__(
        self,
        backend: CoordinationBackend,
        lease: Lease,
        *,
        ttl_seconds: int,
        renew_interval_seconds: float,
    ) -> None:
        _validate_ttl(ttl_seconds)
        _validate_renew_interval(ttl_seconds, renew_interval_seconds)
        self._backend = backend
        self.lease = lease
        self._ttl_seconds = ttl_seconds
        self._renew_interval_seconds = renew_interval_seconds
        self._lost = asyncio.Event()
        self._closed = False
        self._renew_task: asyncio.Task[None] | None = None
        self._loss_reason = "lease ownership was lost"

    @classmethod
    async def acquire(
        cls,
        backend: CoordinationBackend,
        key: str,
        *,
        ttl_seconds: int,
        renew_interval_seconds: float | None = None,
    ) -> RenewingLease | None:
        _validate_ttl(ttl_seconds)
        interval = renew_interval_seconds
        if interval is None:
            interval = max(0.1, min(float(ttl_seconds) / 3.0, 60.0))
        _validate_renew_interval(ttl_seconds, interval)
        lease = await backend.acquire(key, ttl_seconds)
        if lease is None:
            return None
        return cls(
            backend,
            lease,
            ttl_seconds=ttl_seconds,
            renew_interval_seconds=interval,
        )

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    @property
    def loss_reason(self) -> str:
        return self._loss_reason

    async def __aenter__(self) -> RenewingLease:
        if self._closed:
            raise RuntimeError("Cannot restart a closed lease guard")
        if self._renew_task is not None:
            raise RuntimeError("Lease guard is already running")
        self._renew_task = asyncio.create_task(
            self._renew_loop(),
            name=f"lease-renew:{self.lease.key}",
        )
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    def ensure_owned(self) -> None:
        if self._lost.is_set():
            raise LeaseLostError(self._loss_reason)

    async def run(self, operation: Awaitable[T]) -> T:
        """Run one awaitable while ownership is valid.

        If the renewal loop reports loss first, the operation is cancelled and
        ``LeaseLostError`` is raised. If both complete together, loss wins so a
        caller never continues to the next side effect under uncertain
        ownership.
        """

        self.ensure_owned()
        operation_task = asyncio.ensure_future(operation)
        loss_task = asyncio.create_task(self._lost.wait())
        try:
            done, _ = await asyncio.wait(
                {operation_task, loss_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if loss_task in done and self._lost.is_set():
                if not operation_task.done():
                    operation_task.cancel()
                with suppress(asyncio.CancelledError):
                    await operation_task
                raise LeaseLostError(self._loss_reason)
            return await operation_task
        except BaseException:
            if not operation_task.done():
                operation_task.cancel()
                with suppress(asyncio.CancelledError):
                    await operation_task
            raise
        finally:
            loss_task.cancel()
            with suppress(asyncio.CancelledError):
                await loss_task

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._renew_task is not None:
            self._renew_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._renew_task
        try:
            await self._backend.release(self.lease)
        except Exception:
            logger.exception("Failed to release lease %s", self.lease.key)

    async def _renew_loop(self) -> None:
        while True:
            await asyncio.sleep(self._renew_interval_seconds)
            try:
                renewed = await self._backend.renew(
                    self.lease,
                    self._ttl_seconds,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._loss_reason = (
                    f"lease renewal failed: {type(exc).__name__}: {exc}"
                )
                self._lost.set()
                return
            if not renewed:
                self._loss_reason = "lease token no longer owns the coordination key"
                self._lost.set()
                return


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


def _validate_renew_interval(ttl_seconds: int, interval_seconds: float) -> None:
    if interval_seconds <= 0:
        raise ValueError("Lease renew interval must be greater than zero")
    if interval_seconds >= ttl_seconds:
        raise ValueError("Lease renew interval must be shorter than its TTL")


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
