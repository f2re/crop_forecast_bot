from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from src.agro.pest_phenology import choose_pest_notification
from src.api.open_meteo import OpenMeteoError
from src.application.pest_monitoring import (
    PestMonitorRequest,
    evaluate_pest_monitors,
)
from src.application.ports.soil_temperature import SoilTemperatureProvider
from src.application.ports.weather import WeatherProvider
from src.bot.pest_messages import format_pest_notification
from src.database.pest_monitoring import (
    PestMonitoringTarget,
    list_enabled_pest_targets,
    mark_pest_monitor_checked,
)
from src.database.pest_rollover import rollover_calendar_pest_monitor
from src.domain.pests import automatic_biofix_date, validate_pest_for_crop
from src.infrastructure.coordination import (
    CoordinationBackend,
    LeaseLostError,
    RenewingLease,
)

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], AsyncSession]

_PEST_LOCAL_START_HOUR = 7
_PEST_LOCAL_END_HOUR = 11
_PEST_JOB_LOCK_TTL = 4 * 60 * 60
_PEST_NOTIFICATION_RESERVATION_TTL = 5 * 60
_PEST_NOTIFICATION_DEDUP_TTL = 120 * 24 * 60 * 60
_PEST_LEASE_RENEW_SECONDS = 60.0


def register_pest_monitoring_job(
    bot: Bot,
    session_factory: SessionFactory,
    coordination: CoordinationBackend,
) -> None:
    """Attach one light hourly trigger to the existing APScheduler instance."""

    from src.bot.scheduler import get_scheduler

    get_scheduler().add_job(
        check_pest_monitoring,
        trigger="cron",
        hour="*",
        minute=35,
        args=[bot, session_factory, coordination, True],
        id="pest_monitoring",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )


def _local_datetime(
    timezone_name: str,
    now_utc: datetime | None = None,
) -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown pest-monitor timezone %r; using UTC", timezone_name)
        zone = ZoneInfo("UTC")
    current = now_utc or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(zone)


def pest_monitoring_is_due(
    timezone_name: str,
    last_checked_local_date: date | None,
    *,
    now_utc: datetime | None = None,
) -> bool:
    local_now = _local_datetime(timezone_name, now_utc)
    return (
        _PEST_LOCAL_START_HOUR <= local_now.hour < _PEST_LOCAL_END_HOUR
        and last_checked_local_date != local_now.date()
    )


async def _targets(session_factory: SessionFactory) -> list[PestMonitoringTarget]:
    async with session_factory() as session:
        return await list_enabled_pest_targets(session)


async def _mark_checked(
    session_factory: SessionFactory,
    monitor_id: int,
    *,
    local_date: date,
    stage_event_key: str | None = None,
    advance_event_key: str | None = None,
    notified_at: datetime | None = None,
) -> bool:
    async with session_factory() as session:
        return await mark_pest_monitor_checked(
            session,
            monitor_id,
            local_date=local_date,
            stage_event_key=stage_event_key,
            advance_event_key=advance_event_key,
            notified_at=notified_at,
        )


async def _rollover_calendar(
    session_factory: SessionFactory,
    target: PestMonitoringTarget,
    *,
    model,
    biofix_date: date,
) -> bool:
    async with session_factory() as session:
        return await rollover_calendar_pest_monitor(
            session,
            target.monitor_id,
            model=model,
            biofix_date=biofix_date,
        )


async def _send_once(
    coordination: CoordinationBackend,
    key: str,
    sender: Callable[[], Awaitable[object]],
) -> bool:
    lease = await coordination.acquire(key, _PEST_NOTIFICATION_RESERVATION_TTL)
    if lease is None:
        return False
    try:
        await sender()
    except Exception:
        try:
            await coordination.release(lease)
        except Exception:
            logger.exception("Failed to release pest notification reservation %s", key)
        raise
    if not await coordination.renew(lease, _PEST_NOTIFICATION_DEDUP_TTL):
        logger.error(
            "Pest reminder was sent but deduplication was not persisted: %s",
            key,
        )
    return True


def _group_by_field(
    targets: list[PestMonitoringTarget],
) -> dict[int, list[PestMonitoringTarget]]:
    grouped: dict[int, list[PestMonitoringTarget]] = defaultdict(list)
    for target in targets:
        grouped[target.field_id].append(target)
    return dict(grouped)


