"""
Форматирование алертов и дедупликация.
Хранение sent_alert хэшей в памяти (MVP) или Redis (продакшн).
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# In-memory store: {key: expiry_datetime}
# Для продакшна заменить на Redis: await redis.setex(key, ttl, "1")
_sent_alerts: Dict[str, datetime] = {}
_lock = asyncio.Lock()


async def should_send_alert(key: str) -> bool:
    """True если алерт с таким ключом ещё не отправлялся."""
    async with _lock:
        expiry = _sent_alerts.get(key)
        if expiry is None or datetime.now() > expiry:
            return True
        return False


async def mark_alert_sent(key: str, ttl_hours: int = 20):
    """Отметить алерт как отправленный на ttl_hours часов."""
    async with _lock:
        _sent_alerts[key] = datetime.now() + timedelta(hours=ttl_hours)
        # Очистка устаревших ключей
        now = datetime.now()
        expired = [k for k, v in _sent_alerts.items() if v < now]
        for k in expired:
            del _sent_alerts[k]


def format_frost_alert(frost: dict, crop: str = None) -> str:
    """
    Форматирует алерт заморозка для Telegram (HTML).
    
    frost = {
        "min_temp": -2.5,
        "event_date": "2026-04-15",
        "lead_hours": 36,
        "probability": 78,
    }
    """
    temp = frost.get("min_temp", "?")
    date = frost.get("event_date", "?")
    lead = frost.get("lead_hours", 0)
    prob = frost.get("probability", "?")
    
    crop_line = f"\n🌾 Культура: <b>{crop}</b>" if crop else ""
    
    return (
        f"🌡 <b>ПРЕДУПРЕЖДЕНИЕ О ЗАМОРОЗКЕ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Дата: <b>{date}</b>\n"
        f"🌡 Мин. температура: <b>{temp}°C</b>\n"
        f"⏱ До события: <b>{lead} часов</b>\n"
        f"📊 Вероятность: <b>{prob}%</b>"
        f"{crop_line}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>Рекомендация:</b> Примите меры по защите посевов.\n"
        f"📡 Источник: Open-Meteo | Обновлено: {datetime.now():%H:%M}"
    )
