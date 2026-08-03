"""Typed contracts for source-backed biological-risk integration candidates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RiskKind = Literal["disease", "pest"]
IntegrationReadiness = Literal[
    "published_contract",
    "operational_external_model",
    "regional_signal_required",
    "legacy_model_review",
    "weather_screening_only",
]
SourceStatus = Literal[
    "current_operational_tool",
    "current_guidance",
    "published_model",
    "legacy_tool",
    "suspended_service",
]


@dataclass(frozen=True, slots=True)
class BiologicalRiskCandidate:
    """One candidate contract; this object never enables an alert by itself."""

    key: str
    name_ru: str
    scientific_name: str
    kind: RiskKind
    crop_keys: tuple[str, ...]
    readiness: IntegrationReadiness
    weather_inputs: tuple[str, ...]
    required_context: tuple[str, ...]
    permitted_output: str
    source_title: str
    source_urls: tuple[str, ...]
    source_status: SourceStatus
    validation_note: str


def candidate(
    key: str,
    name_ru: str,
    scientific_name: str,
    kind: RiskKind,
    crop_keys: tuple[str, ...],
    readiness: IntegrationReadiness,
    weather_inputs: tuple[str, ...],
    required_context: tuple[str, ...],
    permitted_output: str,
    source_title: str,
    source_urls: tuple[str, ...],
    source_status: SourceStatus,
    validation_note: str,
) -> BiologicalRiskCandidate:
    return BiologicalRiskCandidate(
        key=key,
        name_ru=name_ru,
        scientific_name=scientific_name,
        kind=kind,
        crop_keys=crop_keys,
        readiness=readiness,
        weather_inputs=weather_inputs,
        required_context=required_context,
        permitted_output=permitted_output,
        source_title=source_title,
        source_urls=source_urls,
        source_status=source_status,
        validation_note=validation_note,
    )
