from __future__ import annotations

import html
from datetime import datetime, timezone

from src.agro.crop_catalog import get_crop_name
from src.application.risk_history import RiskHistory, RiskHistoryItem

_RISK_LABELS = {
    "frost": ("🌡", "холод / возможный заморозок"),
    "heat": ("🔥", "сильная жара"),
    "heavy_rain": ("🌧", "сильные осадки"),
    "strong_wind": ("💨", "сильный ветер"),
    "convection": ("⛈", "конвективная неустойчивость"),
}
_TREND_LABELS = {
    "new": ("🆕", "новый сигнал"),
    "strengthening": ("📈", "усиливается"),
    "stable": ("➡️", "стабилен"),
    "weakening": ("📉", "ослабевает"),
    "cleared": ("✅", "снят"),
}
_MAX_ITEMS = 8


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _item_line(item: RiskHistoryItem) -> str:
    signal = item.signal
    risk_emoji, risk_label = _RISK_LABELS[signal.risk_type]
    trend_emoji, trend_label = _TREND_LABELS[item.trend]

    if item.current is None:
        previous = item.previous
        assert previous is not None
        return (
            f"• {trend_emoji} {risk_emoji} <b>{risk_label}</b>, "
            f"{previous.event_date:%d.%m}: {trend_label}; ранее "
            f"{previous.members_exceeding}/{previous.valid_members} сценариев "
            f"({previous.member_fraction * 100:.0f}%)."
        )

    current = item.current
    previous = item.previous
    previous_note = ""
    if previous is not None:
        previous_note = (
            f"; было {previous.members_exceeding}/{previous.valid_members} "
            f"({previous.member_fraction * 100:.0f}%)"
        )
    return (
        f"• {trend_emoji} {risk_emoji} <b>{risk_label}</b>, "
        f"{current.event_date:%d.%m}: {trend_label}; сейчас "
        f"{current.members_exceeding}/{current.valid_members} сценариев "
        f"({current.member_fraction * 100:.0f}%){previous_note}."
    )


def format_risk_history(
    history: RiskHistory,
    *,
    field_name: str,
    crop: str,
) -> str:
    lines = [
        "🕘 <b>История погодных рисков</b>",
        f"🗺 Поле: <b>{html.escape(field_name)}</b>",
        f"🌱 Культура: <b>{html.escape(get_crop_name(crop))}</b>",
    ]

    if not history.available or history.current_run is None:
        lines.extend(
            [
                "",
                f"• {html.escape(history.status)}.",
                "• История формируется только после успешных фоновых запусков "
                "ансамблевого мониторинга.",
            ]
        )
        return "\n".join(lines)

    current = history.current_run
    retrieved_at = _utc(current.retrieved_at)
    lines.extend(
        [
            "",
            f"Последний запуск: <b>{retrieved_at:%d.%m.%Y %H:%M UTC}</b>",
            f"• Модель: {html.escape(current.model)}; источник: "
            f"{html.escape(current.source)}.",
            f"• Полностью оценено суток: {current.valid_days} из "
            f"{current.forecast_days}; исключено: {current.incomplete_days}.",
            "",
            "<b>Изменение модельного сигнала</b>",
        ]
    )

    if history.items:
        for item in history.items[:_MAX_ITEMS]:
            lines.append(_item_line(item))
        hidden = len(history.items) - _MAX_ITEMS
        if hidden > 0:
            lines.append(f"• Ещё изменений: {hidden}.")
    else:
        lines.append(
            "• В последнем запуске сигналов выше операционных порогов нет; "
            "снимать ранее активные сигналы также не требовалось."
        )

    lines.extend(
        [
            "",
            "Тренд сравнивает только два последних запуска одной модели. "
            "Он не является вероятностью события, прогнозом ущерба или "
            "подтверждением явления на конкретном поле.",
        ]
    )
    text = "\n".join(lines)
    if len(text) > 4096:
        raise ValueError("Risk history exceeds Telegram message limit")
    return text
