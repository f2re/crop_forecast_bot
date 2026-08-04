from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.open_meteo_late_blight import OpenMeteoLateBlightProvider
from src.application.late_blight_screening import (
    generate_potato_late_blight_screening,
)
from src.application.ports.late_blight import (
    LateBlightWeatherProvider,
    LateBlightWeatherProviderError,
)
from src.application.risk_notification_delivery import (
    accepted_notification_time,
    send_risk_transition_once,
    was_notified_on_local_date,
)
from src.bot.late_blight_notification_messages import (
    format_late_blight_change_notification,
)
from src.database.biological_monitoring import (
    LateBlightMonitoringTarget,
    list_enabled_late_blight_targets,
    mark_late_blight_observed,
    save_late_blight_delivery_state,
)
from src.database.late_blight_scope import open_field_late_blight_season_ids
from src.domain.late_blight_delivery import plan_late_blight_delivery
from src.infrastructure.coordination import (
    CoordinationBackend,
    LeaseLostError,
    RenewingLease,
)

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], AsyncSession]

_RESERVATION_TTL_SECONDS = 5 * 60
_TRANSITION_TTL_SECONDS = 21 * 24 * 60 * 60
_DAILY_QUOTA_TTL_SECONDS = 36 * 60 * 60
_JOB_LOCK_TTL_SECONDS = 5 * 60 * 60
_LEASE_RENEW_INTERVAL_SECONDS = 60.0


def register_late_blight_monitoring_job(
    bot: Bot,
    session_factory: SessionFactory,
    coordination: CoordinationBackend,
) -> None:
    from src.bot.scheduler import get_scheduler

    get_scheduler().add_job(
        check_late_blight_monitoring,
        trigger="cron",
        hour="0,6,12,18",
        minute=25,
        args=[bot, session_factory, coordination],
        id="late_blight_monitoring",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=900,
    )


def _local_datetime(
    timezone_name: str,
    now_utc: datetime | None = None,
) -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown late-blight timezone %r; using UTC", timezone_name)
        zone = ZoneInfo("UTC")
    current = now_utc or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(zone)


async def _targets(
    session_factory: SessionFactory,
) -> list[LateBlightMonitoringTarget]:
    async with session_factory() as session:
        targets = await list_enabled_late_blight_targets(session)
        allowed_seasons = await open_field_late_blight_season_ids(
            session,
            tuple(dict.fromkeys(target.season_id for target in targets)),
        )
    skipped = [target for target in targets if target.season_id not in allowed_seasons]
    for target in skipped:
        logger.warning(
            "Late-blight monitor paused outside confirmed open field: "
            "user=%s field=%s season=%s",
            target.telegram_id,
            target.field_id,
            target.season_id,
        )
    return [target for target in targets if target.season_id in allowed_seasons]


async def _save_state(
    session_factory: SessionFactory,
    *,
    target: LateBlightMonitoringTarget,
    state,
    local_now: datetime,
    observed_at: datetime,
    notified_at: datetime | None = None,
) -> None:
    async with session_factory() as session:
        await save_late_blight_delivery_state(
            session,
            monitor_ids=target.monitor_ids,
            state=state,
            checked_local_date=local_now.date(),
            observed_at=observed_at,
            notified_at=notified_at,
        )


async def _mark_observed(
    session_factory: SessionFactory,
    *,
    target: LateBlightMonitoringTarget,
    local_now: datetime,
    observed_at: datetime,
) -> None:
    async with session_factory() as session:
        await mark_late_blight_observed(
            session,
            monitor_ids=target.monitor_ids,
            checked_local_date=local_now.date(),
            observed_at=observed_at,
        )


