from src.bot.alerts import format_frost_alert, format_frost_data_unavailable


def test_frost_alert_uses_daily_date_and_escapes_user_values() -> None:
    text = format_frost_alert(
        {
            "date_local": "11.07.2026",
            "t_min": -1.5,
            "lead_days": 1,
            "level": "critical",
            "elevation_m": 120.0,
        },
        "wheat",
        phase="<Кущение>",
        field_name="<Северное>",
    )
    assert "11.07.2026" in text
    assert "примерно через 1 сут." in text
    assert "точный час" in text
    assert "&lt;Северное&gt;" in text
    assert "&lt;Кущение&gt;" in text
    assert "критический" in text


def test_frost_unavailable_warning_is_fail_closed_and_escaped() -> None:
    text = format_frost_data_unavailable(
        "<Северное>",
        "Tmin <не получена>",
    )

    assert "Температурный риск не оценён" in text
    assert "Отсутствие данных не означает отсутствие заморозка" in text
    assert "&lt;Северное&gt;" in text
    assert "Tmin &lt;не получена&gt;" in text
