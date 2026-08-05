from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.domain.late_blight import LateBlightPeriod
from src.domain.late_blight_delivery import (
    LateBlightDeliveryState,
    LateBlightEpisodeState,
    deserialize_late_blight_delivery_state,
    empty_late_blight_delivery_state,
    plan_late_blight_delivery,
    serialize_late_blight_delivery_state,
)


def _period(start: date, end: date) -> LateBlightPeriod:
    return LateBlightPeriod(
        start_date=start,
        end_date=end,
        day_count=(end - start).days + 1,
        data_kind="forecast",
    )


def _local(day: date, hour: int = 12) -> datetime:
    return datetime(
        day.year,
        day.month,
        day.day,
        hour,
        tzinfo=ZoneInfo("Europe/Moscow"),
    )


def test_new_period_is_delivered_once_and_natural_day_passage_is_silent() -> None:
    first = plan_late_blight_delivery(
        (_period(date(2026, 8, 5), date(2026, 8, 9)),),
        previous_state=None,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 5)),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    assert first.change is not None
    assert first.change.kind == "new"
    assert first.dedup_token is not None

    repeated = plan_late_blight_delivery(
        (_period(date(2026, 8, 5), date(2026, 8, 9)),),
        previous_state=first.current_state,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 6)),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    assert repeated.change is None
    assert repeated.silent_advance is True
    assert repeated.current_state.active_periods == (
        LateBlightEpisodeState(date(2026, 8, 6), date(2026, 8, 9)),
    )


def test_one_day_boundary_noise_is_silent_and_keeps_notified_baseline() -> None:
    previous = LateBlightDeliveryState(
        active_periods=(
            LateBlightEpisodeState(date(2026, 8, 5), date(2026, 8, 9)),
        ),
        withdrawn_periods=(),
        inoculum_context="unknown",
    )
    decision = plan_late_blight_delivery(
        (_period(date(2026, 8, 5), date(2026, 8, 10)),),
        previous_state=previous,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 5)),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )

    assert decision.change is None
    assert decision.current_state.active_periods == previous.active_periods


def test_cumulative_two_day_extension_and_shortening_are_material() -> None:
    previous = LateBlightDeliveryState(
        active_periods=(
            LateBlightEpisodeState(date(2026, 8, 5), date(2026, 8, 9)),
        ),
        withdrawn_periods=(),
        inoculum_context="unknown",
    )
    extended = plan_late_blight_delivery(
        (_period(date(2026, 8, 5), date(2026, 8, 11)),),
        previous_state=previous,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 5)),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    assert extended.change is not None
    assert extended.change.kind == "extended"

    shortened = plan_late_blight_delivery(
        (_period(date(2026, 8, 5), date(2026, 8, 7)),),
        previous_state=previous,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 5)),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    assert shortened.change is not None
    assert shortened.change.kind == "shortened"


def test_one_day_earlier_move_is_material_when_it_enters_immediate_band() -> None:
    previous = LateBlightDeliveryState(
        active_periods=(
            LateBlightEpisodeState(date(2026, 8, 7), date(2026, 8, 9)),
        ),
        withdrawn_periods=(),
        inoculum_context="unknown",
    )
    decision = plan_late_blight_delivery(
        (_period(date(2026, 8, 6), date(2026, 8, 9)),),
        previous_state=previous,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 5)),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )

    assert decision.change is not None
    assert decision.change.kind == "starts_earlier"


