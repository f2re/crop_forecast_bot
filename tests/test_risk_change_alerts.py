from datetime import date

from src.bot.risk_alerts import format_ensemble_risk_digest
from src.domain.risk import RiskEvent, RiskOutlook
from src.domain.risk_delivery import RiskEpisodeState, RiskStateChange


def _event(event_date: date) -> RiskEvent:
    return RiskEvent(
        risk_type="heat",
        event_date=event_date,
        lead_days=2,
        level="elevated",
        members_exceeding=18,
        valid_members=31,
        member_fraction=18 / 31,
        severe_members_exceeding=3,
        severe_member_fraction=3 / 31,
        threshold=32.0,
        severe_threshold=35.0,
        unit="°C",
        p10=30.0,
        median=34.0,
        p90=37.0,
        model="gfs_seamless",
        reliability_note="средний срок",
        action="Проверьте влажность почвы.",
        caveat="Общий тепловой скрининг.",
    )


def _outlook(*events: RiskEvent) -> RiskOutlook:
    return RiskOutlook(
        available=True,
        status="accepted",
        events=events,
        model="gfs_seamless",
        member_count=31,
        forecast_days=10,
        valid_days=10,
        incomplete_days=0,
        generated_for_date=date(2026, 8, 3),
    )


def test_digest_explains_heat_extension() -> None:
    events = tuple(_event(date(2026, 8, day)) for day in range(5, 11))
    change = RiskStateChange(
        risk_type="heat",
        previous=(
            RiskEpisodeState(
                risk_type="heat",
                start_date=date(2026, 8, 5),
                end_date=date(2026, 8, 8),
                highest_level="elevated",
            ),
        ),
        current=(
            RiskEpisodeState(
                risk_type="heat",
                start_date=date(2026, 8, 5),
                end_date=date(2026, 8, 10),
                highest_level="elevated",
            ),
        ),
    )

    text = format_ensemble_risk_digest(
        events,
        _outlook(*events),
        field_name="Южное",
        crop="wheat",
        phase="Колошение",
        delivery_mode="immediate",
        priority_bypass=False,
        changes=(change,),
    )

    assert "Что изменилось" in text
    assert "продлится дольше" in text
    assert "до 10 августа вместо 8 августа" in text
    assert "не создают повторное сообщение" in text


def test_digest_explains_cleared_future_heat_once() -> None:
    change = RiskStateChange(
        risk_type="heat",
        previous=(
            RiskEpisodeState(
                risk_type="heat",
                start_date=date(2026, 8, 5),
                end_date=date(2026, 8, 8),
                highest_level="elevated",
            ),
        ),
        current=(),
    )

    text = format_ensemble_risk_digest(
        (),
        _outlook(),
        field_name="Южное",
        crop="wheat",
        phase=None,
        delivery_mode="immediate",
        priority_bypass=False,
        changes=(change,),
    )

    assert "ранее ожидавшийся период" in text
    assert "больше не подтверждается" in text
    assert "выше порога больше не подтверждаются" in text
    assert "модель не указана" not in text
