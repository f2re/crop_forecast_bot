from __future__ import annotations

import pytest

from src.application.risk_notification_delivery import send_risk_transition_once
from src.infrastructure.coordination import MemoryCoordination


class RecordingSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def __call__(self) -> object:
        self.calls += 1
        if self.fail:
            raise RuntimeError("telegram unavailable")
        return object()


@pytest.mark.asyncio
async def test_transition_and_daily_quota_have_distinct_meanings() -> None:
    coordination = MemoryCoordination(namespace="risk-delivery-test")
    first = RecordingSender()
    repeated = RecordingSender()
    later_change = RecordingSender()
    next_day = RecordingSender()
    try:
        outcome = await send_risk_transition_once(
            coordination,
            transition_key="transition:heat-5-9",
            transition_ttl_seconds=3600,
            reservation_ttl_seconds=60,
            daily_quota_key="daily:2026-08-03",
            daily_quota_ttl_seconds=1800,
            sender=first,
        )
        repeated_outcome = await send_risk_transition_once(
            coordination,
            transition_key="transition:heat-5-9",
            transition_ttl_seconds=3600,
            reservation_ttl_seconds=60,
            daily_quota_key="daily:2026-08-03",
            daily_quota_ttl_seconds=1800,
            sender=repeated,
        )
        deferred_outcome = await send_risk_transition_once(
            coordination,
            transition_key="transition:heat-5-11",
            transition_ttl_seconds=3600,
            reservation_ttl_seconds=60,
            daily_quota_key="daily:2026-08-03",
            daily_quota_ttl_seconds=1800,
            sender=later_change,
        )
        next_day_outcome = await send_risk_transition_once(
            coordination,
            transition_key="transition:heat-5-11",
            transition_ttl_seconds=3600,
            reservation_ttl_seconds=60,
            daily_quota_key="daily:2026-08-04",
            daily_quota_ttl_seconds=1800,
            sender=next_day,
        )
    finally:
        await coordination.close()

    assert outcome == "sent"
    assert repeated_outcome == "already_delivered"
    assert deferred_outcome == "deferred_daily"
    assert next_day_outcome == "sent"
    assert first.calls == 1
    assert repeated.calls == 0
    assert later_change.calls == 0
    assert next_day.calls == 1


@pytest.mark.asyncio
async def test_failed_send_releases_transition_and_daily_reservations() -> None:
    coordination = MemoryCoordination(namespace="risk-delivery-failure")
    failing = RecordingSender(fail=True)
    retry = RecordingSender()
    try:
        with pytest.raises(RuntimeError, match="telegram unavailable"):
            await send_risk_transition_once(
                coordination,
                transition_key="transition:rain-new",
                transition_ttl_seconds=3600,
                reservation_ttl_seconds=60,
                daily_quota_key="daily:2026-08-03",
                daily_quota_ttl_seconds=1800,
                sender=failing,
            )
        outcome = await send_risk_transition_once(
            coordination,
            transition_key="transition:rain-new",
            transition_ttl_seconds=3600,
            reservation_ttl_seconds=60,
            daily_quota_key="daily:2026-08-03",
            daily_quota_ttl_seconds=1800,
            sender=retry,
        )
    finally:
        await coordination.close()

    assert failing.calls == 1
    assert outcome == "sent"
    assert retry.calls == 1


def test_delivery_ttl_validation_is_fail_closed() -> None:
    async def sender() -> object:
        return object()

    coordination = MemoryCoordination(namespace="risk-delivery-validation")

    async def run() -> None:
        with pytest.raises(ValueError, match="must exceed"):
            await send_risk_transition_once(
                coordination,
                transition_key="transition:test",
                transition_ttl_seconds=60,
                reservation_ttl_seconds=60,
                sender=sender,
            )
        await coordination.close()

    import asyncio

    asyncio.run(run())