def test_withdrawn_period_is_remembered_and_restored_once() -> None:
    active = LateBlightDeliveryState(
        active_periods=(
            LateBlightEpisodeState(date(2026, 8, 5), date(2026, 8, 9)),
        ),
        withdrawn_periods=(),
        inoculum_context="unknown",
    )
    withdrawn = plan_late_blight_delivery(
        (),
        previous_state=active,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 5)),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    assert withdrawn.change is not None
    assert withdrawn.change.kind == "withdrawn"
    assert withdrawn.current_state.active_periods == ()
    assert withdrawn.current_state.withdrawn_periods == active.active_periods

    unchanged_clear = plan_late_blight_delivery(
        (),
        previous_state=withdrawn.current_state,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 5)),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    assert unchanged_clear.change is None

    restored = plan_late_blight_delivery(
        (_period(date(2026, 8, 5), date(2026, 8, 9)),),
        previous_state=withdrawn.current_state,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 5)),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    assert restored.change is not None
    assert restored.change.kind == "restored"
    assert restored.current_state.withdrawn_periods == ()


def test_digest_uses_local_day_quota_and_quiet_hours_defer() -> None:
    digest = plan_late_blight_delivery(
        (_period(date(2026, 8, 5), date(2026, 8, 7)),),
        previous_state=None,
        inoculum_context="unknown",
        mode="digest",
        local_datetime=_local(date(2026, 8, 5), 10),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    assert digest.daily_quota_token == "2026-08-05"
    assert digest.priority_bypass is False

    quiet = plan_late_blight_delivery(
        (_period(date(2026, 8, 5), date(2026, 8, 7)),),
        previous_state=None,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 5), 23),
        quiet_hours_start=22,
        quiet_hours_end=7,
    )
    assert quiet.deferred is True
    assert quiet.dedup_token is None


def test_confirmed_context_bypasses_quiet_only_for_immediate_window() -> None:
    previous = LateBlightDeliveryState(
        active_periods=(
            LateBlightEpisodeState(date(2026, 8, 5), date(2026, 8, 7)),
        ),
        withdrawn_periods=(),
        inoculum_context="unknown",
    )
    confirmed = plan_late_blight_delivery(
        (_period(date(2026, 8, 5), date(2026, 8, 7)),),
        previous_state=previous,
        inoculum_context="regional_alert_confirmed",
        mode="high_only",
        local_datetime=_local(date(2026, 8, 5), 23),
        quiet_hours_start=22,
        quiet_hours_end=7,
    )
    assert confirmed.change is not None
    assert confirmed.change.kind == "context_confirmed"
    assert confirmed.priority_bypass is True
    assert confirmed.deferred is False

    later_previous = LateBlightDeliveryState(
        active_periods=(
            LateBlightEpisodeState(date(2026, 8, 8), date(2026, 8, 10)),
        ),
        withdrawn_periods=(),
        inoculum_context="unknown",
    )
    later = plan_late_blight_delivery(
        (_period(date(2026, 8, 8), date(2026, 8, 10)),),
        previous_state=later_previous,
        inoculum_context="regional_alert_confirmed",
        mode="immediate",
        local_datetime=_local(date(2026, 8, 5), 23),
        quiet_hours_start=22,
        quiet_hours_end=7,
    )
    assert later.deferred is True
    assert later.priority_bypass is False


def test_high_only_silently_tracks_unknown_context() -> None:
    unknown = plan_late_blight_delivery(
        (_period(date(2026, 8, 5), date(2026, 8, 7)),),
        previous_state=empty_late_blight_delivery_state(),
        inoculum_context="unknown",
        mode="high_only",
        local_datetime=_local(date(2026, 8, 5), 12),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    assert unknown.change is None
    assert unknown.silent_advance is True
    assert unknown.current_state.active_periods


def test_delivery_state_json_round_trip_is_strict() -> None:
    state = LateBlightDeliveryState(
        active_periods=(
            LateBlightEpisodeState(date(2026, 8, 5), date(2026, 8, 7)),
        ),
        withdrawn_periods=(
            LateBlightEpisodeState(date(2026, 7, 20), date(2026, 7, 22)),
        ),
        inoculum_context="nearby_outbreak_confirmed",
    )
    assert deserialize_late_blight_delivery_state(
        serialize_late_blight_delivery_state(state)
    ) == state
