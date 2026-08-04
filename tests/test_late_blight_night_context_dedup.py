from __future__ import annotations

from datetime import date, datetime, timezone

from src.domain.late_blight import LateBlightPeriod
from src.domain.late_blight_delivery import plan_late_blight_delivery


def test_delivery_identity_remains_based_on_hutton_periods_only() -> None:
    period = LateBlightPeriod(
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 8),
        day_count=4,
        data_kind="forecast",
    )
    first = plan_late_blight_delivery(
        (period,),
        previous_state=None,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=datetime(2026, 8, 3, 9, tzinfo=timezone.utc),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    repeated = plan_late_blight_delivery(
        (period,),
        previous_state=first.current_state,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=datetime(2026, 8, 3, 15, tzinfo=timezone.utc),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )

    # Dew point, fog and day-to-night drop are intentionally absent from this
    # contract. Recomputed explanatory values cannot create a new transition.
    assert first.change is not None
    assert repeated.change is None
    assert repeated.dedup_token is None
