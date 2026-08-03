"""Compact Telegram presentation of future biological-risk integrations."""
from __future__ import annotations

import html

from src.agro.crop_catalog import get_crop
from src.domain.biological_risks import (
    BiologicalRiskCandidate,
    candidates_for_crop,
    evidence_gap_for_crop,
)

_READINESS_LABELS = {
    "published_contract": ("📐", "есть формализованная опубликованная модель"),
    "operational_external_model": ("🧰", "есть действующий внешний инструмент"),
    "regional_signal_required": ("🌍", "нужен подтверждённый очаг или перенос"),
    "legacy_model_review": ("🕰", "устаревший инструмент; нужен аудит договора"),
    "weather_screening_only": ("👁", "только погодная благоприятность"),
}


def _format_candidate(item: BiologicalRiskCandidate) -> list[str]:
    symbol, _ = _READINESS_LABELS[item.readiness]
    return [
        f"• {symbol} <b>{html.escape(item.name_ru)}</b> "
        f"(<i>{html.escape(item.scientific_name)}</i>)",
        f"  Что допустимо: {html.escape(item.permitted_output)}",
    ]


def format_crop_biological_risks(crop_key: str) -> str:
    crop = get_crop(crop_key)
    candidates = candidates_for_crop(crop_key)
    gap = evidence_gap_for_crop(crop_key)
    lines = [
        f"{crop['emoji']} <b>Болезни и вредители: {html.escape(crop['name_ru'])}</b>",
        "",
    ]
    if not candidates:
        lines.extend(
            [
                "⚪ <b>Проверяемая погодная модель пока не найдена</b>",
                html.escape(gap or "Культура ещё не классифицирована."),
                "",
                "Это не означает, что у культуры нет болезней или вредителей. "
                "Это означает, что в проверенных открытых источниках пока нет "
                "достаточного договора для безопасной автоматизации.",
            ]
        )
        return "\n".join(lines)

    diseases = tuple(item for item in candidates if item.kind == "disease")
    pests = tuple(item for item in candidates if item.kind == "pest")
    if diseases:
        lines.append("🦠 <b>Болезни</b>")
        for item in diseases:
            lines.extend(_format_candidate(item))
        lines.append("")
    if pests:
        lines.append("🐛 <b>Вредители</b>")
        for item in pests:
            lines.extend(_format_candidate(item))
        lines.append("")

    used_readiness = tuple(
        readiness
        for readiness in _READINESS_LABELS
        if any(item.readiness == readiness for item in candidates)
    )
    lines.append("<b>Обозначения</b>")
    for readiness in used_readiness:
        symbol, label = _READINESS_LABELS[readiness]
        lines.append(f"{symbol} {html.escape(label)}.")
    lines.extend(
        [
            "",
            "⚠️ Это перечень возможных интеграций, а не диагноз и не команда "
            "на обработку. Даже формализованная модель задаёт срок обследования "
            "или благоприятность условий; наличие и численность подтверждаются "
            "на поле.",
        ]
    )
    return "\n".join(lines)
