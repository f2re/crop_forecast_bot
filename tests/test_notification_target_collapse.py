from __future__ import annotations

from src.database.notification_targets import (
    EnabledNotificationTarget,
    collapse_weather_notification_targets,
)


def _target(
    field_id: int,
    name: str,
    *,
    crop: str,
    latitude: float = 55.75,
    longitude: float = 37.62,
    mode: str = "immediate",
    phase: str | None = None,
) -> EnabledNotificationTarget:
    return EnabledNotificationTarget(
        telegram_id=1001,
        field_id=field_id,
        field_name=name,
        latitude=latitude,
        longitude=longitude,
        timezone="Europe/Moscow",
        elevation_m=150.0,
        elevation_source="test",
        selected_crop=crop,
        season_start_date=None,
        phenological_phase=phase,
        daily_digest_enabled=False,
        frost_alerts_enabled=True,
        risk_delivery_mode=mode,  # type: ignore[arg-type]
        quiet_hours_start=22,
        quiet_hours_end=7,
        crop_keys=(crop,),
        field_ids=(field_id,),
        field_names=(name,),
    )


def test_duplicate_coordinate_cards_create_one_weather_target() -> None:
    collapsed = collapse_weather_notification_targets(
        [
            _target(8, "Картофель", crop="potato", phase="Бутонизация"),
            _target(3, "Пшеница", crop="wheat", phase="Колошение"),
        ]
    )

    assert len(collapsed) == 1
    target = collapsed[0]
    assert target.field_id == 3
    assert target.field_ids == (3, 8)
    assert target.field_names == ("Пшеница", "Картофель")
    assert target.field_name == "Пшеница / Картофель"
    assert target.crop_keys == ("wheat", "potato")
    assert target.phenological_phase is None


def test_coordinate_rounding_only_collapses_copied_location() -> None:
    collapsed = collapse_weather_notification_targets(
        [
            _target(1, "Точка 1", crop="wheat"),
            _target(
                2,
                "Точка 2",
                crop="potato",
                latitude=55.750004,
                longitude=37.620004,
            ),
            _target(
                3,
                "Отдельное поле",
                crop="corn",
                latitude=55.751,
                longitude=37.621,
            ),
        ]
    )

    assert len(collapsed) == 2
    assert collapsed[0].field_ids == (1, 2)
    assert collapsed[1].field_ids == (3,)


def test_different_delivery_policies_remain_separate() -> None:
    collapsed = collapse_weather_notification_targets(
        [
            _target(1, "Сразу", crop="wheat", mode="immediate"),
            _target(2, "Сводка", crop="wheat", mode="digest"),
        ]
    )

    assert len(collapsed) == 2
    assert {target.risk_delivery_mode for target in collapsed} == {
        "immediate",
        "digest",
    }
