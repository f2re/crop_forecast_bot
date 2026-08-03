from __future__ import annotations

import html

from src.domain.marker_catalog import (
    AGROMETEOROLOGICAL_HAZARD_REFERENCE,
    AGROMETEOROLOGICAL_HAZARDS,
    METEOROLOGICAL_HAZARD_SOURCE,
    METEOROLOGICAL_HAZARDS,
    PEST_MARKERS,
    HazardType,
    PestMarker,
    pest_markers_by_status,
)
from src.domain.pests import PEST_MODELS


def _screening_symbol(hazard: HazardType) -> str:
    return "🟡" if hazard.screening_status == "model_screening" else "⚪"


def _marker_models(marker_key: str) -> tuple[str, ...]:
    return tuple(
        model.name_ru
        for model in PEST_MODELS.values()
        if marker_key in model.marker_keys
    )


def _short_marker_line(marker: PestMarker) -> str:
    linked = _marker_models(marker.key)
    linked_text = (
        "; модели: " + ", ".join(html.escape(name) for name in linked)
        if linked
        else ""
    )
    return f"• <b>{html.escape(marker.name_ru)}</b>{linked_text}."


def format_marker_catalog_overview() -> str:
    implemented = pest_markers_by_status("implemented")
    candidates = pest_markers_by_status("candidate_unlinked")
    context = pest_markers_by_status("context_only")
    return "\n".join(
        [
            "📚 <b>ОЯ и погодные маркеры</b>",
            "",
            "Каталог разделяет три разные вещи:",
            "• официальные опасные метеорологические явления — "
            "20 типов типового перечня;",
            "• опасные агрометеорологические явления — 18 типов "
            "исторической опытной методики;",
            f"• маркеры вредителей — {len(implemented)} реализовано, "
            f"{len(candidates)} кандидатов без связи с культурами, "
            f"{len(context)} контекстных признака.",
            "",
            "⚠️ <b>Ключевое ограничение</b>",
            "Бот не присваивает явлению официальный статус ОЯ. Такой статус "
            "показывается только из сообщения уполномоченной службы. "
            "Модельные значения бота — ранний screening для подготовки и "
            "осмотра, а не штормовое предупреждение.",
            "",
            "Вредитель связывается с культурой только если модель содержит "
            "реализованный погодный driver, точку отсчёта, метод, пороги и "
            "проверяемый источник. Кандидаты из справочника автоматически к "
            "культурам не привязываются.",
        ]
    )


def format_meteorological_hazards() -> str:
    lines = [
        "🌪 <b>Типовой перечень метеорологических ОЯ</b>",
        "",
        "🟡 — есть только ранний модельный сигнал в боте;",
        "⚪ — пока только справочник и требования к данным.",
        "",
    ]
    lines.extend(
        f"{_screening_symbol(hazard)} <code>{hazard.code}</code> "
        f"{html.escape(hazard.name_ru)}"
        for hazard in METEOROLOGICAL_HAZARDS
    )
    lines.extend(
        [
            "",
            "Источник типового перечня: "
            f"{html.escape(METEOROLOGICAL_HAZARD_SOURCE.title)}.",
            html.escape(METEOROLOGICAL_HAZARD_SOURCE.status_note),
            "",
            "Даже для позиций с 🟡 бот не объявляет ОЯ: критерий зависит от "
            "территории, продолжительности, масштаба и официальной технологии "
            "выпуска предупреждения.",
        ]
    )
    return "\n".join(lines)


def format_agrometeorological_hazards() -> str:
    lines = [
        "🌾 <b>Опасные агрометеорологические явления</b>",
        "",
        "🟡 — в боте есть лишь часть исходных модельных величин;",
        "⚪ — полный расчёт не реализован.",
        "",
    ]
    lines.extend(
        f"{_screening_symbol(hazard)} <code>{hazard.code}</code> "
        f"{html.escape(hazard.name_ru)}"
        for hazard in AGROMETEOROLOGICAL_HAZARDS
    )
    lines.extend(
        [
            "",
            "Методическая основа: "
            f"{html.escape(AGROMETEOROLOGICAL_HAZARD_REFERENCE.title)}.",
            "⚠️ " + html.escape(AGROMETEOROLOGICAL_HAZARD_REFERENCE.status_note),
            "",
            "Поэтому бот использует этот перечень для проектирования данных и "
            "полевой проверки, но не выдаёт его критерии за действующее "
            "официальное предупреждение или подтверждённый ущерб.",
        ]
    )
    return "\n".join(lines)


def format_operational_pest_markers() -> str:
    implemented = pest_markers_by_status("implemented")
    lines = [
        "🐛 <b>Рабочие маркеры моделей вредителей</b>",
        "",
    ]
    lines.extend(_short_marker_line(marker) for marker in implemented)
    lines.extend(
        [
            "",
            "<b>Проверка связей</b>",
        ]
    )
    for model in PEST_MODELS.values():
        weather_markers = [
            marker.name_ru
            for marker in (get_marker for get_marker in ())
        ]
        del weather_markers
        marker_names = [
            next(marker.name_ru for marker in PEST_MARKERS if marker.key == key)
            for key in model.marker_keys
        ]
        lines.append(
            f"• {html.escape(model.name_ru)} — "
            f"{html.escape(', '.join(marker_names))}."
        )
    lines.extend(
        [
            "",
            "Каждая рабочая модель проходит проверку при импорте: в ней должен "
            "быть реализованный погодный driver; кандидат без валидированной "
            "модели вызывает ошибку запуска, а не скрытую привязку к культуре.",
        ]
    )
    return "\n".join(lines)


def format_candidate_pest_markers() -> str:
    candidates = pest_markers_by_status("candidate_unlinked")
    context = pest_markers_by_status("context_only")
    lines = [
        "🧪 <b>Кандидаты для следующих моделей вредителей</b>",
        "",
        "Эти признаки изучены как потенциально полезные, но не связаны с "
        "культурой или вредителем без видоспецифичного источника:",
        "",
    ]
    lines.extend(
        f"• <b>{html.escape(marker.name_ru)}</b> — "
        f"{html.escape(marker.description)}"
        for marker in candidates
    )
    lines.extend(
        [
            "",
            "<b>Контекст, который не заменяет погоду</b>",
        ]
    )
    lines.extend(
        f"• <b>{html.escape(marker.name_ru)}</b> — "
        f"{html.escape(marker.description)}"
        for marker in context
    )
    lines.extend(
        [
            "",
            "Добавление нового маркера в этот список не включает вредителя в "
            "Telegram. Сначала нужны точный вид, культура, biofix, алгоритм, "
            "единицы, пороги, региональная применимость и тесты.",
        ]
    )
    return "\n".join(lines)
