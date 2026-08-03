from datetime import date, datetime, timedelta, timezone

from src.application.soil_temperature import (
    SoilTemperatureDay,
    SoilTemperatureReport,
)
from src.bot.handlers.soil_temperature import (
    format_soil_temperature_help,
    format_soil_temperature_report,
)


def _report() -> SoilTemperatureReport:
    forecast = tuple(
        SoilTemperatureDay(
            local_date=date(2026, 4, 3) + timedelta(days=offset),
            mean_c=12.0 + offset,
            minimum_c=8.0 + offset,
            maximum_c=16.0 + offset,
            source="Open-Meteo ECMWF Best Match, температура почвы 0–7 см",
        )
        for offset in range(7)
    )
    return SoilTemperatureReport(
        latest_completed=SoilTemperatureDay(
            local_date=date(2026, 4, 2),
            mean_c=11.0,
            minimum_c=7.0,
            maximum_c=15.0,
            source="Open-Meteo ECMWF Best Match, температура почвы 0–7 см",
        ),
        recent_mean_c=10.0,
        recent_change_c=1.2,
        recent_days=3,
        forecast=forecast,
        timezone="Europe/Moscow",
        source="Open-Meteo ECMWF Best Match, температура почвы 0–7 см",
        model="ecmwf_best_match",
        depth_label="модельный слой почвы 0–7 см",
        retrieved_at=datetime(2026, 4, 3, 16, 16, tzinfo=timezone.utc),
        spatial_resolution_km=None,
        coverage_start=date(2026, 3, 20),
        coverage_end=date(2026, 4, 9),
        notes=(),
    )


def test_soil_temperature_message_is_compact_and_explicitly_modelled() -> None:
    text = format_soil_temperature_report(_report(), field_name="Основное поле")

    assert "🌡 <b>Почва 0–7 см</b>" in text
    assert "<b>02.04 по модели:</b> 11.0 °C (7.0…15.0)" in text
    assert "За 3 дня: потепление на 1.2 °C." in text
    assert text.count("\n• ") == 5
    assert "• 07.04–09.04: около 17.0 °C" in text
    assert "Последние завершённые сутки" not in text
    assert "Как читать" not in text
    assert "Модель, не датчик" in text
    assert "ECMWF через Open-Meteo · 03.04 19:16 MSK" in text


def test_soil_temperature_help_explains_provenance_and_use() -> None:
    text = format_soil_temperature_help()

    assert "ECMWF IFS через Open-Meteo" in text
    assert "до 4 раз в сутки" in text
    assert "архив модели, а не измерение метеостанции" in text
    assert "9–25 км" in text
    assert "измерить почву на рабочей глубине" in text
