"""
Планировщик задач: событийные алерты + ежедневные отчёты.
APScheduler AsyncIOScheduler.
"""
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

logger = logging.getLogger(__name__)
_scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


async def start_scheduler(bot: Bot):
    """Запустить планировщик при старте бота."""
    # Проверка заморозков — каждые 6 часов
    _scheduler.add_job(
        check_frost_alerts,
        trigger="cron",
        hour="0,6,12,18",
        minute=10,
        args=[bot],
        id="frost_check",
        replace_existing=True,
    )
    # Ежедневный агроотчёт — в 7:00 МСК
    _scheduler.add_job(
        send_daily_digest,
        trigger="cron",
        hour=7,
        minute=0,
        args=[bot],
        id="daily_digest",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("✅ Планировщик алертов запущен")


async def check_frost_alerts(bot: Bot):
    """Проверить риск заморозков для всех пользователей с полями."""
    from src.database.crud import get_all_active_users
    from src.api.open_meteo import fetch_agro_data
    from src.agro.indices import calc_frost_risk
    from src.bot.alerts import should_send_alert, format_frost_alert, mark_alert_sent
    
    logger.info(f"[{datetime.now():%H:%M}] Проверка заморозков...")
    
    async for user in get_all_active_users():
        if not (user.latitude and user.longitude):
            continue
        try:
            df_daily, _ = await fetch_agro_data(user.latitude, user.longitude)
            if df_daily is None:
                continue
            
            frost = calc_frost_risk(df_daily)
            if not frost.get("alert"):
                continue
            
            # Дедупликация: не присылать одно уведомление дважды
            alert_key = f"frost_{user.telegram_id}_{frost['event_date']}"
            if not await should_send_alert(alert_key):
                continue
            
            text = format_frost_alert(frost, user.selected_crop)
            await bot.send_message(user.telegram_id, text, parse_mode="HTML")
            await mark_alert_sent(alert_key, ttl_hours=20)
            
            logger.info(f"📨 Алерт заморозка → user {user.telegram_id}")
        
        except Exception as e:
            logger.error(f"Ошибка алерта для user {user.telegram_id}: {e}")


async def send_daily_digest(bot: Bot):
    """Ежедневный краткий агроотчёт (опт-ин пользователи)."""
    from src.database.crud import get_users_with_daily_digest
    
    async for user in get_users_with_daily_digest():
        try:
            # Генерация краткого отчёта (существующая логика)
            from src.bot.handlers.agro import generate_agro_summary
            text = await generate_agro_summary(user)
            await bot.send_message(user.telegram_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка ежедневного отчёта для {user.telegram_id}: {e}")
