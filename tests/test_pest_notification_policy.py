from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pandas as pd

from src.agro.pest_phenology import calculate_pest_outlook
from src.application.pest_notification_policy import (
    SemanticPestNotification,
    choose_semantic_pest_notification,
    pest_notification_state_key,
)
from src.bot.pest_notification_messages import format_semantic_pest_notification


def _weather_rows(
    start: date,
    values: list[tuple[float, float, str]],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp(start + timedelta(days=offset), tz="UTC"),
                "local_date": (start + timedelta(days=offset)).isoformat(),
                "t_min": t_min,
                "t_max": t_max,
                "data_kind": kind,
                "data_source": "test",
            }
            for offset, (t_min, t_max, kind) in enumerate(values)
        ]
    )


def _outlook():
    biofix = date(2026, 6, 1)
    today = date(2026, 6, 5)
    frame = _weather_rows(
        biofix,
        [
            (11.1, 51.1, "reanalysis"),
            (11.1, 51.1, "reanalysis"),
            (11.1, 51.1, "operational_past"),
            (11.1, 51.1, "operational_past"),
            (11.1, 51.1, "current_forecast"),
            (11.1, 51.1, "forecast"),
        ],
    )
    return calculate_pest_outlook(
        frame,
        "colorado_potato_beetle",
        biofix_date=biofix,
        today=today,
    ), today


def _stage_key(outlook) -> str:
    notification = choose_semantic_pest_notification(
        outlook,
        last_notified_stage=None,
        last_notified_advance=None,
        today=date(2026, 6, 5),
    )
    assert notification is not None
    assert notification.kind == "current_window"
    return notification.event_key


def test_initial_approach_is_dated_and_deduplicated_by_state() -> None:
    outlook, today = _outlook()
    stage_key = _stage_key(outlook)

    first = choose_semantic_pest_notification(
        outlook,
        last_notified_stage=stage_key,
        last_notified_advance=None,
        today=today,
    )
    assert isinstance(first, SemanticPestNotification)
    assert first.change == "initial"
    assert first.expected_date == date(2026, 6, 6)
    assert pest_notification_state_key(first).endswith(":expected:2026-06-06")

    repeated = choose_semantic_pest_notification(
        outlook,
        last_notified_stage=stage_key,
        last_notified_advance=pest_notification_state_key(first),
        today=today,
    )
    assert repeated is None


def test_two_day_shift_is_material_and_human_readable() -> None:
    outlook, today = _outlook()
    stage_key = _stage_key(outlook)
    initial = choose_semantic_pest_notification(
        outlook,
        last_notified_stage=stage_key,
        last_notified_advance=None,
        today=today,
    )
    assert isinstance(initial, SemanticPestNotification)

    later_outlook = replace(outlook, projected_crossing_date=date(2026, 6, 8))
    later = choose_semantic_pest_notification(
        later_outlook,
        last_notified_stage=stage_key,
        last_notified_advance=initial.state_key,
        today=today,
    )
    assert isinstance(later, SemanticPestNotification)
    assert later.change == "later"
    text = format_semantic_pest_notification(
        later,
        later_outlook,
        field_name="Северное",
        crop_key="potato",
    )
    assert "Срок осмотра поля сдвинулся" in text
    assert "Срочного осмотра не требуется" in text
    assert "Это ориентир для осмотра" in text


def test_one_day_shift_is_silent_but_cumulative_shift_is_reported() -> None:
    outlook, today = _outlook()
    stage_key = _stage_key(outlook)
    initial = choose_semantic_pest_notification(
        outlook,
        last_notified_stage=stage_key,
        last_notified_advance=None,
        today=today,
    )
    assert isinstance(initial, SemanticPestNotification)

    one_day_later = replace(outlook, projected_crossing_date=date(2026, 6, 7))
    assert choose_semantic_pest_notification(
        one_day_later,
        last_notified_stage=stage_key,
        last_notified_advance=initial.state_key,
        today=today,
    ) is None

    two_days_later = replace(outlook, projected_crossing_date=date(2026, 6, 8))
    material = choose_semantic_pest_notification(
        two_days_later,
        last_notified_stage=stage_key,
        last_notified_advance=initial.state_key,
        today=today,
    )
    assert isinstance(material, SemanticPestNotification)
    assert material.change == "later"


def test_one_day_earlier_move_to_today_is_material() -> None:
    outlook, today = _outlook()
    stage_key = _stage_key(outlook)
    initial = choose_semantic_pest_notification(
        outlook,
        last_notified_stage=stage_key,
        last_notified_advance=None,
        today=today,
    )
    assert isinstance(initial, SemanticPestNotification)
    assert initial.expected_date == today + timedelta(days=1)

    today_outlook = replace(outlook, projected_crossing_date=today)
    earlier = choose_semantic_pest_notification(
        today_outlook,
        last_notified_stage=stage_key,
        last_notified_advance=initial.state_key,
        today=today,
    )
    assert isinstance(earlier, SemanticPestNotification)
    assert earlier.change == "earlier"


def test_announced_window_can_be_withdrawn_and_restored() -> None:
    outlook, today = _outlook()
    stage_key = _stage_key(outlook)
    initial = choose_semantic_pest_notification(
        outlook,
        last_notified_stage=stage_key,
        last_notified_advance=None,
        today=today,
    )
    assert isinstance(initial, SemanticPestNotification)

    withdrawn_outlook = replace(outlook, projected_crossing_date=None)
    withdrawn = choose_semantic_pest_notification(
        withdrawn_outlook,
        last_notified_stage=stage_key,
        last_notified_advance=initial.state_key,
        today=today,
    )
    assert isinstance(withdrawn, SemanticPestNotification)
    assert withdrawn.change == "withdrawn"
    withdrawn_text = format_semantic_pest_notification(
        withdrawn,
        withdrawn_outlook,
        field_name="Северное",
        crop_key="potato",
    )
    assert "Плановый осмотр пока можно отложить" in withdrawn_text
    assert "больше не подтверждается" in withdrawn_text

    restored = choose_semantic_pest_notification(
        outlook,
        last_notified_stage=stage_key,
        last_notified_advance=withdrawn.state_key,
        today=today,
    )
    assert isinstance(restored, SemanticPestNotification)
    assert restored.change == "restored"
    assert "Окно осмотра снова ожидается" in format_semantic_pest_notification(
        restored,
        outlook,
        field_name="Северное",
        crop_key="potato",
    )


def test_first_reminder_stays_inside_initial_advance_window() -> None:
    outlook, today = _outlook()
    stage_key = _stage_key(outlook)
    far_outlook = replace(
        outlook,
        projected_crossing_date=today + timedelta(days=5),
    )

    assert choose_semantic_pest_notification(
        far_outlook,
        last_notified_stage=stage_key,
        last_notified_advance=None,
        today=today,
    ) is None


def test_legacy_advance_key_gets_one_date_aware_upgrade() -> None:
    outlook, today = _outlook()
    stage_key = _stage_key(outlook)
    assert outlook.next_stage is not None
    legacy_key = (
        f"{outlook.model.model_version}:{outlook.biofix_date.isoformat()}:"
        f"approaching:{outlook.next_stage.key}"
    )

    upgraded = choose_semantic_pest_notification(
        outlook,
        last_notified_stage=stage_key,
        last_notified_advance=legacy_key,
        today=today,
    )
    assert isinstance(upgraded, SemanticPestNotification)
    assert upgraded.change == "initial"
