from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.domain.risk import RiskEvent
from src.domain.risk_delivery import (
    is_quiet_time,
    plan_risk_delivery,
    quiet_hours_label,
    validate_quiet_hours,
    validate_risk_delivery_mode,
)


def _event(
    *,
    risk_type: str = "heavy_rain",
    event_date: date = date(2026, 7, 21),
    level: str = "elevated",
    fraction: float = 0.35,
) -> RiskEvent:
    valid_members = 31
    members = round(valid_members * fraction)
    return RiskEvent(
        risk_type=risk_type,  # type: ignore[arg-type]
        event_date=event_date,
        lead_days=2,
        level=level,  # type: ignore[arg-type]
        members_exceeding=members,
        valid_members=valid_members,
        member_fraction=fraction,
        severe_members_exceeding=0,
        severe_member_fraction=0.0,
        threshold=30.0,
        severe_threshold=50.0,
        unit="мм/сут",
        p10=1.0,
        median=20.0,
        p90=55.0,
        model="gfs_seamless",
        reliability_note="средний срок",
        action="Проверьте водоотвод.",
        caveat="Скрининг модельной ячейки.",
    )


def _local(hour: int, *, fold: int = 0) -> datetime:
    return datetime(
        2026,
        10,
        25,
        hour,
        tzinfo=ZoneInfo("Europe/Berlin"),
        fold=fold,
    )


def test_quiet_hours_cross_midnight_use_local_wall_clock() -> None:
    assert is_quiet_time(_local(23), 22, 7) is True
    assert is_quiet_time(_local(2, fold=0), 22, 7) is True
    assert is_quiet_time(_local(2, fold=1), 22, 7) is True
    assert is_quiet_time(_local(6), 22, 7) is True
    assert is_quiet_time(_local(7), 22, 7) is False
    assert is_quiet_time(_local(21), 22, 7) is False
    assert quiet_hours_label(22, 7) == "22:00–07:00"


def test_quiet_hours_validation_is_fail_closed() -> None:
    assert validate_quiet_hours(None, None) == (None, None)
    with pytest.raises(ValueError, match="задаются вместе"):
        validate_quiet_hours(22, None)
    with pytest.raises(ValueError, match="не должны совпадать"):
        validate_quiet_hours(7, 7)
    with pytest.raises(ValueError, match="диапазоне"):
        validate_quiet_hours(-1, 7)


def test_watch_or_elevated_signal_is_deferred_during_quiet_hours() -> None:
    decision = plan_risk_delivery(
        (_event(),),
        mode="immediate",
        local_datetime=_local(23),
        quiet_hours_start=22,
        quiet_hours_end=7,
    )

    assert decision.deferred is True
    assert decision.events == ()
    assert decision.dedup_token is None


def test_high_signal_bypasses_quiet_hours_but_only_high_events_are_sent() -> None:
    high = _event(level="high", fraction=0.70)
    elevated = _event(risk_type="strong_wind", level="elevated", fraction=0.40)

    decision = plan_risk_delivery(
        (high, elevated),
        mode="immediate",
        local_datetime=_local(23),
        quiet_hours_start=22,
        quiet_hours_end=7,
    )

    assert decision.deferred is False
    assert decision.events == (high,)
    assert decision.priority_bypass is True
    assert decision.dedup_token is not None


def test_daily_digest_uses_one_local_date_token() -> None:
    local_now = datetime(2026, 7, 19, 10, tzinfo=ZoneInfo("Europe/Moscow"))
    decision = plan_risk_delivery(
        (
            _event(event_date=date(2026, 7, 21)),
            _event(risk_type="strong_wind", event_date=date(2026, 7, 22)),
        ),
        mode="digest",
        local_datetime=local_now,
    )

    assert len(decision.events) == 2
    assert decision.dedup_token == "daily:2026-07-19"
    assert decision.priority_bypass is False


def test_high_only_mode_filters_lower_levels() -> None:
    high = _event(level="high", fraction=0.65)
    watch = _event(risk_type="strong_wind", level="watch", fraction=0.20)
    decision = plan_risk_delivery(
        (watch, high),
        mode="high_only",
        local_datetime=datetime(
            2026,
            7,
            19,
            10,
            tzinfo=ZoneInfo("Europe/Moscow"),
        ),
    )

    assert decision.events == (high,)


def test_immediate_dedup_token_changes_after_ten_point_fraction_bucket() -> None:
    local_now = datetime(2026, 7, 19, 10, tzinfo=ZoneInfo("Europe/Moscow"))
    first = plan_risk_delivery(
        (_event(fraction=0.31),),
        mode="immediate",
        local_datetime=local_now,
    )
    second = plan_risk_delivery(
        (_event(fraction=0.41),),
        mode="immediate",
        local_datetime=local_now,
    )

    assert first.dedup_token != second.dedup_token


def test_delivery_mode_validation_rejects_unknown_value() -> None:
    assert validate_risk_delivery_mode("digest") == "digest"
    with pytest.raises(ValueError, match="Неизвестный"):
        validate_risk_delivery_mode("everything")
