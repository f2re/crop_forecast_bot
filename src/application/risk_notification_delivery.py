from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Literal

from src.infrastructure.coordination import CoordinationBackend, Lease

logger = logging.getLogger(__name__)

RiskSendOutcome = Literal["sent", "already_delivered", "deferred_daily"]

# Routine transitions must remain stable across scheduler cycles. The candidate
# survives long enough for several GFS cycles, while the minimum-age key prevents
# an immediate retry of the same forecast run from masquerading as confirmation.
_CONFIRMATION_TTL_SECONDS = 18 * 60 * 60
_CONFIRMATION_MIN_AGE_SECONDS = 4 * 60 * 60
_CONFIRMABLE_MARKER = "confirmable-transition:"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def was_notified_on_local_date(
    last_notified_at: datetime | None,
    local_datetime: datetime,
) -> bool:
    """Check a stored UTC timestamp against the field's local calendar date."""

    if last_notified_at is None:
        return False
    if local_datetime.tzinfo is None or local_datetime.utcoffset() is None:
        raise ValueError("local_datetime must be timezone-aware")
    return (
        _aware_utc(last_notified_at).astimezone(local_datetime.tzinfo).date()
        == local_datetime.date()
    )


def accepted_notification_time(
    outcome: RiskSendOutcome,
    *,
    now: datetime,
) -> datetime | None:
    """Return a durable notification timestamp for accepted transitions."""

    if outcome == "deferred_daily":
        return None
    return _aware_utc(now)


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


async def _routine_transition_is_confirmed(
    coordination: CoordinationBackend,
    transition_key: str,
) -> bool:
    """Require a routine semantic transition to survive for several hours.

    The first observation creates a long-lived candidate and a short minimum-age
    key. A retry while the short key still exists remains silent. Once the
    minimum-age key expires, the same semantic transition is considered stable.

    Urgent transitions are encoded with a different token prefix and therefore
    never enter this gate.
    """

    if _CONFIRMABLE_MARKER not in transition_key:
        return True

    candidate_key = f"{transition_key}:candidate"
    minimum_age_key = f"{transition_key}:minimum-age"
    candidate_lease = await coordination.acquire(
        candidate_key,
        _CONFIRMATION_TTL_SECONDS,
    )
    minimum_age_lease = await coordination.acquire(
        minimum_age_key,
        _CONFIRMATION_MIN_AGE_SECONDS,
    )

    if candidate_lease is not None:
        # First observation. Both leases intentionally remain committed by their
        # acquisition TTLs; no Telegram side effect and no baseline advance.
        return False

    if minimum_age_lease is None:
        # Same semantic transition was seen again too soon. This includes an
        # accidental/manual rerun of the same model cycle.
        return False

    # Candidate existed and the minimum age elapsed. The newly acquired short
    # lease is no longer needed; releasing it keeps Telegram-send retries safe if
    # the downstream call fails.
    await _release_safely(coordination, minimum_age_lease)
    return True


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
    """Send one stable semantic transition under an optional local-day quota.

    Normal weather transitions marked ``confirmable-transition`` are first held
    as candidates. The same transition must still be present after the minimum
    confirmation interval before Telegram is called. Urgent high-risk tokens skip
    this gate.

    ``deferred_daily`` is retained as the existing compatibility outcome for any
    transition that must remain pending without advancing the PostgreSQL
    last-notified baseline. It therefore covers both daily quota deferral and the
    confirmation hold.
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

    if not await _routine_transition_is_confirmed(coordination, transition_key):
        return "deferred_daily"

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
