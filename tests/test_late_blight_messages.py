from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.bot.handlers.markers import _catalog_keyboard, _late_blight_keyboard
from src.bot.late_blight_messages import format_potato_late_blight_screening
from src.domain.late_blight import (
    LateBlightDayAssessment,
    LateBlightNightMoistureAssessment,
    LateBlightOutlook,
    LateBlightPeriod,
)


def _outlook(*, with_period: bool = True) -> LateBlightOutlook:
    days = (
        LateBlightDayAssessment(
            local_date=date(2026, 8, 4),
            data_kind="forecast",
            expected_hours=24,
            valid_hours=24,
            minimum_temperature_c=11.2,
            humid_hours=7,
            complete=True,
            qualifies=True,
        ),
        LateBlightDayAssessment(
            local_date=date(2026, 8, 5),
            data_kind="forecast",
            expected_hours=24,
            valid_hours=24,
            minimum_temperature_c=10.4,
            humid_hours=8,
            complete=True,
            qualifies=True,
        ),
    )
    periods = (
        LateBlightPeriod(
            start_date=date(2026, 8, 4),
            end_date=date(2026, 8, 5),
            day_count=2,
            data_kind="forecast",
        ),
    ) if with_period else ()
    zone = ZoneInfo("Europe/Moscow")
    night_moisture = (
        LateBlightNightMoistureAssessment(
            night_date=date(2026, 8, 5),
            data_kind="forecast",
            start_local=datetime(2026, 8, 4, 19, tzinfo=zone),
            end_local=datetime(2026, 8, 5, 7, tzinfo=zone),
            night_hours=12,
            valid_temperature_humidity_hours=12,
            preceding_day_maximum_temperature_c=24.0,
            night_minimum_temperature_c=10.4,
            day_to_night_drop_c=13.6,
            maximum_relative_humidity_percent=98.0,
            minimum_dewpoint_depression_c=0.4,
            near_saturation_hours=8,
            fog_hours=2,
            precipitation_hours=1,
            optional_moisture_data_available=True,
        ),
    )
    return LateBlightOutlook(
        available=True,
        status=(
            "критерии Hutton выполнены"
            if with_period
            else "порог выполнен только за отдельные сутки"
        ),
        criteria_name="Hutton Criteria",
        days=days,
        periods=periods,
        timezone="Europe/Moscow",
        source="Open-Meteo Forecast API",
        model="best_match",
        retrieved_at=datetime(2026, 8, 3, 12, tzinfo=timezone.utc),
        night_moisture=night_moisture,
    )


def test_report_is_explicit_about_weather_screen_and_limits() -> None:
    text = format_potato_late_blight_screening(
        _outlook(),
        field_name="Основное <поле>",
    )

    assert "Фитофтороз картофеля — погодное окно" in text
    assert "Условия по критериям Hutton выполнены" in text
    assert "04.08–05.08" in text
    assert "Tmin 11.2 °C" in text
    assert "RH ≥90 % — 7 ч" in text
    assert "Ночное увлажнение — поясняющий контекст" in text
    assert "падение T 13.6 °C" in text
    assert "туман/видимость &lt;1 км 2 ч" in text
    assert "не является триггером" in text
    assert "не измерение увлажнения листа" in text
    assert "не доказывает заражение" in text
    assert "не назначает препарат, срок или дозу" in text
    assert "Основное &lt;поле&gt;" in text
    assert len(text) < 4096


def test_report_does_not_contain_direct_treatment_prescription() -> None:
    text = format_potato_late_blight_screening(
        _outlook(),
        field_name="Картофель",
    ).casefold()

    forbidden = (
        "опрыскать",
        "обработать препаратом",
        "норма препарата",
        "доза препарата",
        "фунгицид обязателен",
    )
    assert all(fragment not in text for fragment in forbidden)


def test_potato_biological_section_exposes_screening_button_only_for_potato() -> None:
    potato = _catalog_keyboard(section="biological", crop_key="potato")
    tomato = _catalog_keyboard(section="biological", crop_key="tomato")

    potato_callbacks = {
        button.callback_data
        for row in potato.inline_keyboard
        for button in row
        if button.callback_data is not None
    }
    tomato_callbacks = {
        button.callback_data
        for row in tomato.inline_keyboard
        for button in row
        if button.callback_data is not None
    }

    assert "late_blight:potato" in potato_callbacks
    assert "late_blight:potato" not in tomato_callbacks


def test_unknown_or_greenhouse_scope_cannot_enable_or_recalculate() -> None:
    keyboard = _late_blight_keyboard(enabled=False, open_field=False)
    callbacks = {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data is not None
    }

    assert "crop_growth_context" in callbacks
    assert "late_blight:enable" not in callbacks
    assert "late_blight:potato" not in callbacks


def test_paused_legacy_monitor_can_still_be_disabled() -> None:
    keyboard = _late_blight_keyboard(enabled=True, open_field=False)
    callbacks = {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data is not None
    }

    assert "late_blight:disable" in callbacks
    assert "late_blight:potato" not in callbacks
