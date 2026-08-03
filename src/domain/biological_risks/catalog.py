"""Validated source-backed catalogue of future biological-risk integrations."""
from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from src.agro.crop_catalog import CROPS, normalise_crop_key

from .field_crops import FIELD_CROP_CANDIDATES
from .forage import FORAGE_CANDIDATES
from .grains import GRAIN_CANDIDATES
from .root_vegetables import ROOT_VEGETABLE_CANDIDATES
from .types import BiologicalRiskCandidate

CATALOG_CHECKED_ON = date(2026, 8, 3)

INTEGRATION_CANDIDATES: tuple[BiologicalRiskCandidate, ...] = (
    *GRAIN_CANDIDATES,
    *FIELD_CROP_CANDIDATES,
    *ROOT_VEGETABLE_CANDIDATES,
    *FORAGE_CANDIDATES,
)
CANDIDATES_BY_KEY: dict[str, BiologicalRiskCandidate] = {
    item.key: item for item in INTEGRATION_CANDIDATES
}

# A gap means only that the reviewed open authoritative sources did not provide
# a sufficiently specific reproducible contract. It is not a claim that no
# scientific model exists anywhere.
EVIDENCE_GAPS: dict[str, str] = {
    "millet": (
        "В проверенных открытых руководствах не найден воспроизводимый "
        "видоспецифичный погодный договор для проса. Модели сорго и других "
        "злаков не переносятся автоматически."
    ),
    "buckwheat": (
        "Не найден открытый договор, где одновременно заданы точный объект, "
        "гречиха, погодные входы, точка отсчёта и проверяемые пороги."
    ),
    "mustard": (
        "Модели рапса или канолы нельзя считать моделями горчицы без отдельного "
        "источника по виду растения, вредителю и региону."
    ),
    "clover": (
        "Текущий профиль «клевер» не задаёт вид клевера. Без точного вида "
        "культуры нельзя безопасно связать опубликованную модель болезни или "
        "вредителя."
    ),
    "timothy": (
        "В проверенных открытых источниках не найден видоспецифичный "
        "погодный договор для тимофеевки с порогами и точкой отсчёта."
    ),
}

_ALLOWED_SOURCE_HOSTS = frozenset(
    {
        "cropprotectionnetwork.org",
        "newa.cornell.edu",
        "www.newa.cornell.edu",
        "ipm.ucanr.edu",
        "www.ndsu.edu",
        "www.ag.ndsu.edu",
        "extension.umn.edu",
        "www.ars.usda.gov",
        "ssl.acesag.auburn.edu",
        "www.knowledgebank.irri.org",
        "www.canolacouncil.org",
        "www.gov.mb.ca",
        "cdm.ipmpipe.org",
    }
)
_FORBIDDEN_RECOMMENDATION_FRAGMENTS = (
    "доза препарата",
    "норма препарата",
    "опрыскать",
    "обработать препаратом",
    "обязательно обработать",
)


def candidates_for_crop(crop_key: str) -> tuple[BiologicalRiskCandidate, ...]:
    key = normalise_crop_key(crop_key)
    return tuple(
        sorted(
            (item for item in INTEGRATION_CANDIDATES if key in item.crop_keys),
            key=lambda item: (item.kind, item.name_ru.casefold(), item.key),
        )
    )


def evidence_gap_for_crop(crop_key: str) -> str | None:
    return EVIDENCE_GAPS.get(normalise_crop_key(crop_key))


def _validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Источник должен использовать HTTPS: {url}")
    if parsed.hostname not in _ALLOWED_SOURCE_HOSTS:
        raise ValueError(f"Непроверенный домен источника: {url}")


def validate_biological_risk_catalog() -> None:
    if len(CANDIDATES_BY_KEY) != len(INTEGRATION_CANDIDATES):
        raise ValueError("Ключи кандидатов биологических рисков должны быть уникальны")

    supported_crops = set(CROPS)
    covered_crops: set[str] = set()
    for item in INTEGRATION_CANDIDATES:
        if not item.key or not item.name_ru or not item.scientific_name:
            raise ValueError("Кандидат должен иметь ключ, название и научное имя")
        if not item.crop_keys:
            raise ValueError(f"Кандидат {item.key} не связан ни с одной культурой")
        unknown_crops = set(item.crop_keys).difference(supported_crops)
        if unknown_crops:
            raise ValueError(
                f"Кандидат {item.key} содержит неизвестные культуры: "
                + ", ".join(sorted(unknown_crops))
            )
        covered_crops.update(item.crop_keys)
        if not item.weather_inputs or not item.required_context:
            raise ValueError(f"Кандидат {item.key} не описывает входы и контекст")
        if not item.source_urls:
            raise ValueError(f"Кандидат {item.key} не содержит источника")
        for source_url in item.source_urls:
            _validate_source_url(source_url)
        if item.readiness == "published_contract" and item.source_status in {
            "legacy_tool",
            "suspended_service",
        }:
            raise ValueError(
                f"Кандидат {item.key} ошибочно помечен готовым при устаревшем "
                "или приостановленном источнике"
            )
        combined_text = " ".join(
            (
                item.permitted_output,
                item.validation_note,
            )
        ).casefold()
        if any(
            fragment in combined_text
            for fragment in _FORBIDDEN_RECOMMENDATION_FRAGMENTS
        ):
            raise ValueError(
                f"Кандидат {item.key} содержит недопустимую рекомендацию обработки"
            )

    gap_crops = set(EVIDENCE_GAPS)
    unknown_gaps = gap_crops.difference(supported_crops)
    if unknown_gaps:
        raise ValueError(
            "Пробелы доказательной базы содержат неизвестные культуры: "
            + ", ".join(sorted(unknown_gaps))
        )
    overlap = covered_crops.intersection(gap_crops)
    if overlap:
        raise ValueError(
            "Культура не может одновременно иметь кандидата и считаться пробелом: "
            + ", ".join(sorted(overlap))
        )
    missing = supported_crops.difference(covered_crops | gap_crops)
    if missing:
        raise ValueError(
            "Не классифицированы поддерживаемые культуры: "
            + ", ".join(sorted(missing))
        )


validate_biological_risk_catalog()
