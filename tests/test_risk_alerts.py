from datetime import date

from src.bot.risk_alerts import (
    format_ensemble_risk_alert,
    format_ensemble_risk_digest,
)
from src.domain.risk import RiskEvent, RiskOutlook
from src.domain.risk_delivery import RiskEpisodeState, RiskStateChange


def _event() -> RiskEvent:
    return RiskEvent(
        risk_type="convection",
        event_date=date(2026, 7, 19),
        lead_days=2,
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
        reliability_note="ближайшие дни",
        action="Следите за предупреждениями.",
        caveat="Это не прогноз града.",
    )


def _outlook(*events: RiskEvent) -> RiskOutlook:
    return RiskOutlook(
        available=True,
        status="risk",
        events=events,
        model="gfs_seamless",
        member_count=31,
        forecast_days=16,
        valid_days=15,
        incomplete_days=1,
        generated_for_date=date(2026, 7, 17),
    )


def test_alert_is_compact_calm_and_hides_model_internals() -> None:
    event = _event()
    text = format_ensemble_risk_alert(
        event,
        _outlook(event),
        field_name="Поле 1",
        crop="tomato",
        crops=("tomato", "potato"),
        phase="Цветение",
    )

    assert "Погода: Поле 1" in text
    assert "Погода требует внимания" not in text
    assert "🟠" in text
    assert "Возможны грозовые условия — лучше подготовиться" in text
    assert "не самостоятельный прогноз грозы" in text
    assert "Стоит закрепить оборудование" in text
    assert "Томат, Картофель" in text
    assert "22 из 31" not in text
    assert "Надёжность" not in text
    assert len(text) < 520


def test_withdrawn_heat_is_reported_as_forecast_improvement() -> None:
    change = RiskStateChange(
        risk_type="heat",
        previous=(
            RiskEpisodeState(
                risk_type="heat",
                start_date=date(2026, 8, 5),
                end_date=date(2026, 8, 8),
                highest_level="high",
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

    assert text.startswith("✅")
    assert "Прогноз улучшился" in text
    assert "жара" in text
    assert "больше не ожидаются" in text
    assert "обычному контролю" in text
    assert "Действие:" not in text
