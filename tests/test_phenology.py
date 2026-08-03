from datetime import date, datetime, timezone

import pytest

from src.domain.phenology import (
    date_basis_label,
    evaluate_stage_review,
    validate_date_basis,
    validate_plant_type,
    validate_production_system,
)


def test_phenology_context_values_are_explicit() -> None:
    assert validate_date_basis("transplanting") == "transplanting"
    assert date_basis_label("transplanting") == "высадка рассады"
    assert validate_production_system("open_field") == "open_field"
    assert validate_plant_type("indeterminate") == "indeterminate"

    with pytest.raises(ValueError):
        validate_date_basis("planting")
    with pytest.raises(ValueError):
        validate_production_system("outdoor")
    with pytest.raises(ValueError):
        validate_plant_type("tall")


def test_stage_review_never_changes_stage_or_returns_probability() -> None:
    review = evaluate_stage_review(
        "tomato",
        current_phase="Завязывание плодов",
        phase_confirmed_at=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        today=date(2026, 8, 3),
        timezone_name="Europe/Simferopol",
    )

    assert review.needs_review is True
    assert review.days_since_confirmation == 24
    assert review.next_stage == "Плодоношение"
    assert review.status == "observation_stale"
    assert not hasattr(review, "probability")
    assert not hasattr(review, "suggested_stage")


def test_recent_stage_observation_does_not_trigger_review() -> None:
    review = evaluate_stage_review(
        "tomato",
        current_phase="Цветение",
        phase_confirmed_at=datetime(2026, 7, 25, 20, tzinfo=timezone.utc),
        today=date(2026, 8, 3),
        timezone_name="Europe/Simferopol",
    )

    assert review.needs_review is False
    assert review.days_since_confirmation == 8
    assert review.next_stage == "Завязывание плодов"


def test_legacy_stage_without_confirmation_time_is_requested_for_review() -> None:
    review = evaluate_stage_review(
        "potato",
        current_phase="Цветение",
        phase_confirmed_at=None,
        today=date(2026, 8, 3),
        timezone_name="UTC",
    )

    assert review.needs_review is True
    assert review.status == "confirmation_time_unknown"
    assert review.next_stage == "Клубнеобразование"


def test_confirmation_age_uses_field_local_date() -> None:
    review = evaluate_stage_review(
        "tomato",
        current_phase="Цветение",
        phase_confirmed_at=datetime(2026, 7, 20, 22, 30, tzinfo=timezone.utc),
        today=date(2026, 8, 4),
        timezone_name="Europe/Simferopol",
    )

    # 22:30 UTC is already 21 July in UTC+3.
    assert review.days_since_confirmation == 14
    assert review.needs_review is True