async def check_late_blight_monitoring(
    bot: Bot,
    session_factory: SessionFactory,
    coordination: CoordinationBackend,
    *,
    provider: LateBlightWeatherProvider | None = None,
    now_utc: datetime | None = None,
    job_lock_ttl_seconds: int = _JOB_LOCK_TTL_SECONDS,
    renew_interval_seconds: float = _LEASE_RENEW_INTERVAL_SECONDS,
) -> None:
    """Evaluate enabled open-field potato monitors and deliver period changes."""

    job_guard = await RenewingLease.acquire(
        coordination,
        "job:late-blight-monitoring",
        ttl_seconds=job_lock_ttl_seconds,
        renew_interval_seconds=renew_interval_seconds,
    )
    if job_guard is None:
        logger.info("Late-blight monitoring skipped: another process owns the lock")
        return

    resolved_provider = provider or OpenMeteoLateBlightProvider()
    try:
        async with job_guard:
            targets = await job_guard.run(_targets(session_factory))
            for target in targets:
                job_guard.ensure_owned()
                local_now = _local_datetime(target.timezone, now_utc)
                try:
                    outlook = await job_guard.run(
                        generate_potato_late_blight_screening(
                            target.latitude,
                            target.longitude,
                            provider=resolved_provider,
                            today=local_now.date(),
                        )
                    )
                    if not outlook.available:
                        await job_guard.run(
                            _mark_observed(
                                session_factory,
                                target=target,
                                local_now=local_now,
                                observed_at=outlook.retrieved_at,
                            )
                        )
                        logger.warning(
                            "Late-blight screen unavailable for user %s field %s: %s",
                            target.telegram_id,
                            target.field_id,
                            outlook.status,
                        )
                        continue

                    decision = plan_late_blight_delivery(
                        outlook.periods,
                        previous_state=target.delivery_state,
                        inoculum_context=target.inoculum_context,
                        mode=target.risk_delivery_mode,
                        local_datetime=local_now,
                        quiet_hours_start=target.quiet_hours_start,
                        quiet_hours_end=target.quiet_hours_end,
                    )
                    if decision.deferred:
                        await job_guard.run(
                            _mark_observed(
                                session_factory,
                                target=target,
                                local_now=local_now,
                                observed_at=outlook.retrieved_at,
                            )
                        )
                        logger.info(
                            "Late-blight change deferred for user %s field %s: %s",
                            target.telegram_id,
                            target.field_id,
                            decision.reason,
                        )
                        continue

                    if decision.change is None or decision.dedup_token is None:
                        await job_guard.run(
                            _save_state(
                                session_factory,
                                target=target,
                                state=decision.current_state,
                                local_now=local_now,
                                observed_at=outlook.retrieved_at,
                            )
                        )
                        continue

                    if (
                        decision.daily_quota_token is not None
                        and was_notified_on_local_date(
                            target.last_notified_at,
                            local_now,
                        )
                    ):
                        await job_guard.run(
                            _mark_observed(
                                session_factory,
                                target=target,
                                local_now=local_now,
                                observed_at=outlook.retrieved_at,
                            )
                        )
                        logger.info(
                            "Late-blight change retained by durable daily quota "
                            "for user %s field %s",
                            target.telegram_id,
                            target.field_id,
                        )
                        continue

                    transition_key = (
                        "notification:late-blight-transition:"
                        f"{target.telegram_id}:{target.monitor_id}:"
                        f"{decision.dedup_token}"
                    )
                    daily_quota_key = (
                        "notification:late-blight-day:"
                        f"{target.telegram_id}:{target.monitor_id}:"
                        f"{decision.daily_quota_token}"
                        if decision.daily_quota_token is not None
                        else None
                    )

                    async def send(
                        target: LateBlightMonitoringTarget = target,
                        decision=decision,
                        outlook=outlook,
                    ) -> object:
                        return await bot.send_message(
                            target.telegram_id,
                            format_late_blight_change_notification(
                                decision,
                                outlook,
                                field_name=target.field_name,
                            ),
                        )

                    outcome = await job_guard.run(
                        send_risk_transition_once(
                            coordination,
                            transition_key=transition_key,
                            transition_ttl_seconds=_TRANSITION_TTL_SECONDS,
                            reservation_ttl_seconds=_RESERVATION_TTL_SECONDS,
                            sender=send,
                            daily_quota_key=daily_quota_key,
                            daily_quota_ttl_seconds=(
                                _DAILY_QUOTA_TTL_SECONDS
                                if daily_quota_key is not None
                                else None
                            ),
                        )
                    )
                    if outcome == "deferred_daily":
                        await job_guard.run(
                            _mark_observed(
                                session_factory,
                                target=target,
                                local_now=local_now,
                                observed_at=outlook.retrieved_at,
                            )
                        )
                        continue

                    notified_at = accepted_notification_time(
                        outcome,
                        now=datetime.now(timezone.utc),
                    )
                    await job_guard.run(
                        _save_state(
                            session_factory,
                            target=target,
                            state=decision.current_state,
                            local_now=local_now,
                            observed_at=outlook.retrieved_at,
                            notified_at=notified_at,
                        )
                    )
                except LeaseLostError:
                    raise
                except LateBlightWeatherProviderError as exc:
                    logger.warning(
                        "Late-blight provider unavailable for user %s field %s: %s",
                        target.telegram_id,
                        target.field_id,
                        exc,
                    )
                except Exception:
                    logger.exception(
                        "Late-blight monitoring failed for user %s field %s",
                        target.telegram_id,
                        target.field_id,
                    )
    except LeaseLostError as exc:
        logger.error("Late-blight monitoring lost its distributed lock: %s", exc)
