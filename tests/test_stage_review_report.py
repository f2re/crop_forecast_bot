from datetime import date, datetime, timezone

from src.bot.report_presentation import compact_agro_report


REPORT = """🌾 <b>Агрометеорологический отчёт</b>
🗺 Поле: <b>Основное поле</b>
🌱 Культура: <b>Томат</b>
📅 Начало сезона/посев: 10.05.2026
🌿 Фаза: <b>Завязывание плодов</b> — указана пользователем

✅ <b>Что происходит:</b> в валидной прогнозной Tmin общий температурный риск по заданной политике не выявлен
• Проверено прогнозных суток: 7

💧 <b>Осадки и атмосферная испаряемость</b>
• Накопленные осадки с начала сезона: 120.0 мм по 85 валидным суткам.

🌱 <b>Теплообеспеченность</b>
• ГДД с начала сезона: 920.0°C·сут при Tbase=10.0°C
• Прогнозный прирост за 7 сут.: 110.0°C·сут
"""


def test_compact_report_uses_explicit_date_meaning_and_stage_review() -> None:
    text = compact_agro_report(
        REPORT,
        season_start_date=date(2026, 5, 10),
        today=date(2026, 8, 3),
        source="Open-Meteo",
        crop_key="tomato",
        current_phase="Завязывание плодов",
        date_basis="transplanting",
        phase_confirmed_at=datetime(2026, 7, 10, 10, tzinfo=timezone.utc),
        timezone_name="Europe/Simferopol",
    )

    assert "📅 Высадка рассады: 10.05.2026" in text
    assert "Стадия подтверждена <b>24 сут.</b> назад" in text
    assert "следующая стадия: <b>Плодоношение</b>" in text
    assert "календарное напоминание" in text
    assert "вероятность" not in text
    assert "стадия автоматически изменена" not in text


def test_recent_observation_is_not_repeated_as_warning() -> None:
    text = compact_agro_report(
        REPORT,
        season_start_date=date(2026, 5, 10),
        today=date(2026, 8, 3),
        crop_key="tomato",
        current_phase="Завязывание плодов",
        date_basis="transplanting",
        phase_confirmed_at=datetime(2026, 7, 30, 10, tzinfo=timezone.utc),
        timezone_name="Europe/Simferopol",
    )

    assert "следующая стадия" not in text
    assert "календарное напоминание" not in text


def test_missing_stage_requests_observation_without_guessing() -> None:
    text = compact_agro_report(
        REPORT.replace(
            "🌿 Фаза: <b>Завязывание плодов</b> — указана пользователем",
            "🌿 Фаза: не указана; автоматически не определяется",
        ),
        season_start_date=date(2026, 5, 10),
        today=date(2026, 8, 3),
        crop_key="tomato",
        current_phase=None,
        date_basis="transplanting",
        phase_confirmed_at=None,
        timezone_name="Europe/Simferopol",
    )

    assert "Фактическая стадия ещё не подтверждена" in text
    assert "Плодоношение" not in text
