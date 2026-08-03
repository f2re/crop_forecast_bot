from __future__ import annotations

from datetime import date, datetime, timezone

from src.bot.handlers.markers import _catalog_keyboard
from src.bot.late_blight_messages import format_potato_late_blight_screening
from src.domain.late_blight import (
    LateBlightDayAssessment,
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
    assert "модельной сетки на высоте 2 м" in text
    assert "не увлажнение листа и не диагноз" in text
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
