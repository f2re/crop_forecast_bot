from __future__ import annotations

from src.agro.crop_catalog import get_crop_name


def format_frost_alert(event: dict, crop: str | None = None) -> str:
    crop_line = f"\n🌾 Культура: <b>{get_crop_name(crop)}</b>" if crop else ""
    level = "критический" if event.get("level") == "critical" else "предупредительный"
    return (
        "🌡 <b>Температурный риск для поля</b>\n"
        f"📅 Локальное время модели: <b>{event.get('date_local', '?')}</b>\n"
        f"🌡 Прогноз Tmin воздуха: <b>{event.get('t_min', '?')}°C</b>\n"
        f"⏱ Заблаговременность: <b>около {event.get('lead_hours', 0)} ч</b>\n"
        f"⚠️ Уровень: <b>{level}</b>"
        f"{crop_line}\n\n"
        "Это скрининг по температуре воздуха на высоте 2 м, а не измерение "
        "температуры растений. Проверьте локальный прогноз, фазу культуры и "
        "микрорельеф перед решением о защитных мерах."
    )
