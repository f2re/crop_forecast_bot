from __future__ import annotations

from datetime import date, datetime, timezone

from src.bot.late_blight_notification_messages import (
    format_late_blight_change_notification,
)
from src.domain.late_blight import LateBlightOutlook, LateBlightPeriod
from src.domain.late_blight_delivery import (
    LateBlightDeliveryState,
    LateBlightEpisodeState,
    plan_late_blight_delivery,
)


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
        night_moisture=(),
    )


def test_notification_is_short_and_does_not_repeat_methodology() -> None:
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

    assert "Погода благоприятна для фитофтороза картофеля" in text
    assert "05.08–08.08" in text
    assert "осмотрите нижние листья" in text
    assert "наличие инфекции не подтверждено" in text
    assert "Ночной контекст" not in text
    assert "Hutton" not in text
    assert "Open-Meteo" not in text
    assert "модель" not in text.casefold()
    assert len(text) < 500


def test_withdrawn_window_is_a_clear_improvement_message() -> None:
    previous = LateBlightDeliveryState(
        active_periods=(
            LateBlightEpisodeState(date(2026, 8, 5), date(2026, 8, 8)),
        ),
        withdrawn_periods=(),
        inoculum_context="unknown",
    )
    decision = plan_late_blight_delivery(
        (),
        previous_state=previous,
        inoculum_context="unknown",
        mode="immediate",
        local_datetime=datetime(2026, 8, 3, 12, tzinfo=timezone.utc),
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    text = format_late_blight_change_notification(
        decision,
        _outlook(()),
        field_name="Картофельное поле",
    )

    assert text.startswith("✅")
    assert "больше не ожидается" in text
    assert "Специальный осмотр" in text
    assert len(text) < 350
