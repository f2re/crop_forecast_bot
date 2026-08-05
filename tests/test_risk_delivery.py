from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.domain.risk import RiskEvent
from src.domain.risk_delivery import (
    RiskEpisodeState,
    is_quiet_time,
    plan_risk_delivery,
    quiet_hours_label,
    validate_quiet_hours,
    validate_risk_delivery_mode,
)


def _event(
    *,
    risk_type: str = "heavy_rain",
    event_date: date = date(2026, 10, 27),
    level: str = "elevated",
    fraction: float = 0.35,
    p10: float = 1.0,
    median: float = 20.0,
    p90: float = 55.0,
) -> RiskEvent:
    valid_members = 31
    members = round(valid_members * fraction)
    lead_days = max(0, (event_date - date(2026, 10, 25)).days)
    return RiskEvent(
        risk_type=risk_type,  # type: ignore[arg-type]
        event_date=event_date,
        lead_days=lead_days,
        level=level,  # type: ignore[arg-type]
        members_exceeding=members,
        valid_members=valid_members,
        member_fraction=fraction,
        severe_members_exceeding=0,
        severe_member_fraction=0.0,
        threshold=30.0,
        severe_threshold=50.0,
        unit="мм/сут",
        p10=p10,
        median=median,
        p90=p90,
        model="gfs_seamless",
        reliability_note="средний срок",
        action="Проверьте водоотвод.",
        caveat="Скрининг модельной ячейки.",
    )


