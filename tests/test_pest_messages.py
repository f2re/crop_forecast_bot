from datetime import date

import pandas as pd

from src.agro.pest_phenology import calculate_pest_outlook
from src.bot.pest_messages import format_pest_help, format_pest_outlook
from src.domain.pests import get_pest_model


def test_air_pest_help_explains_formula_and_rejects_treatment_claim() -> None:
    text = format_pest_help(get_pest_model("colorado_potato_beetle"))

    assert "(Tмакс + Tмин) / 2" in text
    assert "11,1" in text
    assert "первая найденная кладка яиц" in text
    assert "экономический порог" in text
    assert "не назначает препарат" in text


def test_soil_pest_help_names_driver_and_exact_method() -> None:
    text = format_pest_help(get_pest_model("seedcorn_maggot_soil"))

    assert "модельного слоя почвы 0–7 см" in text
    assert "3.9 °C" in text
    assert "29.0 °C" in text
    assert "одна условная синусоида" in text
    assert "горизонтальным отсечением" in text
    assert "1 января" in text
    assert "не назначает препарат" in text


def test_pest_outlook_is_an_observation_window_not_presence_forecast() -> None:
    rows = []
    for day_number in range(1, 5):
        day = date(2026, 6, day_number)
        rows.append(
            {
                "date": pd.Timestamp(day, tz="UTC"),
                "local_date": day.isoformat(),
                "t_min": 11.1,
                "t_max": 51.1,
                "data_kind": "operational_past",
            }
        )
    outlook = calculate_pest_outlook(
        pd.DataFrame(rows),
        "colorado_potato_beetle",
        biofix_date=date(2026, 6, 1),
        today=date(2026, 6, 5),
    )
    text = format_pest_outlook(
        outlook,
        field_name="Поле 1",
        crop_key="potato",
        source="test",
    )

    assert "окно осмотра" in text
    assert "не прогноз наличия" in text
    assert "необходимости обработки" in text
    assert "пропусков: 0" in text
