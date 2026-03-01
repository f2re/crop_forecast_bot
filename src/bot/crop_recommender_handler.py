"""
Обработчик рекомендаций по культурам.

Первичный путь: Open-Meteo → агроиндексы (ГТК, ГДД, заморозки, ЕТ0).
Fallback: simple_recommender (только география) при недоступности сети.
"""
import logging
from geopy.geocoders import Nominatim

from src.api.open_meteo import fetch_agro_data
from src.agro.indices import compute_all_indices
from src.bot.simple_recommender import format_simple_recommendation

logger = logging.getLogger(__name__)
geolocator = Nominatim(user_agent="crop_recommendation_bot")

# Культура по умолчанию для ГДД (в будущем — из профиля пользователя)
DEFAULT_CROP = "wheat"


def _get_address(lat: float, lon: float) -> str:
    """Reverse-геокодирование координат. Возвращает строку адреса или координаты."""
    try:
        loc = geolocator.reverse((lat, lon), language="ru", timeout=10)
        return loc.address if loc else f"{lat:.4f}, {lon:.4f}"
    except Exception as e:
        logger.warning(f"Геокодирование недоступно: {e}")
        return f"{lat:.4f}°N {lon:.4f}°E"


def _format_agro_report(address: str, data: dict, indices: dict) -> str:
    """
    Формирует текст агроотчёта для Telegram.

    Структура (UX Layer — ≤ 3 действия на блок):
      1. Заголовок + адрес
      2. Алерты заморозков (если есть)
      3. ГТК (увлажнённость)
      4. ГДД (фенофаза)
      5. Баланс ЕТ0 (потребность в поливе)
      6. Итоговый совет
    """
    htc   = indices["htc"]
    gdd   = indices["gdd"]
    frost = indices["frost"]
    et0   = indices["et0_bal"]
    meta  = data["meta"]

    lines = [
        "🌾 АГРОМЕТЕОРОЛОГИЧЕСКИЙ АНАЛИЗ",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📍 {address}",
        f"🏔 Высота: {meta['elevation']:.0f} м н.у.м.",
        "",
    ]

    # ── Алерты заморозков ────────────────────────────────────────────────────
    if frost["alerts"]:
        lines.append("🌡 РИСК ЗАМОРОЗКОВ (7 суток):")
        for a in frost["alerts"]:
            lines.append(
                f"  {a['level']}  {a['date']}  Tмин={a['t_min']}°C  "
                f"(через {a['lead_hours']}ч)"
            )
            lines.append(f"  💬 {a['action']}")
        lines.append("")
    else:
        lines.append("✅ Заморозков в ближайшие 7 суток не ожидается")
        lines.append("")

    # ── ГТК ─────────────────────────────────────────────────────────────────
    htc_val = f"{htc['htc']:.2f}" if htc["htc"] is not None else "н/д"
    lines += [
        f"💧 УВЛАЖНЁННОСТЬ (ГТК Селянинова, {htc['window_days']} сут):",
        f"  ГТК = {htc_val}   {htc['interpretation']}",
        f"  Осадки: {htc['sum_precip_mm']} мм  |  ΣT>10°C: {htc['sum_t_above10']}°",
        "",
    ]

    # ── ГДД ─────────────────────────────────────────────────────────────────
    lines += [
        f"🌱 ФЕНОЛОГИЯ ({gdd['crop']}, Tbase={gdd['t_base']}°C):",
        f"  Накоплено ГДД: {gdd['gdd_past']}°  |  +7 сут прогноз: +{gdd['gdd_forecast_7d']}°",
        f"  Текущая фаза: {gdd['current_phase']}",
    ]
    if gdd["next_phase"]:
        lines.append(
            f"  До фазы '{gdd['next_phase']['name']}': ещё {gdd['next_phase']['gdd_needed']}° ГДД"
        )
    lines.append("")

    # ── ЕТ0 баланс ──────────────────────────────────────────────────────────
    lines += [
        f"🚿 ВОДНЫЙ БАЛАНС (последние {et0['window_days']} сут):",
        f"  Осадки: {et0['precip_sum_mm']} мм  |  ЕТ0 (FAO-56): {et0['et0_sum_mm']} мм",
        f"  {et0['status']}",
        "",
    ]

    # ── Источник данных ──────────────────────────────────────────────────────
    lines += [
        "─────────────────────────────────",
        "📡 Источник: Open-Meteo (GFS/ICON)",
        "📅 Прогноз: 7 сут  |  Архив: 14 сут",
    ]

    return "\n".join(lines)


def handle_crop_recommendation_request(bot, message):
    """
    Главный обработчик запроса на агрорекомендации.

    Синхронная функция (совместима с pyTelegramBotAPI).

    Args:
        bot:     экземпляр TeleBot
        message: сообщение с location или text-координатами
    """
    lat     = message.location.latitude
    lon     = message.location.longitude
    user_id = message.from_user.id

    logger.info(f"🚀 Анализ для {user_id}: {lat:.4f}, {lon:.4f}")

    address = _get_address(lat, lon)

    bot.send_message(
        message.chat.id,
        f"🌍 Запрашиваю метеоданные...\n"
        f"📍 {address}\n"
        f"⏳ Обычно 3–5 секунд."
    )

    try:
        # ── Первичный путь: Open-Meteo + агроиндексы ─────────────────────────
        weather_data = fetch_agro_data(lat, lon)
        indices      = compute_all_indices(weather_data["daily"], crop=DEFAULT_CROP)
        report       = _format_agro_report(address, weather_data, indices)

        bot.send_message(message.chat.id, report)
        logger.info(f"✅ Агроотчёт отправлен: {user_id}")

    except Exception as e:
        # ── Fallback: только география ────────────────────────────────────────
        logger.warning(f"⚠️ Open-Meteo недоступен, fallback: {e}")

        fallback_text = format_simple_recommendation(lat, lon)
        bot.send_message(
            message.chat.id,
            "⚠️ Метеоданные временно недоступны. Показываю упрощённые рекомендации:\n\n"
            + fallback_text
        )