def _local(hour: int, *, day: int = 25, fold: int = 0) -> datetime:
    return datetime(
        2026,
        10,
        day,
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


def test_watch_signal_is_history_only_and_never_pushed() -> None:
    decision = plan_risk_delivery(
        (_event(level="watch", fraction=0.20),),
        mode="immediate",
        local_datetime=_local(10),
    )

    assert decision.events == ()
    assert decision.changes == ()
    assert decision.current_state == ()
    assert decision.dedup_token is None


def test_far_elevated_and_far_high_signals_are_not_introduced() -> None:
    elevated = _event(event_date=date(2026, 11, 3), level="elevated")
    high = _event(
        risk_type="strong_wind",
        event_date=date(2026, 11, 3),
        level="high",
        fraction=0.70,
    )

    decision = plan_risk_delivery(
        (elevated, high),
        mode="immediate",
        local_datetime=_local(10),
    )

    assert decision.events == ()
    assert decision.changes == ()
    assert decision.current_state == ()


def test_near_elevated_change_is_deferred_during_quiet_hours() -> None:
    decision = plan_risk_delivery(
        (_event(),),
        mode="immediate",
        local_datetime=_local(23),
        quiet_hours_start=22,
        quiet_hours_end=7,
    )

    assert decision.deferred is True
    assert decision.events == ()
    assert decision.current_state == ()


def test_only_immediate_new_high_bypasses_quiet_hours() -> None:
    high = _event(
        event_date=date(2026, 10, 26),
        level="high",
        fraction=0.70,
    )
    elevated = _event(
        risk_type="strong_wind",
        event_date=date(2026, 10, 26),
        level="elevated",
        fraction=0.40,
    )

    urgent = plan_risk_delivery(
        (high, elevated),
        mode="immediate",
        local_datetime=_local(23),
        quiet_hours_start=22,
        quiet_hours_end=7,
    )

    assert urgent.deferred is False
    assert urgent.events == (high,)
    assert urgent.priority_bypass is True
    assert tuple(episode.risk_type for episode in urgent.current_state) == (
        "heavy_rain",
    )

    after_quiet = plan_risk_delivery(
        (high, elevated),
        mode="immediate",
        local_datetime=_local(8),
        previous_state=urgent.current_state,
        quiet_hours_start=22,
        quiet_hours_end=7,
    )
    assert after_quiet.priority_bypass is False
    assert after_quiet.events == (elevated,)


def test_high_two_days_away_respects_quiet_hours() -> None:
    high = _event(
        event_date=date(2026, 10, 27),
        level="high",
        fraction=0.70,
    )
    decision = plan_risk_delivery(
        (high,),
        mode="immediate",
        local_datetime=_local(23),
        quiet_hours_start=22,
        quiet_hours_end=7,
    )

    assert decision.deferred is True
    assert decision.priority_bypass is False


def test_daily_digest_has_separate_transition_and_local_day_tokens() -> None:
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
    assert decision.dedup_token is not None
    assert decision.daily_quota_token == "daily:2026-07-19"
    assert decision.priority_bypass is False


def test_high_only_mode_filters_lower_periods() -> None:
    high = _event(
        event_date=date(2026, 7, 21),
        level="high",
        fraction=0.65,
    )
    elevated = _event(
        risk_type="strong_wind",
        event_date=date(2026, 7, 21),
        level="elevated",
        fraction=0.40,
    )
    decision = plan_risk_delivery(
        (elevated, high),
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


def test_fraction_and_value_noise_do_not_repeat_the_same_period() -> None:
    local_now = datetime(2026, 7, 19, 10, tzinfo=ZoneInfo("Europe/Moscow"))
    first_events = tuple(
        _event(
            risk_type="heat",
            event_date=date(2026, 7, 21) + timedelta(days=offset),
            fraction=0.35,
            p10=31.0,
            median=34.0,
            p90=37.0,
        )
        for offset in range(4)
    )
    first = plan_risk_delivery(
        first_events,
        mode="immediate",
        local_datetime=local_now,
    )
    second_events = tuple(
        _event(
            risk_type="heat",
            event_date=date(2026, 7, 21) + timedelta(days=offset),
            fraction=0.58,
            p10=29.0,
            median=31.0,
            p90=34.0,
        )
        for offset in range(4)
    )
    second = plan_risk_delivery(
        second_events,
        mode="immediate",
        local_datetime=local_now,
        previous_state=first.current_state,
    )

    assert first.dedup_token is not None
    assert second.changes == ()
    assert second.events == ()
    assert second.dedup_token is None
    assert second.current_state == first.current_state


def test_one_day_period_noise_is_silent_and_keeps_notified_baseline() -> None:
    local_now = datetime(2026, 7, 19, 10, tzinfo=ZoneInfo("Europe/Moscow"))
    previous = (
        RiskEpisodeState(
            risk_type="heat",
            start_date=date(2026, 7, 21),
            end_date=date(2026, 7, 24),
            highest_level="elevated",
        ),
    )
    events = tuple(
        _event(
            risk_type="heat",
            event_date=date(2026, 7, 21) + timedelta(days=offset),
        )
        for offset in range(5)
    )

    decision = plan_risk_delivery(
        events,
        mode="immediate",
        local_datetime=local_now,
        previous_state=previous,
    )

    assert decision.changes == ()
    assert decision.dedup_token is None
    assert decision.current_state == previous


def test_cumulative_two_day_extension_creates_one_update() -> None:
    local_now = datetime(2026, 7, 19, 10, tzinfo=ZoneInfo("Europe/Moscow"))
    previous = (
        RiskEpisodeState(
            risk_type="heat",
            start_date=date(2026, 7, 21),
            end_date=date(2026, 7, 24),
            highest_level="elevated",
        ),
    )
    events = tuple(
        _event(
            risk_type="heat",
            event_date=date(2026, 7, 21) + timedelta(days=offset),
        )
        for offset in range(6)
    )

    decision = plan_risk_delivery(
        events,
        mode="immediate",
        local_datetime=local_now,
        previous_state=previous,
    )

    assert len(decision.changes) == 1
    assert decision.changes[0].current[0].end_date == date(2026, 7, 26)
    assert decision.dedup_token is not None


def test_one_day_earlier_move_is_material_when_it_enters_near_term_band() -> None:
    local_now = datetime(2026, 7, 19, 10, tzinfo=ZoneInfo("Europe/Moscow"))
    previous = (
        RiskEpisodeState(
            risk_type="heat",
            start_date=date(2026, 7, 23),
            end_date=date(2026, 7, 24),
            highest_level="elevated",
        ),
    )
    events = (
        _event(risk_type="heat", event_date=date(2026, 7, 22)),
        _event(risk_type="heat", event_date=date(2026, 7, 23)),
        _event(risk_type="heat", event_date=date(2026, 7, 24)),
    )

    decision = plan_risk_delivery(
        events,
        mode="immediate",
        local_datetime=local_now,
        previous_state=previous,
    )

    assert len(decision.changes) == 1
    assert decision.changes[0].current[0].start_date == date(2026, 7, 22)


def test_level_change_is_material_even_with_same_dates() -> None:
    local_now = datetime(2026, 7, 19, 10, tzinfo=ZoneInfo("Europe/Moscow"))
    previous = (
        RiskEpisodeState(
            risk_type="heat",
            start_date=date(2026, 7, 21),
            end_date=date(2026, 7, 22),
            highest_level="elevated",
        ),
    )
    events = (
        _event(
            risk_type="heat",
            event_date=date(2026, 7, 21),
            level="high",
            fraction=0.70,
        ),
        _event(
            risk_type="heat",
            event_date=date(2026, 7, 22),
            level="high",
            fraction=0.70,
        ),
    )

    decision = plan_risk_delivery(
        events,
        mode="immediate",
        local_datetime=local_now,
        previous_state=previous,
    )

    assert len(decision.changes) == 1
    assert decision.changes[0].current[0].highest_level == "high"


def test_unselected_hazard_type_remains_pending_in_baseline() -> None:
    local_now = datetime(2026, 7, 19, 10, tzinfo=ZoneInfo("Europe/Moscow"))
    rain = _event(event_date=date(2026, 7, 21))
    wind = _event(risk_type="strong_wind", event_date=date(2026, 7, 22))

    first = plan_risk_delivery(
        (rain, wind),
        mode="immediate",
        local_datetime=local_now,
        max_events=1,
    )
    second = plan_risk_delivery(
        (rain, wind),
        mode="immediate",
        local_datetime=local_now,
        previous_state=first.current_state,
        max_events=1,
    )

    assert tuple(change.risk_type for change in first.changes) == ("heavy_rain",)
    assert tuple(change.risk_type for change in second.changes) == ("strong_wind",)


def test_elapsed_first_day_is_not_a_forecast_change() -> None:
    previous = (
        RiskEpisodeState(
            risk_type="heat",
            start_date=date(2026, 10, 25),
            end_date=date(2026, 10, 29),
            highest_level="elevated",
        ),
    )
    current_events = tuple(
        _event(
            risk_type="heat",
            event_date=date(2026, 10, 26) + timedelta(days=offset),
        )
        for offset in range(4)
    )

    decision = plan_risk_delivery(
        current_events,
        mode="immediate",
        local_datetime=_local(10, day=26),
        previous_state=previous,
    )

    assert decision.changes == ()
    assert decision.dedup_token is None


def test_removed_future_heat_creates_one_clear_update() -> None:
    previous = (
        RiskEpisodeState(
            risk_type="heat",
            start_date=date(2026, 10, 27),
            end_date=date(2026, 10, 31),
            highest_level="elevated",
        ),
    )

    decision = plan_risk_delivery(
        (),
        mode="immediate",
        local_datetime=_local(10),
        previous_state=previous,
    )

    assert len(decision.changes) == 1
    assert decision.changes[0].current == ()
    assert decision.events == ()
    assert decision.current_state == ()
    assert decision.dedup_token is not None


def test_legacy_watch_baseline_is_removed_without_clear_notification() -> None:
    previous = (
        RiskEpisodeState(
            risk_type="strong_wind",
            start_date=date(2026, 10, 27),
            end_date=date(2026, 10, 28),
            highest_level="watch",
        ),
    )

    decision = plan_risk_delivery(
        (),
        mode="immediate",
        local_datetime=_local(10),
        previous_state=previous,
    )

    assert decision.changes == ()
    assert decision.current_state == ()
    assert decision.dedup_token is None


def test_delivery_mode_validation_rejects_unknown_value() -> None:
    assert validate_risk_delivery_mode("digest") == "digest"
    with pytest.raises(ValueError, match="Неизвестный"):
        validate_risk_delivery_mode("everything")
