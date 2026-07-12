from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from src.agro.indices import FROST_STATUS_INSUFFICIENT, calc_frost_risk
from src.api.open_meteo import OpenMeteoError, fetch_agro_data
from src.application.agro_report import generate_agro_report
from src.bot.alerts import format_frost_alert, format_frost_data_unavailable
from src.database.crud import NotificationTarget
from src.database.notification_targets import list_enabled_notification_targets
from src.infrastructure.coordination import (
    CoordinationBackend,
    LeaseLostError,
    RenewingLease,
)

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], AsyncSession]
_scheduler: AsyncIOScheduler | None = None

_NOTIFICATION_RESERVATION_TTL = 5 * 60
_FROST_DEDUP_TTL = 20 * 60 * 60
_FROST_UNAVAILABLE_DEDUP_TTL = 20 * 60 * 60
_DAILY_DIGEST_DEDUP_TTL = 36 * 60 * 60
_FROST_JOB_LOCK_TTL = 5 * 60 * 60
_DAILY_JOB_LOCK_TTL = 6 * 60 * 60
_JOB_LEASE_RENEW_INTERVAL_SECONDS = 60.0
_DAILY_DIGEST_LOCAL_START_HOUR = 7
_DAILY_DIGEST_LOCAL_END_HOUR = 11


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=get_settings().scheduler_timezone)
    return _scheduler


def _field_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown field timezone %r; using UTC", timezone_name)
        return ZoneInfo("UTC")


def _local_datetime(
    timezone_name: str,
    now_utc: datetime | None = None,
) -> datetime:
    current = now_utc or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(_field_timezone(timezone_name))


def _local_date(timezone_name: str, now_utc: datetime | None = None) -> str:
    return _local_datetime(timezone_name, now_utc).date().isoformat()


def _daily_digest_is_due(
    timezone_name: str,
    now_utc: datetime | None = None,
) -> bool:
    local_hour = _local_datetime(timezone_name, now_utc).hour
    return _DAILY_DIGEST_LOCAL_START_HOUR <= local_hour < _DAILY_DIGEST_LOCAL_END_HOUR


