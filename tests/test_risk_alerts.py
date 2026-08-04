from datetime import date

from src.bot.risk_alerts import format_ensemble_risk_alert
from src.domain.risk import RiskEvent, RiskOutlook


def test_alert_is_compact_actionable_and_hides_model_internals() -> None:
    event = RiskEvent(
        risk_type="convection",
        event_date=date(2026, 7, 29),
        lead_days=12,
        level="elevated",
        members_exceeding=22,
        valid_members=31,
        member_fraction=22 / 31,
        severe_members_exceeding=8,
        severe_member_fraction=8 / 31,
        threshold=1000.0,
        severe_threshold=2000.0,
        unit="Дж/кг, CAPE max",
        p10=100.0,
        median=1400.0,
        p90=2600.0,
        model="gfs_seamless",
        reliability_note="дальний срок",
        action="Следите за предупреждениями.",
        caveat="Это не прогноз града.",
    )
    outlook = RiskOutlook(
        available=True,
        status="risk",
        events=(event,),
        model="gfs_seamless",
        member_count=31,
        forecast_days=16,
        valid_days=15,
        incomplete_days=1,
        generated_for_date=date(2026, 7, 17),
    )

    text = format_ensemble_risk_alert(
        event,
        outlook,
        field_name="Поле 1",
        crop="tomato",
        crops=("tomato", "potato"),
        phase="Цветение",
    )

    assert "Погода: Поле 1" in text
    assert "🟡" in text
    assert "Неустойчивая атмосфера — наблюдать" in text
    assert "не прогноз грозы" in text
    assert "Следите за официальными предупреждениями и радаром" in text
    assert "Томат, Картофель" in text
    assert "22 из 31" not in text
    assert "согласованность" not in text
    assert "не откалиброванная вероятность" not in text
    assert "Надёжность" not in text
    assert "15 из 16" not in text
    assert len(text) < 500
