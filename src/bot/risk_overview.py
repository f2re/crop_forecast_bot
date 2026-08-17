from __future__ import annotations

import html
from datetime import timezone

from src.application.risk_overview import RiskOverview
from src.bot.risk_language import (
    crop_context_lines,
    format_risk_period,
    group_risk_events,
    model_label,
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
    """Render a compact decision-oriented weather overview."""

    outlook = overview.outlook
    meta = overview.meta
    retrieved_at = meta.retrieved_at.astimezone(timezone.utc)
    periods = group_risk_events(outlook.events)

    lines = [
        f"⚠️ <b>Погодные риски: {html.escape(field_name)}</b>",
    ]
    lines.extend(
        crop_context_lines(
            crops=crops,
            selected_crop=crop,
            phase=phase,
        )
    )
    lines.append("")

    if not outlook.available:
        lines.extend(
            [
                f"⚪ Данные временно недоступны: {html.escape(outlook.status)}.",
                "Что сделать: проверьте официальный прогноз.",
            ]
        )
    elif periods:
        for index, period in enumerate(periods[:_MAX_PERIODS]):
            if index:
                lines.append("")
            lines.append(format_risk_period(period))
        hidden = max(0, len(periods) - _MAX_PERIODS)
        if hidden:
            lines.append(f"\nЕщё периодов: {hidden}.")
    else:
        lines.extend(
            [
                "🟢 <b>Существенных погодных рисков не выявлено.</b>",
                "Срочных действий нет; продолжайте обычный осмотр поля.",
            ]
        )

    lines.extend(
        [
            "",
            (
                f"<i>Данные: {html.escape(model_label(meta.model))} · "
                f"{retrieved_at:%d.%m %H:%M UTC} · "
                f"проверено {outlook.valid_days}/{outlook.forecast_days} суток.</i>"
            ),
        ]
    )

    text = "\n".join(lines)
    if len(text) > 4096:
        raise ValueError("Risk overview exceeds Telegram message limit")
    return text
