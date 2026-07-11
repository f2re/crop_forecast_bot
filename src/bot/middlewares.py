from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from src.infrastructure.coordination import CoordinationBackend, Lease

logger = logging.getLogger(__name__)

_CALLBACK_PROCESSING_TTL_SECONDS = 5 * 60
_CALLBACK_DELIVERY_TTL_SECONDS = 24 * 60 * 60
_CALLBACK_ACTION_TTL_SECONDS = 3


def callback_delivery_key(callback: CallbackQuery) -> str:
    """Return a stable key for one Telegram callback delivery."""
    return f"callback:delivery:{callback.id}"


def callback_action_key(callback: CallbackQuery) -> str:
    """Return a short-lived semantic key for rapid repeated button presses."""
    if callback.message is not None:
        location = f"chat:{callback.message.chat.id}:message:{callback.message.message_id}"
    elif callback.inline_message_id:
        location = f"inline:{callback.inline_message_id}"
    else:
        location = f"instance:{callback.chat_instance}"

    digest = hashlib.blake2s(
        (callback.data or "").encode("utf-8"),
        digest_size=8,
    ).hexdigest()
    return f"callback:action:{callback.from_user.id}:{location}:{digest}"


class CallbackIdempotencyMiddleware(BaseMiddleware):
    """Suppress callback redelivery and rapid duplicate actions across processes.

    The exact Telegram callback ID is retained for a day after successful
    processing. A semantic action key is retained briefly to absorb two presses
    of the same inline button that Telegram represents as different callback
    IDs. Both reservations are released if the handler raises, allowing a
    controlled retry.
    """

    def __init__(
        self,
        coordination: CoordinationBackend,
        *,
        processing_ttl_seconds: int = _CALLBACK_PROCESSING_TTL_SECONDS,
        delivery_ttl_seconds: int = _CALLBACK_DELIVERY_TTL_SECONDS,
        action_ttl_seconds: int = _CALLBACK_ACTION_TTL_SECONDS,
    ) -> None:
        self._coordination = coordination
        self._processing_ttl_seconds = processing_ttl_seconds
        self._delivery_ttl_seconds = delivery_ttl_seconds
        self._action_ttl_seconds = action_ttl_seconds

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        delivery_key = callback_delivery_key(event)
        delivery_lease = await self._coordination.acquire(
            delivery_key,
            self._processing_ttl_seconds,
        )
        if delivery_lease is None:
            await _answer_duplicate(event)
            return None

        action_key = callback_action_key(event)
        try:
            action_lease = await self._coordination.acquire(
                action_key,
                self._processing_ttl_seconds,
            )
        except BaseException:
            await self._release(delivery_lease, delivery_key)
            raise

        if action_lease is None:
            await self._renew(
                delivery_lease,
                self._delivery_ttl_seconds,
                delivery_key,
            )
            await _answer_duplicate(event)
            return None

        try:
            result = await handler(event, data)
        except BaseException:
            await self._release(action_lease, action_key)
            await self._release(delivery_lease, delivery_key)
            raise

        await self._renew(action_lease, self._action_ttl_seconds, action_key)
        await self._renew(
            delivery_lease,
            self._delivery_ttl_seconds,
            delivery_key,
        )
        return result

    async def _renew(self, lease: Lease, ttl_seconds: int, key: str) -> None:
        try:
            renewed = await self._coordination.renew(lease, ttl_seconds)
        except Exception:
            logger.exception("Failed to persist callback idempotency key %s", key)
            return
        if not renewed:
            logger.error("Callback idempotency lease was lost: %s", key)

    async def _release(self, lease: Lease, key: str) -> None:
        try:
            await self._coordination.release(lease)
        except Exception:
            logger.exception("Failed to release callback idempotency key %s", key)


async def _answer_duplicate(callback: CallbackQuery) -> None:
    with suppress(Exception):
        await callback.answer("Запрос уже обрабатывается")
