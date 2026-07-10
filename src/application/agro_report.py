from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.agro.crop_catalog import get_crop_name
from src.agro.indices import compute_all_indices
from src.api.open_meteo import AgroWeatherData, fetch_agro_data


@dataclass(frozen=True, slots=True)
class AgroReport:
    text: str
    generated_at: datetime
    source: str


async def generate_agro_report(latitude: float, longitude: float, crop: str) -> AgroReport:
    weather = await fetch_agro_data(latitude, longitude)
    indices = compute_all_indices(weather.daily, crop=crop)
    text = format_agro_report(weather, indices, crop)
    return AgroReport(
        text=text,
        generated_at=datetime.now(timezone.utc),
        source=weather.meta.source,
    )


def format_agro_report(weather: AgroWeatherData, indices: dict, crop: str) -> str:
    htc = indices["htc"]
    gdd = indices["gdd"]
    frost = indices["frost"]
    water = indices["et0_bal"]
    crop_name = get_crop_name(crop)

    lines = [
        "🌾 <b>Агрометеорологический отчёт</b>",
        f"📍 {weather.meta.latitude:.4f}, {weather.meta.longitude:.4f}",
        f"🏔 Высота модели: {weather.meta.elevation_m:.0f} м",
        f"🌱 Культура: <b>{crop_name}</b>",
        "",
    ]

    if frost["alerts"]:
        lines.append("🌡 <b>Что происходит:</b> есть температурный риск")
        for alert in frost["alerts"][:3]:
            lines.append(
                f"• {alert['date_local']}: минимум {alert['t_min']:.1f}°C, "
                f"заблаговременность около {alert['lead_hours']} ч"
            )
        lines.append(
            "<b>Что делать:</b> сверить локальный прогноз и готовность защитных мер; "
            "решение принимать с учётом фазы культуры и микрорельефа."
        )
    else:
        lines.append("✅ <b>Что происходит:</b> по модельной температуре воздуха риск заморозка не выявлен")

    lines.extend(["", "💧 <b>Влагообеспеченность</b>"])
    if htc["htc"] is None:
        lines.append(f"• ГТК не рассчитан: {htc['interpretation']}")
    else:
        lines.append(
            f"• ГТК = {htc['htc']:.2f}; {htc['interpretation']} "
            f"(доступно {htc['available_days']} сут.)"
        )
    lines.append(
        f"• Баланс осадки − ET₀ за {water['window_days']} сут.: "
        f"{water['balance_mm']:+.1f} мм. {water['status']}"
    )

    lines.extend(
        [
            "",
            "🌱 <b>Теплообеспеченность</b>",
            f"• ГДД за доступный период: {gdd['gdd_past']:.1f}°C·сут "
            f"при Tbase={gdd['t_base']:.1f}°C",
            f"• Прогноз прироста за 7 суток: {gdd['gdd_forecast_7d']:.1f}°C·сут",
            "• Фенофаза не определяется без даты посева/начала сезона.",
            "",
            "📊 <b>Надёжность:</b> оперативная оценка по Open-Meteo; "
            "архив 14 суток и прогноз 7 суток. Это не климатическая норма и не прогноз урожайности.",
            "🔄 <b>Когда проверить снова:</b> после следующего обновления прогноза или при смене фазы культуры.",
        ]
    )
    return "\n".join(lines)
