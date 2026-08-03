from __future__ import annotations

from src.bot.marker_messages import (
    format_agrometeorological_hazards,
    format_candidate_pest_markers,
    format_marker_catalog_overview,
    format_meteorological_hazards,
    format_operational_pest_markers,
)
from src.domain.marker_catalog import (
    AGROMETEOROLOGICAL_HAZARD_REFERENCE,
    AGROMETEOROLOGICAL_HAZARDS,
    METEOROLOGICAL_HAZARDS,
    PEST_MARKERS,
    get_pest_marker,
    pest_markers_by_status,
)
from src.domain.pests import PEST_MODELS


EXPECTED_METEOROLOGICAL_CODES = tuple(f"A.{index}" for index in range(1, 21))
EXPECTED_AGROMETEOROLOGICAL_CODES = (
    *(f"A.1.{index:02d}" for index in range(1, 15)),
    *(f"A.2.{index:02d}" for index in range(1, 5)),
)


def test_meteorological_hazard_catalog_contains_the_complete_typical_list() -> None:
    assert len(METEOROLOGICAL_HAZARDS) == 20
    assert tuple(hazard.code for hazard in METEOROLOGICAL_HAZARDS) == (
        EXPECTED_METEOROLOGICAL_CODES
    )
    assert {hazard.key for hazard in METEOROLOGICAL_HAZARDS} == {
        "very_strong_wind",
        "hurricane_wind",
        "squall",
        "tornado",
        "very_heavy_rain",
        "strong_shower",
        "prolonged_heavy_rain",
        "very_heavy_snow",
        "large_hail",
        "severe_blizzard",
        "severe_dust_storm",
        "severe_fog",
        "severe_icing_deposition",
        "severe_frost",
        "severe_heat",
        "anomalously_cold_weather",
        "anomalously_hot_weather",
        "vegetation_frost",
        "extreme_fire_danger",
        "snow_avalanche",
    }


def test_agrometeorological_reference_is_complete_and_not_current_authority() -> None:
    assert len(AGROMETEOROLOGICAL_HAZARDS) == 18
    assert tuple(hazard.code for hazard in AGROMETEOROLOGICAL_HAZARDS) == (
        EXPECTED_AGROMETEOROLOGICAL_CODES
    )
    assert AGROMETEOROLOGICAL_HAZARD_REFERENCE.status == (
        "expired_experimental_reference"
    )
    assert "до 01.01.2022" in AGROMETEOROLOGICAL_HAZARD_REFERENCE.status_note


def test_catalog_keys_and_codes_are_unique() -> None:
    hazards = (*METEOROLOGICAL_HAZARDS, *AGROMETEOROLOGICAL_HAZARDS)
    source_codes = {(hazard.source_key, hazard.code) for hazard in hazards}
    assert len(source_codes) == len(hazards)
    assert len({hazard.key for hazard in hazards}) == len(hazards)
    assert len({marker.key for marker in PEST_MARKERS}) == len(PEST_MARKERS)


def test_each_pest_model_has_an_implemented_weather_driver() -> None:
    for model in PEST_MODELS.values():
        markers = tuple(get_pest_marker(key) for key in model.marker_keys)
        assert any(
            marker.role == "weather_driver" and marker.status == "implemented"
            for marker in markers
        )
        assert all(marker.status != "candidate_unlinked" for marker in markers)
        assert "degree_day_accumulation" in model.marker_keys
        assert "continuous_completed_series" in model.marker_keys
        assert "forecast_separation" in model.marker_keys


def test_unvalidated_candidate_markers_are_not_linked_to_crops() -> None:
    linked = {
        marker_key
        for model in PEST_MODELS.values()
        for marker_key in model.marker_keys
    }
    candidates = {
        marker.key for marker in pest_markers_by_status("candidate_unlinked")
    }
    assert candidates
    assert candidates.isdisjoint(linked)


def test_air_and_soil_models_declare_different_weather_drivers() -> None:
    assert "air_daily_temperature" in PEST_MODELS[
        "colorado_potato_beetle"
    ].marker_keys
    assert "air_daily_temperature" in PEST_MODELS["black_cutworm"].marker_keys
    assert "soil_temperature_0_to_7cm" in PEST_MODELS[
        "seedcorn_maggot_soil"
    ].marker_keys
    assert "air_daily_temperature" not in PEST_MODELS[
        "seedcorn_maggot_soil"
    ].marker_keys


def test_telegram_catalog_sections_are_compact_and_cautious() -> None:
    sections = (
        format_marker_catalog_overview(),
        format_meteorological_hazards(),
        format_agrometeorological_hazards(),
        format_operational_pest_markers(),
        format_candidate_pest_markers(),
    )
    for text in sections:
        assert 0 < len(text) < 4096

    overview = sections[0]
    assert "не присваивает явлению официальный статус ОЯ" in overview
    assert "Кандидаты" in sections[4]
    assert "автоматически" not in sections[4].casefold() or (
        "не включает" in sections[4]
    )
    assert "до 01.01.2022" in sections[2]
