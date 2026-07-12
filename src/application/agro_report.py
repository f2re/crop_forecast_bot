from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from src.agro.crop_catalog import get_crop_name
from src.agro.indices import (
    FROST_STATUS_INSUFFICIENT,
    compute_all_indices,
)
from src.api.open_meteo import OpenMeteoProvider
from src.application.ports.weather import WeatherProvider
from src.domain.weather import AgroWeatherData, WeatherCoverage


@dataclass(frozen=True, slots=True)
class AgroReport:
    text: str
    generated_at: datetime
    source: str
    metadata_source: str
    timezone: str
    elevation_m: float
    coverage: WeatherCoverage


async def generate_agro_report(
    latitude: float,
    longitude: float,
    crop: str,
    *,
    season_start_date: date | None = None,
    phenological_phase: str | None = None,
    field_name: str = "Основное поле",
    provider: WeatherProvider | None = None,
) -> AgroReport:
    weather_provider = provider or OpenMeteoProvider()
    weather = await weather_provider.fetch(
        latitude,
        longitude,
        season_start=season_start_date,
    )
    season_start_timestamp: pd.Timestamp | None = None
    if season_start_date is not None:
        local_start = datetime.combine(
            season_start_date,
            time.min,
            tzinfo=ZoneInfo(weather.meta.timezone),
        )
        # Preserve the local calendar date for coverage checks. The calculation
        # layer filters by this local date rather than a widened UTC interval.
        season_start_timestamp = pd.Timestamp(local_start)

    indices = compute_all_indices(
        weather.daily,
        crop=crop,
        utc_offset_seconds=weather.meta.utc_offset_seconds,
        season_start=season_start_timestamp,
        phase=phenological_phase,
        elevation_m=weather.meta.elevation_m,
    )
    text = format_agro_report(
        weather,
        indices,
        crop,
        field_name=field_name,
        season_start_date=season_start_date,
        phenological_phase=phenological_phase,
    )
    sources = [weather.meta.source]
    if weather.coverage.history_source:
        sources.insert(0, weather.coverage.history_source)
    return AgroReport(
        text=text,
        generated_at=datetime.now(timezone.utc),
        source=" + ".join(sources),
        metadata_source=weather.meta.source,
        timezone=weather.meta.timezone,
        elevation_m=weather.meta.elevation_m,
        coverage=weather.coverage,
    )


def _coverage_line(weather: AgroWeatherData) -> str:
    coverage = weather.coverage
    if coverage.actual_start is None or coverage.actual_end is None:
        return "период данных не определён"
    return f"{coverage.actual_start:%d.%m.%Y} — {coverage.actual_end:%d.%m.%Y}"


def _format_source_counts(counts: dict[str, int]) -> str:
    labels = {
        "observation": "наблюдения",
        "reanalysis": "реанализ",
        "operational_past": "оперативное прошлое модели",
        "current_forecast": "текущий прогноз",
        "forecast": "прогноз",
    }
    parts = [f"{labels.get(kind, kind)}: {days} сут." for kind, days in counts.items()]
    return ", ".join(parts) if parts else "источник по строкам не указан"


