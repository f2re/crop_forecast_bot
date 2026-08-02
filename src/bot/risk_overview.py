from __future__ import annotations

import html
from datetime import timezone

from src.application.risk_overview import RiskOverview
from src.bot.risk_language import (
    crop_context_lines,
    format_risk_period,
    group_risk_events,
    model_label,
    unique_actions,
)

_MAX_PERIODS = 5


def format_risk_overview(
    overview: RiskOverview,
    *,
    field_name: str,
    crop: str,
    crops: tuple[str, ...] = (),
    phase: str | None = None,
) -> str:
    """Render weather signals without presenting raw members as crop damage odds."""

    outlook = overview.outlook
    meta = overview.meta
    retrieved_at = meta.retrieved_at.astimezone(timezone.utc)
    periods = group_risk_events(outlook.events)

    lines = [
        "⚠️ <b>Погодные условия, требующие внимания</b>",
        f"🗺 Поле: <b>{html.escape(field_name)}</b>",
    ]
    lines.extend(
        crop_context_lines(
            crops=crops,
            selected_crop=crop,
            phase=phase,
        )
    )
    lines.extend(
        [
            "",
            "<b>Как читать прогноз</b>",
            f"• {meta.member_count} вариантов одной модели рассчитаны с немного "
            "разными начальными условиями. Чем больше вариантов показывают одно "
            "и то же, тем согласованнее сигнал.",
            "• Это не процент повреждения культуры и не официальное предупреждение.",
            "",
            "<b>Что ожидается</b>",
        ]
    )

    if not outlook.available:
        lines.append(f"• Анализ не выполнен: {html.escape(outlook.status)}.")
        lines.append(
            "• Отсутствие полного ансамбля не означает отсутствие локального явления."
        )
    elif periods:
        for period in periods[:_MAX_PERIODS]:
            lines.extend([format_risk_period(period), ""])
        hidden = max(0, len(periods) - _MAX_PERIODS)
        if hidden:
            lines.append(f"• Дополнительных периодов: {hidden}.")
    else:
        lines.append(
            "• На полностью обеспеченной части прогноза общие погодные пороги "
            "внимания не достигнуты. Локальные явления всё равно возможны."
        )

    lines.extend(
        [
            "<b>Надёжность данных</b>",
            f"• Источник: {html.escape(meta.source)}; модель: "
            f"{html.escape(model_label(meta.model))}.",
            f"• Полностью проверено суток: {outlook.valid_days} из "
            f"{outlook.forecast_days}; пропущено из-за неполных данных: "
            f"{outlook.incomplete_days}.",
            f"• Данные получены: {retrieved_at:%d.%m.%Y %H:%M UTC}.",
            "• Ближайшие 3–5 суток обычно полезнее для конкретных действий. "
            "После 7–10 суток даты и интенсивность могут заметно сдвинуться.",
        ]
    )

    lines.extend(["", "<b>Что делать сейчас</b>"])
    if periods:
        for action in unique_actions(periods):
            lines.append(f"• {html.escape(action)}")
    else:
        lines.append(
            "• Продолжайте обычный контроль поля и официальных предупреждений."
        )

    lines.extend(
        [
            "",
            "<b>Когда проверить снова</b>",
            "• После следующего запуска модели, при изменении фактической фазы "
            "культуры и обязательно при официальном предупреждении.",
        ]
    )
    if any(period.risk_type == "convection" for period in periods):
        lines.append(
            "• CAPE описывает запас энергии в атмосфере. Без подъёма воздуха, "
            "влаги, сдвига ветра и краткосрочных наблюдений он не доказывает "
            "грозу или град."
        )

    text = "\n".join(line for line in lines if line is not None)
    if len(text) > 4096:
        raise ValueError("Risk overview exceeds Telegram message limit")
    return text
