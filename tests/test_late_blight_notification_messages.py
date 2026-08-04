from __future__ import annotations

from datetime import date, datetime, timezone

from src.bot.late_blight_notification_messages import (
    format_late_blight_change_notification,
)
from src.domain.late_blight import (
    LateBlightNightMoistureAssessment,
    LateBlightOutlook,
    LateBlightPeriod,
)
from src.domain.late_blight_delivery import plan_late_blight_delivery


def _outlook(periods) -> LateBlightOutlook:
    night = LateBlightNightMoistureAssessment(
        night_date=date(2026, 8, 6),
        data_kind="forecast",
        start_local=datetime(2026, 8, 5, 19, tzinfo=timezone.utc),
        end_local=datetime(2026, 8, 6, 7, tzinfo=timezone.utc),
        night_hours=12,
        valid_temperature_humidity_hours=12,
        preceding_day_maximum_temperature_c=24.0,
        night_minimum_temperature_c=11.0,
        day_to_night_drop_c=13.0,
        maximum_relative_humidity_percent=98.0,
        minimum_dewpoint_depression_c=0.5,
        near_saturation_hours=8,
        fog_hours=2,
        precipitation_hours=1,
        optional_moisture_data_available=True,
    )
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
        night_moisture=(night,),
    )


def test_notification_explains_weather_window_without_treatment_advice() -> None:
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
    assert "Ночной контекст" in text
    assert "почти насыщенный воздух до 8 ч/ночь" in text
    assert "падение T до 13.0 °C" in text
    assert "не отдельный триггер" in text
    assert "Резкий перепад температуры не является отдельным критерием" in text
    assert "не подтверждает наличие возбудителя" in text
    assert "необходимость обработки" in text
    assert "доза" not in text.casefold()
    assert len(text) < 4096
