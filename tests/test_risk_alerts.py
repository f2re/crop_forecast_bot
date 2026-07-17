from datetime import date

from src.bot.risk_alerts import format_ensemble_risk_alert
from src.domain.risk import RiskEvent, RiskOutlook


def test_alert_explains_raw_fraction_and_hail_limit() -> None:
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
        valid_days=16,
        generated_for_date=date(2026, 7, 17),
    )

    text = format_ensemble_risk_alert(
        event,
        outlook,
        field_name="Поле 1",
        crop="wheat",
        phase="Колошение",
    )

    assert "22 из 31" in text
    assert "сырая доля модельных сценариев" in text
    assert "не прогноз града" in text
    assert "через 12 сут." in text
