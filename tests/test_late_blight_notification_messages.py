from __future__ import annotations

from datetime import date, datetime, timezone

from src.bot.late_blight_notification_messages import (
    format_late_blight_change_notification,
)
from src.domain.late_blight import LateBlightOutlook
from src.domain.late_blight_delivery import plan_late_blight_delivery


def _outlook(periods) -> LateBlightOutlook:
    return LateBlightOutlook(
        available=True,
        status="критерии Hutton выполнены",
        criteria_name="Hutton Criteria",
        days=(),
        periods=periods,
        timezone="UTC",
        source="Open-Meteo Forecast API",
        model="best_match",
        retrieved_at=datetime(2026, 8, 3, 12, tzinfo=timezone.utc),
    )


def test_notification_explains_weather_window_without_treatment_advice() -> None:
    from src.domain.late_blight import LateBlightPeriod

    period = LateBlightPeriod(
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 8),
        day_count=4,
        data_kind="forecast",
    )
    decision = plan_late_blight_delivery(
        (period,),
        previous_state=None,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=datetime(2026, 8, 3, 12, tzinfo=timezone.utc),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    text = format_late_blight_change_notification(
        decision,
        _outlook((period,)),
        field_name="Картофельное поле",
    )

    assert "Появилось новое погодное окно" in text
    assert "05.08–08.08" in text
    assert "не подтверждает наличие возбудителя" in text
    assert "необходимость обработки" in text
    assert "доза" not in text.casefold()
    assert len(text) < 4096
