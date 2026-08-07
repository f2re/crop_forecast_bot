from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.application.risk_notification_delivery import send_risk_transition_once
from src.bot.risk_alerts import format_ensemble_risk_digest
from src.domain.risk import RiskEvent, RiskOutlook
from src.domain.risk_delivery import (
    RiskEpisodeState,
    RiskStateChange,
    plan_risk_delivery,
)
from src.infrastructure.coordination import MemoryCoordination


AS_OF = date(2026, 8, 7)


def _event(
    day: int,
    *,
    level: str = "high",
    risk_type: str = "heat",
    p10: float = 28.0,
    p90: float = 38.0,
) -> RiskEvent:
    event_date = date(2026, 8, day)
    return RiskEvent(
        risk_type=risk_type,  # type: ignore[arg-type]
        event_date=event_date,
        lead_days=(event_date - AS_OF).days,
        level=level,  # type: ignore[arg-type]
        members_exceeding=24,
        valid_members=31,
        member_fraction=24 / 31,
        severe_members_exceeding=12 if level == "high" else 2,
        severe_member_fraction=(12 if level == "high" else 2) / 31,
        threshold=32.0,
        severe_threshold=35.0,
        unit="°C",
        p10=p10,
        median=(p10 + p90) / 2,
        p90=p90,
        model="gfs_seamless",
        reliability_note="test",
        action="test",
        caveat="test",
    )


def _local() -> datetime:
    return datetime(2026, 8, 7, 6, tzinfo=ZoneInfo("Europe/Moscow"))


def _outlook(events: tuple[RiskEvent, ...]) -> RiskOutlook:
    return RiskOutlook(
        available=True,
        status="accepted",
        events=events,
        model="gfs_seamless",
        member_count=31,
        forecast_days=16,
        valid_days=16,
        incomplete_days=0,
        generated_for_date=AS_OF,
    )


def test_far_heat_end_22_to_13_august_is_silent() -> None:
    previous = (
        RiskEpisodeState(
            risk_type="heat",
            start_date=date(2026, 8, 7),
            end_date=date(2026, 8, 22),
            highest_level="high",
        ),
    )
    current = tuple(_event(day) for day in range(7, 14))

    decision = plan_risk_delivery(
        current,
        mode="immediate",
        local_datetime=_local(),
        previous_state=previous,
    )

    assert decision.changes == ()
    assert decision.events == ()
    assert decision.dedup_token is None
    assert decision.current_state == previous


def test_period_end_becomes_relevant_only_inside_72_hours() -> None:
    previous = (
        RiskEpisodeState(
            risk_type="heat",
            start_date=date(2026, 8, 7),
            end_date=date(2026, 8, 22),
            highest_level="high",
        ),
    )
    current = tuple(_event(day) for day in range(7, 11))

    decision = plan_risk_delivery(
        current,
        mode="immediate",
        local_datetime=_local(),
        previous_state=previous,
    )

    assert len(decision.changes) == 1
    assert decision.changes[0].current[0].end_date == date(2026, 8, 10)
    assert decision.dedup_token is not None
    assert decision.dedup_token.startswith("confirmable-transition:")


def test_high_risk_four_days_away_does_not_push() -> None:
    decision = plan_risk_delivery(
        (_event(11),),
        mode="immediate",
        local_datetime=_local(),
    )

    assert decision.changes == ()
    assert decision.events == ()
    assert decision.current_state == ()


def test_high_risk_today_is_marked_urgent() -> None:
    decision = plan_risk_delivery(
        (_event(7), _event(8)),
        mode="immediate",
        local_datetime=_local(),
    )

    assert decision.dedup_token is not None
    assert decision.dedup_token.startswith("urgent-transition:")


@pytest.mark.asyncio
async def test_routine_transition_requires_stability_interval() -> None:
    now = [0.0]
    coordination = MemoryCoordination(
        namespace="notification-stability",
        clock=lambda: now[0],
    )
    sends: list[str] = []

    async def sender() -> object:
        sends.append("sent")
        return object()

    kwargs = dict(
        coordination=coordination,
        transition_key=(
            "notification:weather-risk-transition:1:2:"
            "confirmable-transition:abc"
        ),
        transition_ttl_seconds=21 * 24 * 60 * 60,
        reservation_ttl_seconds=5 * 60,
        sender=sender,
    )
    try:
        first = await send_risk_transition_once(**kwargs)
        assert first == "deferred_daily"
        assert sends == []

        now[0] += 3 * 60 * 60
        too_soon = await send_risk_transition_once(**kwargs)
        assert too_soon == "deferred_daily"
        assert sends == []

        now[0] += 2 * 60 * 60
        confirmed = await send_risk_transition_once(**kwargs)
        assert confirmed == "sent"
        assert sends == ["sent"]

        repeated = await send_risk_transition_once(**kwargs)
        assert repeated == "already_delivered"
        assert sends == ["sent"]
    finally:
        await coordination.close()


@pytest.mark.asyncio
async def test_urgent_transition_skips_confirmation_hold() -> None:
    coordination = MemoryCoordination(namespace="urgent-notification")
    sends: list[str] = []

    async def sender() -> object:
        sends.append("sent")
        return object()

    try:
        outcome = await send_risk_transition_once(
            coordination,
            transition_key=(
                "notification:weather-risk-transition:1:2:"
                "urgent-transition:abc"
            ),
            transition_ttl_seconds=21 * 24 * 60 * 60,
            reservation_ttl_seconds=5 * 60,
            sender=sender,
        )
        assert outcome == "sent"
        assert sends == ["sent"]
    finally:
        await coordination.close()


def test_push_card_hides_far_heat_tail() -> None:
    events = tuple(_event(day) for day in range(7, 23))
    change = RiskStateChange(
        risk_type="heat",
        previous=(),
        current=(
            RiskEpisodeState(
                risk_type="heat",
                start_date=date(2026, 8, 7),
                end_date=date(2026, 8, 22),
                highest_level="high",
            ),
        ),
    )

    text = format_ensemble_risk_digest(
        events,
        _outlook(events),
        field_name="Основное поле",
        crop="tomato",
        crops=("tomato",),
        phase="Завязывание плодов",
        delivery_mode="immediate",
        priority_bypass=False,
        changes=(change,),
    )

    assert "Ближайшие 3 суток" in text
    assert "7–10 августа" in text
    assert "22 августа" not in text
    assert "Что изменилось" not in text
    assert "Погода требует внимания" not in text
