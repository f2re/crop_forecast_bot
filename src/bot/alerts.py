from __future__ import annotations

from src.agro.crop_catalog import get_crop_name


def format_frost_alert(
    event: dict,
    crop: str | None = None,
    *,
    phase: str | None = None,
    field_name: str | None = None,
) -> str:
    crop_line = f"\n🌾 Культура: <b>{get_crop_name(crop)}</b>" if crop else ""
    phase_line = f"\n🌿 Фаза: <b>{phase}</b> (указана пользователем)" if phase else ""
    field_line = f"\n🗺 Поле: <b>{field_name}</b>" if field_name else ""
    elevation = event.get("elevation_m")
    elevation_line = (
        f"\n🏔 Высота модели: <b>{float(elevation):.0f} м</b>"
        if elevation is not None
        else ""
    )
    level = "критический" if event.get("level") == "critical" else "предупредительный"
    return (
        "🌡 <b>Температурный риск для поля</b>"
        f"{field_line}\n"
        f"📅 Локальное время модели: <b>{event.get('date_local', '?')}</b>\n"
        f"🌡 Прогноз Tmin воздуха: <b>{event.get('t_min', '?')}°C</b>\n"
        f"⏱ Заблаговременность: <b>около {event.get('lead_hours', 0)} ч</b>\n"
        f"⚠️ Уровень общего скрининга: <b>{level}</b>"
        f"{crop_line}{phase_line}{elevation_line}\n\n"
        "Это скрининг по температуре воздуха на высоте 2 м, а не температура "
        "поверхности растений и не порог повреждения культуры. Сверьте локальный "
        "прогноз, фактическую фазу и понижения микрорельефа."
    )