async def check_pest_monitoring(
    bot: Bot,
    session_factory: SessionFactory,
    coordination: CoordinationBackend,
    due_only: bool = True,
    *,
    provider: WeatherProvider | None = None,
    soil_provider: SoilTemperatureProvider | None = None,
    now_utc: datetime | None = None,
    job_lock_ttl_seconds: int = _PEST_JOB_LOCK_TTL,
    renew_interval_seconds: float = _PEST_LEASE_RENEW_SECONDS,
) -> None:
    """Evaluate enabled pest monitors once per local day, sequentially by field."""

    job_guard = await RenewingLease.acquire(
        coordination,
        "job:pest-monitoring",
        ttl_seconds=job_lock_ttl_seconds,
        renew_interval_seconds=renew_interval_seconds,
    )
    if job_guard is None:
        logger.info("Pest monitoring skipped: another process owns the job lock")
        return

    try:
        async with job_guard:
            targets = await job_guard.run(_targets(session_factory))
            for field_targets in _group_by_field(targets).values():
                job_guard.ensure_owned()
                due_targets = [
                    target
                    for target in field_targets
                    if not due_only
                    or pest_monitoring_is_due(
                        target.timezone,
                        target.last_checked_local_date,
                        now_utc=now_utc,
                    )
                ]
                if not due_targets:
                    continue

                valid_targets: list[PestMonitoringTarget] = []
                requests: list[PestMonitorRequest] = []
                for original_target in due_targets:
                    target = original_target
                    try:
                        model = validate_pest_for_crop(
                            target.pest_key,
                            target.crop_key,
                        )
                    except ValueError as exc:
                        logger.warning(
                            "Ignoring invalid pest monitor %s: %s",
                            target.monitor_id,
                            exc,
                        )
                        continue

                    local_day = _local_datetime(
                        target.timezone,
                        now_utc,
                    ).date()
                    calendar_start = automatic_biofix_date(model, local_day)
                    if calendar_start is not None and (
                        target.biofix_date != calendar_start
                        or target.biofix_type != model.biofix_type
                        or target.model_version != model.model_version
                    ):
                        await job_guard.run(
                            _rollover_calendar(
                                session_factory,
                                target,
                                model=model,
                                biofix_date=calendar_start,
                            )
                        )
                        target = replace(
                            target,
                            biofix_date=calendar_start,
                            biofix_type=model.biofix_type,
                            model_version=model.model_version,
                            last_checked_local_date=None,
                            last_notified_stage=None,
                            last_notified_advance=None,
                        )

                    if target.model_version != model.model_version:
                        logger.warning(
                            "Pest monitor %s uses model version %s; current is %s. "
                            "User must reopen the monitor to accept the update.",
                            target.monitor_id,
                            target.model_version,
                            model.model_version,
                        )
                        continue
                    valid_targets.append(target)
                    requests.append(
                        PestMonitorRequest(
                            monitor_id=target.monitor_id,
                            pest_key=target.pest_key,
                            biofix_date=target.biofix_date,
                        )
                    )
                if not valid_targets:
                    continue

                first = valid_targets[0]
                calculation_day = _local_datetime(
                    first.timezone,
                    now_utc,
                ).date()
                try:
                    reports = await job_guard.run(
                        evaluate_pest_monitors(
                            first.latitude,
                            first.longitude,
                            tuple(requests),
                            provider=provider,
                            soil_provider=soil_provider,
                            today=calculation_day,
                        )
                    )
                except OpenMeteoError as exc:
                    logger.warning(
                        "Pest temperature data unavailable for field %s: %s",
                        first.field_id,
                        exc,
                    )
                    continue
                except ValueError as exc:
                    logger.warning(
                        "Pest calculation rejected for field %s: %s",
                        first.field_id,
                        exc,
                    )
                    continue

                for target, report in zip(valid_targets, reports, strict=True):
                    job_guard.ensure_owned()
                    local_day = _local_datetime(
                        report.timezone,
                        now_utc,
                    ).date()
                    notification = choose_pest_notification(
                        report.outlook,
                        last_notified_stage=target.last_notified_stage,
                        last_notified_advance=target.last_notified_advance,
                        today=local_day,
                    )
                    if notification is None:
                        await job_guard.run(
                            _mark_checked(
                                session_factory,
                                target.monitor_id,
                                local_date=local_day,
                            )
                        )
                        continue

                    key = (
                        "notification:pest-monitoring:"
                        f"{target.telegram_id}:{target.monitor_id}:"
                        f"{notification.event_key}"
                    )

                    async def send(
                        target: PestMonitoringTarget = target,
                        notification=notification,
                        outlook=report.outlook,
                    ) -> object:
                        return await bot.send_message(
                            target.telegram_id,
                            format_pest_notification(
                                notification,
                                outlook,
                                field_name=target.field_name,
                                crop_key=target.crop_key,
                            ),
                        )

                    try:
                        await job_guard.run(_send_once(coordination, key, send))
                    except LeaseLostError:
                        raise
                    except Exception:
                        logger.exception(
                            "Pest reminder failed for user %s monitor %s",
                            target.telegram_id,
                            target.monitor_id,
                        )
                        continue

                    stage_key = (
                        notification.event_key
                        if notification.kind == "current_window"
                        else None
                    )
                    advance_key = (
                        notification.event_key
                        if notification.kind == "approaching_window"
                        else None
                    )
                    await job_guard.run(
                        _mark_checked(
                            session_factory,
                            target.monitor_id,
                            local_date=local_day,
                            stage_event_key=stage_key,
                            advance_event_key=advance_key,
                            notified_at=datetime.now(timezone.utc),
                        )
                    )
    except LeaseLostError as exc:
        logger.error("Pest monitoring lost its distributed lock; aborting: %s", exc)
