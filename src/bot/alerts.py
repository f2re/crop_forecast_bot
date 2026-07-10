from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

_sent_alerts: dict[str, datetime] = {}
_lock = asyncio.Lock()


async def should_send_alert(key: str) -> bool:
    async with _lock:
        expiry = _sent_alerts.get(key)
        return expiry is None or datetime.utcnow() > expiry


async def mark_alert_sent(key: str, ttl_hours: int = 20) -> None:
    async with _lock:
        now = datetime.utcnow()
        _sent_alerts[key] = now + timedelta(hours=ttl_hours)
        expired = [stored_key for stored_key, expiry in _sent_alerts.items() if expiry < now]
        for stored_key in expired:
            _sent_alerts.pop(stored_key, None)


def format_frost_alert(event: dict, crop: str | None = None) -> str:
    crop_line = f"\n🌾 Культура: <b>{crop}</b>" if crop else ""
    level = "критический" if event.get("level") == "critical" else "предупредительный"
    return (
        "🌡 <b>Температурный риск для поля</b>\n"
        f"📅 Локальное время модели: <b>{event.get('date_local', '?')}</b>\n"
        f"🌡 Прогноз Tmin воздуха: <b>{event.get('t_min', '?')}°C</b>\n"
        f"⏱ Заблаговременность: <b>около {event.get('lead_hours', 0)} ч</b>\n"
        f"⚠️ Уровень: <b>{level}</b>"
        f"{crop_line}\n\n"
        "Это скрининг по температуре воздуха на высоте 2 м, а не измерение температуры растений. "
        "Проверьте локальный прогноз, фазу культуры и микрорельеф перед решением о защитных мерах."
    )
