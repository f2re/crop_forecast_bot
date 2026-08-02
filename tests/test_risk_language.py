from datetime import date

from src.bot.risk_language import (
    crop_context_lines,
    format_risk_period,
    group_risk_events,
)
from src.domain.risk import RiskEvent


def _heat_event(day: int, lead_days: int, members: int = 28) -> RiskEvent:
    return RiskEvent(
        risk_type="heat",
        event_date=date(2026, 8, day),
        lead_days=lead_days,
        level="high",
        members_exceeding=members,
        valid_members=31,
        member_fraction=members / 31,
        severe_members_exceeding=20,
        severe_member_fraction=20 / 31,
        threshold=32.0,
        severe_threshold=35.0,
        unit="°C, Tmax воздуха 2 м",
        p10=31.5,
        median=34.0,
        p90=37.5,
        model="gfs_seamless",
        reliability_note="test",
        action="Проверьте влагу и перенесите чувствительные работы.",
        caveat="Порог зависит от культуры и фазы.",
    )


def test_consecutive_hazard_days_are_grouped_into_period() -> None:
    periods = group_risk_events(
        (
            _heat_event(2, 0),
            _heat_event(3, 1),
            _heat_event(5, 3),
        )
    )

    assert len(periods) == 2
    assert periods[0].start_date == date(2026, 8, 2)
    assert periods[0].end_date == date(2026, 8, 3)
    assert periods[1].start_date == date(2026, 8, 5)

    text = format_risk_period(periods[0])
    assert "Жара: 2–3 августа" in text
    assert "28 из 31 вариантов модели" in text
    assert "основной разброс вариантов" in text
    assert "Приоритет" in text
    assert "%" not in text
    assert "пересекли" not in text


def test_far_signal_is_planning_information_not_call_to_act_now() -> None:
    period = group_risk_events((_heat_event(14, 12),))[0]

    text = format_risk_period(period)

    assert "дальний сигнал" in text
    assert "только предварительное планирование" in text
    assert "готовиться сейчас" not in text
    assert "устойчивый сигнал" not in text


def test_multiple_crop_context_does_not_claim_crop_damage() -> None:
    lines = crop_context_lines(
        crops=("tomato", "potato"),
        selected_crop="tomato",
        phase="Цветение",
    )
    text = "\n".join(lines)

    assert "Томат" in text
    assert "Картофель" in text
    assert "Погодные условия общие для точки" in text
    assert "повреждение каждой культуры отдельно не рассчитано" in text
    assert "Фаза выбранной культуры" in text