def format_agro_report(
    weather: AgroWeatherData,
    indices: dict,
    crop: str,
    *,
    field_name: str = "Основное поле",
    season_start_date: date | None = None,
    phenological_phase: str | None = None,
) -> str:
    htc = indices["htc"]
    gdd = indices["gdd"]
    frost = indices["frost"]
    water = indices["et0_bal"]
    crop_name = get_crop_name(crop)
    safe_field_name = html.escape(field_name)
    safe_phase = html.escape(phenological_phase) if phenological_phase else None

    lines = [
        "🌾 <b>Агрометеорологический отчёт</b>",
        f"🗺 Поле: <b>{safe_field_name}</b>",
        f"📍 {weather.meta.latitude:.4f}, {weather.meta.longitude:.4f}",
        f"🕒 Часовой пояс: {html.escape(weather.meta.timezone)}",
        f"🏔 Высота модели: {weather.meta.elevation_m:.0f} м",
        f"🌱 Культура: <b>{html.escape(crop_name)}</b>",
    ]
    if season_start_date is not None:
        lines.append(f"📅 Начало сезона/посев: {season_start_date:%d.%m.%Y}")
    else:
        lines.append("📅 Начало сезона: не задано")
    if safe_phase:
        lines.append(f"🌿 Фаза: <b>{safe_phase}</b> — указана пользователем")
    else:
        lines.append("🌿 Фаза: не указана; автоматически не определяется")
    lines.append("")

    if frost["status"] == FROST_STATUS_INSUFFICIENT:
        lines.append("⚠️ <b>Температурный риск не оценён:</b> недостаточно данных")
        lines.append(f"• {html.escape(frost['status_note'])}")
        lines.append(
            "<b>Что делать:</b> повторить запрос после обновления прогноза и "
            "проверить независимый локальный источник. Отсутствие данных не "
            "означает отсутствие заморозка."
        )
    elif frost["alerts"]:
        lines.append("🌡 <b>Что происходит:</b> есть температурный риск")
        for alert in frost["alerts"][:3]:
            lead = (
                "сегодня"
                if alert["lead_days"] == 0
                else f"примерно через {alert['lead_days']} сут."
            )
            lines.append(
                f"• {alert['date_local']}: Tmin воздуха {alert['t_min']:.1f}°C, {lead}"
            )
        lines.append(
            "<b>Что делать:</b> сверить локальный прогноз, измерения на поле, "
            "фактическую фазу и понижения рельефа. Этот скрининг не определяет "
            "порог повреждения культуры."
        )
    else:
        lines.append(
            "✅ <b>Что происходит:</b> в валидной прогнозной Tmin общий "
            "температурный риск по заданной политике не выявлен"
        )
        lines.append(
            f"• Проверено прогнозных суток: {frost['valid_forecast_days']}"
        )

    lines.extend(["", "💧 <b>Влагообеспеченность</b>"])
    if htc["htc"] is None:
        lines.append(f"• ГТК не рассчитан: {html.escape(htc['interpretation'])}")
    else:
        lines.append(
            f"• ГТК = {htc['htc']:.2f}; {html.escape(htc['interpretation'])} "
            f"(тёплых валидных суток: {htc['available_days']})"
        )
    if water["balance_mm"] is None:
        lines.append(
            f"• Осадки − ET₀ не рассчитаны: {html.escape(water['status'])}. "
            f"Валидных суток: {water['valid_days']} из {water['window_days']}."
        )
    else:
        lines.append(
            f"• Осадки − ET₀ за {water['window_days']} завершённых суток: "
            f"{water['balance_mm']:+.1f} мм. {html.escape(water['status'])}"
        )
    lines.append("• Разность осадки − ET₀ не является дозой полива.")

    lines.extend(["", "🌱 <b>Теплообеспеченность</b>"])
    if gdd["gdd_past"] is None:
        lines.append("• ГДД не рассчитаны: нет завершённых валидных суток.")
    elif gdd["period_is_season"]:
        lines.append(
            f"• ГДД с начала сезона: {gdd['gdd_past']:.1f}°C·сут "
            f"при Tbase={gdd['t_base']:.1f}°C"
        )
    else:
        lines.append(
            f"• ГДД за доступный период: {gdd['gdd_past']:.1f}°C·сут "
            f"при Tbase={gdd['t_base']:.1f}°C"
        )
        lines.append(f"• {html.escape(gdd['period_note'])}")

    if gdd["gdd_forecast_7d"] is None:
        lines.append("• Прогнозный прирост ГДД не рассчитан: нет прогнозных суток.")
    else:
        lines.append(
            f"• Прогнозный прирост за {gdd['forecast_days']} сут.: "
            f"{gdd['gdd_forecast_7d']:.1f}°C·сут"
        )
    if gdd["missing_fraction"] is not None and gdd["missing_fraction"] > 0:
        lines.append(
            f"• Пропуски в расчётном периоде: {gdd['missing_fraction'] * 100:.1f}%"
        )
    contributions = gdd.get("contribution_by_kind", {})
    if contributions:
        lines.append(
            "• Вклад прошлого периода: "
            + ", ".join(
                f"{kind} {value:.1f}°C·сут" for kind, value in contributions.items()
            )
        )
    lines.append(f"• {html.escape(gdd['phenology_note'])}")

    lines.extend(
        [
            "",
            "📊 <b>Надёжность и источники</b>",
            f"• Период объединённого ряда: {_coverage_line(weather)}",
            f"• ГДД: {_format_source_counts(gdd.get('source_counts', {}))}",
            f"• ГТК: {_format_source_counts(htc.get('source_counts', {}))}",
            f"• Осадки − ET₀: {_format_source_counts(water.get('source_counts', {}))}",
            f"• Tmin-прогноз: {_format_source_counts(frost.get('source_counts', {}))}",
        ]
    )
    if weather.coverage.history_source:
        lines.append(
            "• Прошлый сезонный ряд: Open-Meteo Historical Weather API "
            "(реанализ, не полевая станция)."
        )
    else:
        lines.append("• Сезонный реанализ в этот отчёт не включён.")
    lines.append("• Текущие и будущие дни: Open-Meteo Forecast API.")
    for note in weather.coverage.notes:
        lines.append(f"⚠️ {html.escape(note)}")
    lines.extend(
        [
            "",
            "🔄 <b>Когда проверить снова:</b> после обновления прогноза, "
            "изменения фактической фазы или корректировки даты посева.",
            "ℹ️ Это не климатическая норма и не прогноз урожайности.",
        ]
    )
    return "\n".join(lines)
