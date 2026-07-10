from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from src.agro.indices import calc_frost_risk
from src.api.open_meteo import OpenMeteoError, fetch_agro_data
from src.application.agro_report import generate_agro_report
from src.bot.alerts import format_frost_alert, mark_alert_sent, should_send_alert
from src.database.crud import get_all_active_users, get_users_with_daily_digest

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], AsyncSession]
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=get_settings().scheduler_timezone)
    return _scheduler


async def start_scheduler(bot: Bot, session_factory: SessionFactory) -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        return
    scheduler.add_job(
        check_frost_alerts,
        trigger="cron",
        hour="0,6,12,18",
        minute=10,
        args=[bot, session_factory],
        id="frost_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=900,
    )
    scheduler.add_job(
        send_daily_digest,
        trigger="cron",
        hour=7,
        minute=0,
        args=[bot, session_factory],
        id="daily_digest",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )
    scheduler.start()
    logger.info("Scheduler started")


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


async def check_frost_alerts(bot: Bot, session_factory: SessionFactory) -> None:
    logger.info("[%s] Frost screening started", datetime.now().isoformat(timespec="minutes"))
    async with session_factory() as session:
        async for user in get_all_active_users(session):
            try:
                weather = await fetch_agro_data(user.latitude, user.longitude)
                risk = calc_frost_risk(
                    weather.daily,
                    utc_offset_seconds=weather.meta.utc_offset_seconds,
                )
                for event in risk["alerts"]:
                    alert_key = (
                        f"frost:{user.telegram_id}:{event['event_date']}:"
                        f"{event['t_min']:.1f}"
                    )
                    if not await should_send_alert(alert_key):
                        continue
                    await bot.send_message(
                        user.telegram_id,
                        format_frost_alert(event, user.selected_crop),
                    )
                    await mark_alert_sent(alert_key, ttl_hours=20)
            except OpenMeteoError as exc:
                logger.warning("Open-Meteo unavailable for user %s: %s", user.telegram_id, exc)
            except Exception:
                logger.exception("Frost alert failed for user %s", user.telegram_id)


async def send_daily_digest(bot: Bot, session_factory: SessionFactory) -> None:
    async with session_factory() as session:
        async for user in get_users_with_daily_digest(session):
            try:
                report = await generate_agro_report(
                    user.latitude,
                    user.longitude,
                    user.selected_crop or "wheat",
                )
                await bot.send_message(user.telegram_id, report.text)
            except Exception:
                logger.exception("Daily digest failed for user %s", user.telegram_id)
