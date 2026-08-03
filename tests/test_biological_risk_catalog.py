from __future__ import annotations

from src.agro.crop_catalog import CROPS
from src.domain.biological_risks import (
    CANDIDATES_BY_KEY,
    EVIDENCE_GAPS,
    INTEGRATION_CANDIDATES,
    candidates_for_crop,
    validate_biological_risk_catalog,
)
from src.domain.pests import PEST_MODELS


def test_biological_risk_catalog_is_valid_and_keys_are_unique() -> None:
    validate_biological_risk_catalog()
    assert len(CANDIDATES_BY_KEY) == len(INTEGRATION_CANDIDATES)
    assert len(INTEGRATION_CANDIDATES) >= 45


def test_every_supported_crop_has_candidates_or_explicit_evidence_gap() -> None:
    covered = {
        crop_key
        for candidate in INTEGRATION_CANDIDATES
        for crop_key in candidate.crop_keys
    }
    gaps = set(EVIDENCE_GAPS)

    assert covered.isdisjoint(gaps)
    assert set(CROPS) == covered | gaps
    assert gaps == {"millet", "buckwheat", "mustard", "clover", "timothy"}


def test_existing_production_pest_models_are_not_duplicated_as_candidates() -> None:
    assert set(PEST_MODELS).isdisjoint(CANDIDATES_BY_KEY)


def test_legacy_or_suspended_sources_are_never_marked_as_published_contracts() -> None:
    for candidate in INTEGRATION_CANDIDATES:
        if candidate.source_status in {"legacy_tool", "suspended_service"}:
            assert candidate.readiness != "published_contract"


def test_host_specific_models_are_not_silently_transferred() -> None:
    onion_thrips = CANDIDATES_BY_KEY["onion_thrips_green_onion"]
    squash_bug = CANDIDATES_BY_KEY["squash_bug_summer_squash"]
    cucurbit_scab = CANDIDATES_BY_KEY["cucurbit_scab"]

    assert onion_thrips.crop_keys == ("onion",)
    assert "зелён" in onion_thrips.validation_note
    assert squash_bug.crop_keys == ("zucchini",)
    assert "watermelon" not in cucurbit_scab.crop_keys


def test_crop_lookup_returns_only_declared_links() -> None:
    sunflower_keys = {item.key for item in candidates_for_crop("sunflower")}
    mustard_keys = {item.key for item in candidates_for_crop("mustard")}

    assert {
        "sunflower_stem_weevil",
        "sunflower_beetle",
        "sunflower_moth",
    }.issubset(sunflower_keys)
    assert mustard_keys == set()


def test_candidates_do_not_contain_direct_treatment_prescriptions() -> None:
    forbidden = (
        "доза препарата",
        "норма препарата",
        "опрыскать",
        "обработать препаратом",
        "обязательно обработать",
    )
    for candidate in INTEGRATION_CANDIDATES:
        text = " ".join(
            (
                candidate.permitted_output,
                candidate.validation_note,
            )
        ).casefold()
        assert all(fragment not in text for fragment in forbidden)
