from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from src.agro.crop_catalog import get_crop_name
from src.agro.indices import compute_all_indices
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
        season_start_timestamp = pd.Timestamp(local_start).tz_convert("UTC")

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

    lines = [
        "🌾 <b>Агрометеорологический отчёт</b>",
        f"🗺 Поле: <b>{field_name}</b>",
        f"📍 {weather.meta.latitude:.4f}, {weather.meta.longitude:.4f}",
        f"🕒 Часовой пояс: {weather.meta.timezone}",
        f"🏔 Высота модели: {weather.meta.elevation_m:.0f} м",
        f"🌱 Культура: <b>{crop_name}</b>",
    ]
    if season_start_date is not None:
        lines.append(f"📅 Начало сезона/посев: {season_start_date:%d.%m.%Y}")
    else:
        lines.append("📅 Начало сезона: не задано")
    if phenological_phase:
        lines.append(f"🌿 Фаза: <b>{phenological_phase}</b> — указана пользователем")
    else:
        lines.append("🌿 Фаза: не указана; автоматически не угадывается")
    lines.append("")

    if frost["alerts"]:
        lines.append("🌡 <b>Что происходит:</b> есть температурный риск")
        for alert in frost["alerts"][:3]:
            lines.append(
                f"• {alert['date_local']}: Tmin воздуха {alert['t_min']:.1f}°C, "
                f"примерно через {alert['lead_hours']} ч"
            )
        lines.append(
            "<b>Что делать:</b> сверить локальный прогноз, фактическую фазу "
            "и условия понижений рельефа. Порог повреждения культуры этим "
            "скринингом не определяется."
        )
    else:
        lines.append(
            "✅ <b>Что происходит:</b> по прогнозной Tmin воздуха общий "
            "температурный риск не выявлен"
        )

    lines.extend(["", "💧 <b>Влагообеспеченность</b>"])
    if htc["htc"] is None:
        lines.append(f"• ГТК не рассчитан: {htc['interpretation']}")
    else:
        lines.append(
            f"• ГТК = {htc['htc']:.2f}; {htc['interpretation']} "
            f"(валидных тёплых суток: {htc['available_days']})"
        )
    if water.get("available") and water.get("balance_mm") is not None:
        lines.append(
            f"• Баланс осадки − ET₀ за {water['window_days']} сут.: "
            f"{water['balance_mm']:+.1f} мм. {water['status']}"
        )
    else:
        lines.append(
            f"• Баланс осадки − ET₀ не рассчитан: {water['status']}. "
            f"Валидных суток: {water.get('valid_days', 0)}/"
            f"{water.get('expected_days', water['window_days'])}."
        )

    lines.extend(["", "🌱 <b>Теплообеспеченность</b>"])
    if gdd["period_is_season"]:
        lines.append(
            f"• ГДД с начала сезона: {gdd['gdd_past']:.1f}°C·сут "
            f"при Tbase={gdd['t_base']:.1f}°C"
        )
    else:
        lines.append(
            f"• ГДД только за доступный период: {gdd['gdd_past']:.1f}°C·сут "
            f"при Tbase={gdd['t_base']:.1f}°C"
        )
        if season_start_date is not None:
            lines.append(
                "• Ряд не покрывает дату начала сезона; сезонная сумма не заявляется."
            )
    lines.append(f"• Прогноз прироста за 7 суток: {gdd['gdd_forecast_7d']:.1f}°C·сут")
    source_parts = []
    if gdd.get("gdd_reanalysis"):
        source_parts.append(f"реанализ {gdd['gdd_reanalysis']:.1f}")
    if gdd.get("gdd_operational_past"):
        source_parts.append(f"оперативное прошлое {gdd['gdd_operational_past']:.1f}")
    if source_parts:
        lines.append(
            "• Состав прошлой суммы ГДД: " + "; ".join(source_parts) + " °C·сут"
        )
    if gdd["missing_fraction"]:
        lines.append(
            f"• Пропуски в расчётном периоде: {gdd['missing_fraction'] * 100:.1f}%"
        )
    lines.append(f"• {gdd['phenology_note']}")

    lines.extend(
        [
            "",
            "📊 <b>Надёжность и источники</b>",
            f"• Период объединённого ряда: {_coverage_line(weather)}",
            "• Прошлые данные: реанализ Open-Meteo Historical Weather API "
            "(если был нужен и доступен)",
            "• Текущие дни и прогноз: Open-Meteo Forecast API",
            "• Реанализ, оперативный архив модели и прогноз не считаются "
            "наблюдениями одной природы.",
        ]
    )
    for note in weather.coverage.notes:
        lines.append(f"⚠️ {note}")
    lines.extend(
        [
            "",
            "🔄 <b>Когда проверить снова:</b> после обновления прогноза, "
            "изменения фактической фазы или корректировки даты посева.",
            "ℹ️ Это не климатическая норма и не прогноз урожайности.",
        ]
    )
    return "\n".join(lines)