async def start_scheduler(
    bot: Bot,
    session_factory: SessionFactory,
    coordination: CoordinationBackend,
) -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        return
    scheduler.add_job(
        check_frost_alerts,
        trigger="cron",
        hour="0,6,12,18",
        minute=10,
        args=[bot, session_factory, coordination],
        id="frost_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=900,
    )
    scheduler.add_job(
        send_daily_digest,
        trigger="cron",
        hour="*",
        minute=5,
        args=[bot, session_factory, coordination, True],
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


async def _targets(
    session_factory: SessionFactory,
    *,
    daily_digest_only: bool = False,
    frost_alerts_only: bool = False,
) -> list[NotificationTarget]:
    async with session_factory() as session:
        return await list_enabled_notification_targets(
            session,
            daily_digest_only=daily_digest_only,
            frost_alerts_only=frost_alerts_only,
        )


async def _send_once(
    coordination: CoordinationBackend,
    key: str,
    committed_ttl_seconds: int,
    sender: Callable[[], Awaitable[object]],
) -> bool:
    lease = await coordination.acquire(key, _NOTIFICATION_RESERVATION_TTL)
    if lease is None:
        return False

    try:
        await sender()
    except Exception:
        try:
            await coordination.release(lease)
        except Exception:
            logger.exception("Failed to release notification reservation %s", key)
        raise
    if not await coordination.renew(lease, committed_ttl_seconds):
        logger.error(
            "Notification was sent but its deduplication lease was not persisted: %s",
            key,
        )
    return True


async def check_frost_alerts(
    bot: Bot,
    session_factory: SessionFactory,
    coordination: CoordinationBackend,
    *,
    job_lock_ttl_seconds: int = _FROST_JOB_LOCK_TTL,
    renew_interval_seconds: float = _JOB_LEASE_RENEW_INTERVAL_SECONDS,
) -> None:
    job_guard = await RenewingLease.acquire(
        coordination,
        "job:frost-check",
        ttl_seconds=job_lock_ttl_seconds,
        renew_interval_seconds=renew_interval_seconds,
    )
    if job_guard is None:
        logger.info("Frost screening skipped: another process owns the job lock")
        return

    logger.info(
        "[%s] Frost screening started",
        datetime.now().isoformat(timespec="minutes"),
    )
    try:
        async with job_guard:
            targets = await job_guard.run(
                _targets(session_factory, frost_alerts_only=True)
            )
            for target in targets:
                job_guard.ensure_owned()
                try:
                    weather = await job_guard.run(
                        fetch_agro_data(target.latitude, target.longitude)
                    )
                    job_guard.ensure_owned()
                    risk = calc_frost_risk(
                        weather.daily,
                        utc_offset_seconds=weather.meta.utc_offset_seconds,
                        crop=target.selected_crop,
                        phase=target.phenological_phase,
                        elevation_m=weather.meta.elevation_m,
                    )
                    if risk["status"] == FROST_STATUS_INSUFFICIENT:
                        logger.warning(
                            "Frost screening unavailable for user %s field %s: %s",
                            target.telegram_id,
                            target.field_id,
                            risk["status_note"],
                        )
                        unavailable_key = (
                            "notification:frost-data-unavailable:"
                            f"{target.telegram_id}:{target.field_id}:"
                            f"{_local_date(target.timezone)}"
                        )

                        async def send_unavailable(
                            target: NotificationTarget = target,
                            reason: str = str(risk["status_note"]),
                        ) -> object:
                            return await bot.send_message(
                                target.telegram_id,
                                format_frost_data_unavailable(
                                    target.field_name,
                                    reason,
                                ),
                            )

                        # A notification has its own lease. Once acquired, let
                        # the in-flight Telegram operation settle even if the
                        # broader job lease is lost; another worker cannot send
                        # the same field/day notification concurrently.
                        job_guard.ensure_owned()
                        await _send_once(
                            coordination,
                            unavailable_key,
                            _FROST_UNAVAILABLE_DEDUP_TTL,
                            send_unavailable,
                        )
                        continue
                    for event in risk["alerts"]:
                        alert_key = (
                            f"notification:frost:{target.telegram_id}:{target.field_id}:"
                            f"{event['event_date']}:{event['level']}"
                        )

                        async def send(
                            event: dict = event,
                            target: NotificationTarget = target,
                        ) -> object:
                            return await bot.send_message(
                                target.telegram_id,
                                format_frost_alert(
                                    event,
                                    target.selected_crop,
                                    phase=target.phenological_phase,
                                    field_name=target.field_name,
                                ),
                            )

                        job_guard.ensure_owned()
                        await _send_once(
                            coordination,
                            alert_key,
                            _FROST_DEDUP_TTL,
                            send,
                        )
                except LeaseLostError:
                    raise
                except OpenMeteoError as exc:
                    logger.warning(
                        "Open-Meteo unavailable for user %s field %s: %s",
                        target.telegram_id,
                        target.field_id,
                        exc,
                    )
                except Exception:
                    logger.exception(
                        "Frost alert failed for user %s field %s",
                        target.telegram_id,
                        target.field_id,
                    )
    except LeaseLostError as exc:
        logger.error("Frost screening lost its distributed lock; aborting: %s", exc)
        return


async def send_daily_digest(
    bot: Bot,
    session_factory: SessionFactory,
    coordination: CoordinationBackend,
    due_only: bool = False,
    *,
    job_lock_ttl_seconds: int = _DAILY_JOB_LOCK_TTL,
    renew_interval_seconds: float = _JOB_LEASE_RENEW_INTERVAL_SECONDS,
) -> None:
    job_guard = await RenewingLease.acquire(
        coordination,
        "job:daily-digest",
        ttl_seconds=job_lock_ttl_seconds,
        renew_interval_seconds=renew_interval_seconds,
    )
    if job_guard is None:
        logger.info("Daily digest skipped: another process owns the job lock")
        return

    try:
        async with job_guard:
            targets = await job_guard.run(
                _targets(session_factory, daily_digest_only=True)
            )
            for target in targets:
                job_guard.ensure_owned()
                if due_only and not _daily_digest_is_due(target.timezone):
                    continue
                digest_key = (
                    f"notification:digest:{target.telegram_id}:{target.field_id}:"
                    f"{_local_date(target.timezone)}"
                )
                try:
                    report = await job_guard.run(
                        generate_agro_report(
                            target.latitude,
                            target.longitude,
                            target.selected_crop,
                            season_start_date=target.season_start_date,
                            phenological_phase=target.phenological_phase,
                            field_name=target.field_name,
                        )
                    )

                    async def send(
                        report_text: str = report.text,
                        target: NotificationTarget = target,
                    ) -> object:
                        return await bot.send_message(target.telegram_id, report_text)

                    job_guard.ensure_owned()
                    await _send_once(
                        coordination,
                        digest_key,
                        _DAILY_DIGEST_DEDUP_TTL,
                        send,
                    )
                except LeaseLostError:
                    raise
                except Exception:
                    logger.exception(
                        "Daily digest failed for user %s field %s",
                        target.telegram_id,
                        target.field_id,
                    )
    except LeaseLostError as exc:
        logger.error("Daily digest lost its distributed lock; aborting: %s", exc)
        return
