from __future__ import annotations

import html

from src.agro.crop_catalog import get_crop_name
from src.domain.risk import RiskEvent, RiskOutlook

_RISK_LABELS = {
    "frost": ("🌡", "Заморозок / холод"),
    "heat": ("🔥", "Сильная жара"),
    "heavy_rain": ("🌧", "Сильные осадки"),
    "strong_wind": ("💨", "Сильный ветер"),
    "convection": ("⛈", "Конвективная неустойчивость"),
}
_LEVEL_LABELS = {
    "watch": "наблюдение",
    "elevated": "повышенный",
    "high": "высокий",
}


def format_ensemble_risk_alert(
    event: RiskEvent,
    outlook: RiskOutlook,
    *,
    field_name: str,
    crop: str | None = None,
    phase: str | None = None,
) -> str:
    emoji, label = _RISK_LABELS[event.risk_type]
    crop_line = (
        f"\n🌾 Культура: <b>{html.escape(get_crop_name(crop))}</b>" if crop else ""
    )
    phase_line = (
        f"\n🌿 Фаза: <b>{html.escape(phase)}</b> (указана пользователем)"
        if phase
        else ""
    )
    coverage_line = ""
    if outlook.forecast_days > 0:
        coverage_line = (
            f"\n• Полностью проверено суток: {outlook.valid_days} из "
            f"{outlook.forecast_days}"
        )
        if outlook.incomplete_days:
            coverage_line += (
                f"; исключено из-за неполных данных: {outlook.incomplete_days}"
            )
    lead = "сегодня" if event.lead_days == 0 else f"через {event.lead_days} сут."
    raw_percent = event.member_fraction * 100.0
    severe_percent = event.severe_member_fraction * 100.0
    threshold_sign = "≤" if event.risk_type == "frost" else "≥"

    return (
        f"{emoji} <b>Предупреждение: {label}</b>\n"
        f"🗺 Поле: <b>{html.escape(field_name)}</b>\n"
        f"📅 Дата: <b>{event.event_date:%d.%m.%Y}</b> ({lead})\n"
        f"⚠️ Уровень скрининга: <b>{_LEVEL_LABELS[event.level]}</b>\n"
        f"📊 Доля ансамбля: <b>{event.members_exceeding} из "
        f"{event.valid_members} ({raw_percent:.0f}%)</b> для порога "
        f"{threshold_sign}{event.threshold:g} {html.escape(event.unit)}\n"
        f"• Более строгий порог {threshold_sign}{event.severe_threshold:g}: "
        f"{event.severe_members_exceeding} из {event.valid_members} "
        f"({severe_percent:.0f}%)\n"
        f"• Диапазон P10–P90: {event.p10:g}…{event.p90:g}; "
        f"медиана {event.median:g} {html.escape(event.unit)}\n"
        f"• Модель: {html.escape(event.model)}; {html.escape(event.reliability_note)}"
        f"{coverage_line}{crop_line}{phase_line}\n\n"
        f"<b>Что делать:</b> {html.escape(event.action)}\n\n"
        f"<b>Ограничение:</b> {html.escape(event.caveat)}\n"
        "Доля ансамбля — это сырая доля модельных сценариев, а не "
        "откалиброванная вероятность. Проверяйте официальные предупреждения и "
        "более свежие прогнозы перед затратным или необратимым решением."
    )


def format_ensemble_data_unavailable(field_name: str, reason: str) -> str:
    return (
        "⚠️ <b>Ежедневный анализ погодных рисков не выполнен</b>\n"
        f"🗺 Поле: <b>{html.escape(field_name)}</b>\n"
        f"Причина: {html.escape(reason)}.\n\n"
        "Отсутствие ансамблевых данных не означает отсутствие риска. Проверьте "
        "официальный локальный прогноз и повторите анализ после обновления данных."
    )
