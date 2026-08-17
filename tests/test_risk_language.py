from datetime import date

from src.bot.risk_language import (
    crop_context_lines,
    format_risk_period,
    group_risk_events,
)
from src.domain.risk import RiskEvent


def _event(
    *,
    risk_type: str = "heat",
    day: int,
    lead_days: int,
    level: str = "high",
    members: int = 28,
    p10: float = 31.5,
    median: float = 34.0,
    p90: float = 37.5,
) -> RiskEvent:
    return RiskEvent(
        risk_type=risk_type,  # type: ignore[arg-type]
        event_date=date(2026, 8, day),
        lead_days=lead_days,
        level=level,  # type: ignore[arg-type]
        members_exceeding=members,
        valid_members=31,
        member_fraction=members / 31,
        severe_members_exceeding=20 if level == "high" else 0,
        severe_member_fraction=20 / 31 if level == "high" else 0.0,
        threshold=15.0 if risk_type == "strong_wind" else 32.0,
        severe_threshold=20.0 if risk_type == "strong_wind" else 35.0,
        unit="м/с" if risk_type == "strong_wind" else "°C",
        p10=p10,
        median=median,
        p90=p90,
        model="gfs_seamless",
        reliability_note="test",
        action="Техническая длинная рекомендация не должна попадать в сообщение.",
        caveat="Техническое ограничение не должно попадать в сообщение.",
    )


def test_consecutive_hazard_days_are_grouped_into_period() -> None:
    periods = group_risk_events(
        (
            _event(day=2, lead_days=0),
            _event(day=3, lead_days=1),
            _event(day=5, lead_days=3),
        )
    )

    assert len(periods) == 2
    text = format_risk_period(periods[0])
    assert "🔴" in text
    assert "Сильная жара — подготовьтесь сегодня" in text
    assert "2–3 августа" in text
    assert "31.5–37.5 °C" in text
    assert "Что лучше сделать:" in text
    assert "вариант" not in text
    assert "Надёжность" not in text
    assert "Действие:" not in text


def test_weak_wind_signal_is_human_and_non_alarmist_in_manual_view() -> None:
    period = group_risk_events(
        (
            _event(
                risk_type="strong_wind",
                day=7,
                lead_days=3,
                level="watch",
                members=5,
                p10=9.0,
                median=11.8,
                p90=15.2,
            ),
        )
    )[0]

    text = format_risk_period(period)

    assert "🟡" in text
    assert "Сильные порывы ветра — срочных действий нет" in text
    assert "7 августа · порывы 9–15.2 м/с" in text
    assert "Проверьте прогноз перед опрыскиванием" in text
    assert "5 из 31" not in text
    assert len(text) < 260


def test_far_signal_is_observation_not_call_to_act_now() -> None:
    period = group_risk_events((_event(day=14, lead_days=12),))[0]

    text = format_risk_period(period)
    assert "🟡" in text
    assert "срочных действий нет" in text
    assert "подготовьтесь сегодня" not in text


def test_convection_card_hides_cape_and_does_not_claim_thunderstorm_or_hail() -> None:
    period = group_risk_events(
        (
            _event(
                risk_type="convection",
                day=8,
                lead_days=1,
                level="elevated",
                members=22,
                p10=100.0,
                median=1400.0,
                p90=2600.0,
            ),
        )
    )[0]

    text = format_risk_period(period)
    assert "Условия для развития грозовых облаков — подготовьтесь заранее" in text
    assert "Гроза и град этим расчётом не подтверждены" in text
    assert "официальное предупреждение и радар" in text
    assert "CAPE" not in text
    assert "Дж/кг" not in text


def test_crop_context_is_compact() -> None:
    lines = crop_context_lines(
        crops=("tomato", "potato"),
        selected_crop="tomato",
        phase="Цветение",
    )
    assert lines == [
        "🌱 Томат, Картофель",
        "🌿 Томат: <b>Цветение</b>",
    ]
