from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from src.agro.climate_reference import calc_season_climate_reference
from src.agro.crop_catalog import get_crop_name
from src.agro.indices import (
    FROST_STATUS_INSUFFICIENT,
    compute_all_indices,
)
from src.agro.water import calc_water_accumulation
from src.api.open_meteo import OpenMeteoProvider
from src.api.open_meteo_climate import OpenMeteoClimateProvider
from src.application.ports.climate import ClimateProvider, ClimateProviderError
from src.application.ports.weather import WeatherProvider
from src.domain.climate import ClimateReferenceData
from src.domain.weather import AgroWeatherData, WeatherCoverage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgroReport:
    text: str
    generated_at: datetime
    source: str
    metadata_source: str
    timezone: str
    elevation_m: float
    coverage: WeatherCoverage
    model: str | None = None
    model_run: datetime | None = None
    retrieved_at: datetime | None = None
    cache_ttl_seconds: int | None = None
    spatial_resolution_km: float | None = None


async def generate_agro_report(
    latitude: float,
    longitude: float,
    crop: str,
    *,
    season_start_date: date | None = None,
    phenological_phase: str | None = None,
    field_name: str = "Основное поле",
    provider: WeatherProvider | None = None,
    climate_provider: ClimateProvider | None = None,
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
    indices["water_accumulation"] = calc_water_accumulation(
        weather.daily,
        season_start=season_start_timestamp,
    )

    climate_data: ClimateReferenceData | None = None
    indices["climate_reference"] = {
        "available": False,
        "requested": False,
        "status": "для сравнения нужна дата начала сезона",
    }
    resolved_climate_provider = climate_provider
    # Unit/application tests commonly inject only the operational weather
    # provider. Do not start an unrelated network request in that case unless a
    # climate provider was supplied explicitly.
    if resolved_climate_provider is None and provider is None:
        resolved_climate_provider = OpenMeteoClimateProvider()
    if season_start_timestamp is not None and resolved_climate_provider is not None:
        try:
            climate_data = await resolved_climate_provider.fetch_reference(
                latitude,
                longitude,
                timezone=weather.meta.timezone,
            )
            climate_reference = calc_season_climate_reference(
                weather.daily,
                climate_data.daily,
                crop=crop,
                season_start=season_start_timestamp,
                reference_start=climate_data.meta.reference_start,
                reference_end=climate_data.meta.reference_end,
            )
            climate_reference["requested"] = True
            climate_reference["provider"] = {
                "source": climate_data.meta.source,
                "model": climate_data.meta.model,
                "reference_start": climate_data.meta.reference_start.isoformat(),
                "reference_end": climate_data.meta.reference_end.isoformat(),
                "retrieved_at": climate_data.meta.retrieved_at,
                "cache_ttl_seconds": climate_data.meta.cache_ttl_seconds,
                "spatial_resolution_km": climate_data.meta.spatial_resolution_km,
            }
            indices["climate_reference"] = climate_reference
        except (ClimateProviderError, ValueError) as exc:
            climate_data = None
            logger.warning(
                "Climate reference unavailable for %.5f, %.5f: %s",
                latitude,
                longitude,
                exc,
            )
            indices["climate_reference"] = {
                "available": False,
                "requested": True,
                "status": "реанализная база ERA5-Land временно недоступна",
            }

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
    if climate_data is not None:
        sources.insert(0, climate_data.meta.source)
    return AgroReport(
        text=text,
        generated_at=datetime.now(timezone.utc),
        source=" + ".join(dict.fromkeys(sources)),
        metadata_source=weather.meta.source,
        timezone=weather.meta.timezone,
        elevation_m=weather.meta.elevation_m,
        coverage=weather.coverage,
        model=weather.meta.model,
        model_run=weather.meta.model_run,
        retrieved_at=weather.meta.retrieved_at,
        cache_ttl_seconds=weather.meta.cache_ttl_seconds,
        spatial_resolution_km=weather.meta.spatial_resolution_km,
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


def _format_iso_day(value: str | None) -> str:
    if not value:
        return "дата не определена"
    return date.fromisoformat(value).strftime("%d.%m.%Y")


def _format_provider_metadata(weather: AgroWeatherData) -> list[str]:
    lines: list[str] = []
    if weather.meta.model:
        lines.append(f"• Конфигурация модели: {html.escape(weather.meta.model)}")
    if weather.meta.model_run is not None:
        model_run = weather.meta.model_run.astimezone(timezone.utc)
        lines.append(f"• Запуск модели: {model_run:%d.%m.%Y %H:%M UTC}")
    else:
        lines.append("• Точный запуск модели: endpoint провайдера не сообщает")
    if weather.meta.retrieved_at is not None:
        retrieved = weather.meta.retrieved_at.astimezone(timezone.utc)
        lines.append(f"• Получено ботом: {retrieved:%d.%m.%Y %H:%M UTC}")
    if weather.meta.cache_ttl_seconds is not None:
        cache_minutes = weather.meta.cache_ttl_seconds // 60
        lines.append(f"• Политика кэша: до {cache_minutes} мин.")
    if weather.meta.spatial_resolution_km is not None:
        lines.append(
            f"• Пространственное разрешение: около "
            f"{weather.meta.spatial_resolution_km:g} км"
        )
    else:
        lines.append("• Разрешение выбранной модельной сетки: endpoint не сообщает")
    return lines


def _percentile_text(metric: dict) -> str:
    percentile = metric.get("empirical_percentile")
    if percentile is None:
        return "процентиль не определён"
    return f"{percentile:.0f}-й эмпирический процентиль"


def _format_climate_reference(climate: dict) -> list[str]:
    if not climate.get("requested"):
        return []

    lines = ["", "📈 <b>Сезон относительно реанализной базы 1991–2020</b>"]
    if not climate.get("available"):
        lines.append(f"• Не рассчитано: {html.escape(climate.get('status', 'нет данных'))}.")
        return lines

    metrics = climate["metrics"]
    temperature = metrics["mean_temperature_c"]
    if temperature["available"]:
        lines.append(
            f"• Средняя температура: {temperature['current']:.1f}°C; "
            f"{temperature['anomaly_from_mean']:+.1f}°C к среднему; "
            f"{_percentile_text(temperature)}."
        )

    precipitation = metrics["precip_sum_mm"]
    et0 = metrics["et0_sum_mm"]
    water_parts: list[str] = []
    if precipitation["available"]:
        precip_percent = precipitation.get("percent_of_mean")
        if precip_percent is None:
            water_parts.append(
                f"осадки {precipitation['current']:.1f} мм; "
                f"среднее близко к нулю, {_percentile_text(precipitation)}"
            )
        else:
            water_parts.append(
                f"осадки {precip_percent:.0f}% от среднего, "
                f"{_percentile_text(precipitation)}"
            )
    if et0["available"]:
        et0_percent = et0.get("percent_of_mean")
        if et0_percent is None:
            water_parts.append(
                f"ET₀ {et0['current']:.1f} мм; "
                f"среднее близко к нулю, {_percentile_text(et0)}"
            )
        else:
            water_parts.append(
                f"ET₀ {et0_percent:.0f}% от среднего, "
                f"{_percentile_text(et0)}"
            )
    if water_parts:
        lines.append("• " + "; ".join(water_parts) + ".")

    gdd = metrics["gdd_c_day"]
    if gdd["available"]:
        lines.append(
            f"• ГДД: {gdd['current']:.1f}°C·сут; "
            f"{gdd['anomaly_from_mean']:+.1f}°C·сут к среднему; "
            f"{_percentile_text(gdd)}."
        )

    dry_spell = metrics["max_dry_spell_days"]
    if dry_spell["available"]:
        lines.append(
            f"• Максимальная сухая серия: {dry_spell['current']:.0f} сут.; "
            f"{_percentile_text(dry_spell)}."
        )

    available_counts = [
        int(metric["reference_years"])
        for metric in metrics.values()
        if metric.get("available")
    ]
    min_years = min(available_counts) if available_counts else 0
    provider = climate.get("provider", {})
    resolution = provider.get("spatial_resolution_km")
    resolution_note = (
        f", номинальная сетка около {resolution:g} км"
        if resolution is not None
        else ""
    )
    lines.append(
        f"• Окно: {climate['window_days']} завершённых суток; "
        f"не менее {min_years} сопоставимых лет{resolution_note}."
    )
    lines.append(
        "• Процентиль — положение среди реанализных лет, не вероятность. "
        "Это не станционная норма и не SPI/SPEI."
    )
    return lines


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
    accumulated_water = indices.get("water_accumulation", {})
    climate_reference = indices.get("climate_reference", {})
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

    lines.extend(["", "💧 <b>Осадки и атмосферная испаряемость</b>"])
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

    if accumulated_water:
        scope = (
            "с начала сезона"
            if accumulated_water.get("period_is_season")
            else "за доступный завершённый период"
        )
        if accumulated_water.get("precip_sum_mm") is None:
            lines.append(
                "• Накопленные осадки не рассчитаны: "
                f"{html.escape(accumulated_water.get('status', 'нет данных'))}."
            )
        else:
            lines.append(
                f"• Накопленные осадки {scope}: "
                f"{accumulated_water['precip_sum_mm']:.1f} мм "
                f"по {accumulated_water['precip_valid_days']} валидным суткам."
            )
        if accumulated_water.get("et0_sum_mm") is None:
            lines.append("• Накопленная ET₀ провайдера не рассчитана.")
        else:
            lines.append(
                f"• Накопленная ET₀ провайдера {scope}: "
                f"{accumulated_water['et0_sum_mm']:.1f} мм."
            )
        if accumulated_water.get("p_minus_et0_mm") is None:
            lines.append(
                "• Накопленная разность P−ET₀ не рассчитана: нет достаточно "
                "полного парного ряда."
            )
        else:
            lines.append(
                f"• Климатическая разность P−ET₀ {scope}: "
                f"{accumulated_water['p_minus_et0_mm']:+.1f} мм "
                f"по {accumulated_water['paired_days']} парным суткам."
            )
        if accumulated_water.get("dry_spell_available"):
            lines.append(
                "• Сухая серия на конец ряда: "
                f"{accumulated_water['trailing_dry_spell_days']} сут.; "
                f"максимум {accumulated_water['max_dry_spell_days']} сут. "
                f"при осадках <{accumulated_water['dry_day_threshold_mm']:g} мм/сут."
            )
        else:
            lines.append(
                f"• Сухие серии не рассчитаны: "
                f"{html.escape(accumulated_water.get('dry_spell_status', 'нет данных'))}."
            )
        if accumulated_water.get("max_1day_precip_mm") is not None:
            extremes = (
                f"• Максимум осадков за сутки: "
                f"{accumulated_water['max_1day_precip_mm']:.1f} мм "
                f"({_format_iso_day(accumulated_water.get('max_1day_precip_date'))})"
            )
            if accumulated_water.get("max_5day_precip_mm") is not None:
                extremes += (
                    f"; за 5 последовательных суток: "
                    f"{accumulated_water['max_5day_precip_mm']:.1f} мм"
                )
            lines.append(extremes + ".")
        if not accumulated_water.get("period_is_season"):
            lines.append(
                f"• {html.escape(accumulated_water.get('scope_note', ''))}"
            )
    lines.append(
        "• P−ET₀ и сухая серия — климатические индикаторы, а не запас влаги "
        "в корнеобитаемом слое и не доза полива."
    )

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

    lines.extend(_format_climate_reference(climate_reference))

    lines.extend(
        [
            "",
            "📊 <b>Надёжность и источники</b>",
            f"• Период объединённого ряда: {_coverage_line(weather)}",
            f"• ГДД: {_format_source_counts(gdd.get('source_counts', {}))}",
            f"• ГТК: {_format_source_counts(htc.get('source_counts', {}))}",
            f"• Осадки − ET₀: {_format_source_counts(water.get('source_counts', {}))}",
            (
                "• Накопленные осадки/ET₀: "
                + _format_source_counts(accumulated_water.get("source_counts", {}))
            ),
            f"• Tmin-прогноз: {_format_source_counts(frost.get('source_counts', {}))}",
        ]
    )
    lines.extend(_format_provider_metadata(weather))
    if weather.coverage.history_source:
        lines.append(
            "• Прошлый сезонный ряд: Open-Meteo Historical Weather API "
            "(реанализ, не полевая станция)."
        )
    else:
        lines.append("• Сезонный реанализ в этот отчёт не включён.")
    if climate_reference.get("available"):
        provider_meta = climate_reference.get("provider", {})
        cache_days = int(provider_meta.get("cache_ttl_seconds", 0)) // (24 * 60 * 60)
        lines.append(
            "• Климатическое сравнение: ERA5-Land 1991–2020 через Open-Meteo; "
            f"кэш до {cache_days} сут."
        )
    lines.append("• Текущие и будущие дни: Open-Meteo Forecast API.")
    for note in weather.coverage.notes:
        lines.append(f"⚠️ {html.escape(note)}")
    lines.extend(
        [
            "",
            "🔄 <b>Когда проверить снова:</b> после обновления прогноза, "
            "изменения фактической фазы или корректировки даты посева.",
        ]
    )
    if climate_reference.get("requested"):
        lines.append(
            "ℹ️ Сравнение 1991–2020 основано на реанализной сетке, а не на "
            "полевой станции; это не прогноз урожайности."
        )
    else:
        lines.append("ℹ️ Это не климатическая норма и не прогноз урожайности.")
    return "\n".join(lines)
