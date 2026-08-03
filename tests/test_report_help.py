from datetime import date

from src.bot.report_help import (
    format_heat_help,
    format_htc_help,
    format_phase_help,
    format_sources_help,
    format_water_help,
)


def test_tomato_heat_help_shows_exact_daily_average_example() -> None:
    text = format_heat_help("tomato")

    assert "базовая температура <b>10.0 °C</b>" in text
    assert "max(0, (Tмакс + Tмин) / 2 − Tбаза)" in text
    assert "Tмакс=28 °C" in text
    assert "Tмин=16 °C" in text
    assert "<b>12.0 °C·сут</b>" in text
    assert "не измерение роста растения" in text
    assert "точную стадию развития" in text


def test_water_help_does_not_turn_climatic_difference_into_irrigation_dose() -> None:
    text = format_water_help()

    assert "суточная сумма дождя" in text
    assert "Текущий день и прогноз не входят" in text
    assert "не заменяются нулём" in text
    assert "эталонное испарение" in text
    assert "не означает, что нужно полить ровно" in text
    assert "менее 1 мм" in text


def test_htc_help_contains_formula_and_reproducible_example() -> None:
    text = format_htc_help()

    assert "ГТК = 10 × сумма осадков / сумма средних температур" in text
    assert "выше 10 °C" in text
    assert "10 × 80 / 1000 = 0,80" in text
    assert "не выдаёт универсальный диагноз засухи" in text


def test_phase_help_is_a_confirmation_prompt_not_an_automatic_prediction() -> None:
    text = format_phase_help(
        "tomato",
        season_start_date=date(2026, 4, 15),
        current_phase="Завязывание плодов",
        today=date(2026, 8, 3),
    )

    assert "прошло <b>110 сут.</b>" in text
    assert "посев, всходы или высадка рассады" in text
    assert "открытый грунт или теплица" in text
    assert "не заменит наблюдение без подтверждения" in text


def test_sources_help_distinguishes_gridded_data_from_field_measurements() -> None:
    text = format_sources_help()

    assert "не являются измерением непосредственно на поле" in text
    assert "не включают текущие незавершённые сутки" in text
    assert "дождемер" in text
