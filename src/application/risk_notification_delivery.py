from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from src.infrastructure.coordination import CoordinationBackend, Lease

logger = logging.getLogger(__name__)

RiskSendOutcome = Literal["sent", "already_delivered", "deferred_daily"]


async def _release_safely(
    coordination: CoordinationBackend,
    lease: Lease | None,
) -> None:
    if lease is None:
        return
    try:
        await coordination.release(lease)
    except Exception:
        logger.exception("Failed to release notification lease %s", lease.key)


async def _commit_safely(
    coordination: CoordinationBackend,
    lease: Lease,
    *,
    ttl_seconds: int,
) -> None:
    try:
        committed = await coordination.renew(lease, ttl_seconds)
    except Exception:
        logger.exception("Failed to persist notification lease %s", lease.key)
        return
    if not committed:
        logger.error(
            "Notification side effect completed but lease was not persisted: %s",
            lease.key,
        )


async def send_risk_transition_once(
    coordination: CoordinationBackend,
    *,
    transition_key: str,
    transition_ttl_seconds: int,
    reservation_ttl_seconds: int,
    sender: Callable[[], Awaitable[object]],
    daily_quota_key: str | None = None,
    daily_quota_ttl_seconds: int | None = None,
) -> RiskSendOutcome:
    """Send one semantic transition under an optional local-day quota.

    The transition key answers: "was this exact forecast change delivered?".
    The daily key answers: "was an ordinary digest already delivered today?".
    They must remain separate:

    * an existing transition key means the Telegram side effect was already
      accepted, so PostgreSQL may advance to the new semantic baseline;
    * an occupied daily key means this different change must remain pending for
      the next local day;
    * if the daily quota is unavailable, the short transition reservation is
      released so the same change can be retried later.
    """

    if reservation_ttl_seconds <= 0:
        raise ValueError("reservation_ttl_seconds must be positive")
    if transition_ttl_seconds <= reservation_ttl_seconds:
        raise ValueError(
            "transition_ttl_seconds must exceed reservation_ttl_seconds"
        )
    if daily_quota_key is None and daily_quota_ttl_seconds is not None:
        raise ValueError("daily_quota_ttl_seconds requires daily_quota_key")
    if daily_quota_key is not None:
        if daily_quota_ttl_seconds is None:
            raise ValueError("daily_quota_key requires daily_quota_ttl_seconds")
        if daily_quota_ttl_seconds <= reservation_ttl_seconds:
            raise ValueError(
                "daily_quota_ttl_seconds must exceed reservation_ttl_seconds"
            )

    transition_lease = await coordination.acquire(
        transition_key,
        reservation_ttl_seconds,
    )
    if transition_lease is None:
        return "already_delivered"

    daily_lease: Lease | None = None
    if daily_quota_key is not None:
        daily_lease = await coordination.acquire(
            daily_quota_key,
            reservation_ttl_seconds,
        )
        if daily_lease is None:
            await _release_safely(coordination, transition_lease)
            return "deferred_daily"

    try:
        await sender()
    except Exception:
        await _release_safely(coordination, daily_lease)
        await _release_safely(coordination, transition_lease)
        raise

    await _commit_safely(
        coordination,
        transition_lease,
        ttl_seconds=transition_ttl_seconds,
    )
    if daily_lease is not None and daily_quota_ttl_seconds is not None:
        await _commit_safely(
            coordination,
            daily_lease,
            ttl_seconds=daily_quota_ttl_seconds,
        )
    return "sent"
