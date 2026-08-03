from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from src.application.risk_notification_delivery import (
    accepted_notification_time,
    send_risk_transition_once,
    was_notified_on_local_date,
)
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


@pytest.mark.asyncio
async def test_delivery_ttl_validation_is_fail_closed() -> None:
    async def sender() -> object:
        return object()

    coordination = MemoryCoordination(namespace="risk-delivery-validation")
    try:
        with pytest.raises(ValueError, match="must exceed"):
            await send_risk_transition_once(
                coordination,
                transition_key="transition:test",
                transition_ttl_seconds=60,
                reservation_ttl_seconds=60,
                sender=sender,
            )
    finally:
        await coordination.close()


def test_persisted_utc_time_is_compared_in_field_local_date() -> None:
    moscow = ZoneInfo("Europe/Moscow")
    stored_naive_utc = datetime(2026, 8, 3, 20, 30)

    assert was_notified_on_local_date(
        stored_naive_utc,
        datetime(2026, 8, 3, 23, 45, tzinfo=moscow),
    )
    assert not was_notified_on_local_date(
        stored_naive_utc,
        datetime(2026, 8, 4, 0, 5, tzinfo=moscow),
    )


def test_local_date_comparison_is_stable_across_dst_fold() -> None:
    berlin = ZoneInfo("Europe/Berlin")
    first_0230 = datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    second_0230 = datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)

    assert was_notified_on_local_date(
        first_0230,
        datetime(2026, 10, 25, 2, 45, tzinfo=berlin, fold=0),
    )
    assert was_notified_on_local_date(
        second_0230,
        datetime(2026, 10, 25, 2, 45, tzinfo=berlin, fold=1),
    )


def test_accepted_transition_gets_durable_utc_timestamp() -> None:
    naive_now = datetime(2026, 8, 3, 12, 0)

    sent_at = accepted_notification_time("sent", now=naive_now)
    recovered_at = accepted_notification_time(
        "already_delivered",
        now=naive_now,
    )

    assert sent_at == datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    assert recovered_at == sent_at
    assert accepted_notification_time("deferred_daily", now=naive_now) is None


def test_local_date_requires_timezone_aware_reference() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        was_notified_on_local_date(
            datetime(2026, 8, 3, 12, 0),
            datetime(2026, 8, 3, 15, 0),
        )
