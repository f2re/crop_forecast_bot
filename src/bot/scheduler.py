from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from src.agro.ensemble_risks import calc_ensemble_risks
from src.agro.indices import FROST_STATUS_INSUFFICIENT, calc_frost_risk
from src.api.open_meteo import OpenMeteoError, fetch_agro_data
from src.api.open_meteo_ensemble import (
    OpenMeteoEnsembleError,
    OpenMeteoEnsembleProvider,
)
from src.application.agro_report import generate_agro_report
from src.application.ports.risk import RiskForecastProvider
from src.bot.alerts import format_frost_alert, format_frost_data_unavailable
from src.bot.report_presentation import compact_agro_report
from src.bot.risk_alerts import (
    format_ensemble_data_unavailable,
    format_ensemble_risk_digest,
)
from src.database.notification_targets import (
    EnabledNotificationTarget,
    list_enabled_notification_targets,
)
from src.database.risk_delivery_state import (
    load_risk_delivery_state,
    save_risk_delivery_state,
)
from src.database.risk_history import (
    StoredRiskRun,
    prune_risk_runs_before,
    save_risk_run,
    set_signal_delivery,
)
from src.domain.risk import EnsembleForecastMeta, RiskOutlook
from src.domain.risk_delivery import (
    RiskEpisodeState,
    is_quiet_time,
    plan_risk_delivery,
)
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
_ENSEMBLE_RISK_DEDUP_TTL = 21 * 24 * 60 * 60
_ENSEMBLE_UNAVAILABLE_DEDUP_TTL = 20 * 60 * 60
_DAILY_DIGEST_DEDUP_TTL = 36 * 60 * 60
_FROST_JOB_LOCK_TTL = 5 * 60 * 60
_ENSEMBLE_JOB_LOCK_TTL = 5 * 60 * 60
_DAILY_JOB_LOCK_TTL = 6 * 60 * 60
_JOB_LEASE_RENEW_INTERVAL_SECONDS = 60.0
_DAILY_DIGEST_LOCAL_START_HOUR = 7
_DAILY_DIGEST_LOCAL_END_HOUR = 11
_MAX_RISK_ALERTS_PER_FIELD = 5


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


def _risk_delivery_preferences(
    target: object,
) -> tuple[str, int | None, int | None]:
    """Read new preferences while keeping old test/compatibility targets usable."""
    return (
        str(getattr(target, "risk_delivery_mode", "immediate")),
        getattr(target, "quiet_hours_start", None),
        getattr(target, "quiet_hours_end", None),
    )


async def start_scheduler(
    bot: Bot,
    session_factory: SessionFactory,
    coordination: CoordinationBackend,
) -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        return
    scheduler.add_job(
        check_weather_risk_alerts,
        trigger="cron",
        hour="0,6,12,18",
        minute=10,
        args=[bot, session_factory, coordination],
        id="weather_risk_check",
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
) -> list[EnabledNotificationTarget]:
    async with session_factory() as session:
        return await list_enabled_notification_targets(
            session,
            daily_digest_only=daily_digest_only,
            frost_alerts_only=frost_alerts_only,
        )


async def _record_risk_run(
    session_factory: SessionFactory,
    *,
    field_id: int,
    meta: EnsembleForecastMeta,
    outlook: RiskOutlook,
) -> StoredRiskRun:
    async with session_factory() as session:
        return await save_risk_run(
            session,
            field_id=field_id,
            meta=meta,
            outlook=outlook,
        )


async def _load_delivery_state(
    session_factory: SessionFactory,
    *,
    field_id: int,
    model: str,
    delivery_mode: str,
) -> tuple[RiskEpisodeState, ...]:
    async with session_factory() as session:
        state = await load_risk_delivery_state(
            session,
            field_id=field_id,
            model=model,
            delivery_mode=delivery_mode,
        )
    return () if state is None else state.episodes


async def _store_delivery_state(
    session_factory: SessionFactory,
    *,
    field_id: int,
    model: str,
    delivery_mode: str,
    episodes: tuple[RiskEpisodeState, ...],
    observed_at: datetime,
    notified_at: datetime | None = None,
) -> None:
    async with session_factory() as session:
        await save_risk_delivery_state(
            session,
            field_id=field_id,
            model=model,
            delivery_mode=delivery_mode,
            episodes=episodes,
            observed_at=observed_at,
            notified_at=notified_at,
        )


async def _set_risk_delivery(
    session_factory: SessionFactory,
    *,
    signal_id: int,
    state: str,
    notified_at: datetime | None = None,
) -> bool:
    async with session_factory() as session:
        return await set_signal_delivery(
            session,
            signal_id=signal_id,
            state=state,
            notified_at=notified_at,
        )


async def _set_many_risk_deliveries(
    session_factory: SessionFactory,
    *,
    signal_ids: tuple[int, ...],
    state: str,
    notified_at: datetime | None = None,
) -> None:
    for signal_id in signal_ids:
        await _set_risk_delivery(
            session_factory,
            signal_id=signal_id,
            state=state,
            notified_at=notified_at,
        )


async def _prune_risk_history(session_factory: SessionFactory) -> int:
    retention_days = get_settings().risk_history_retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    async with session_factory() as session:
        return await prune_risk_runs_before(session, cutoff=cutoff)


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


async def check_weather_risk_alerts(
    bot: Bot,
    session_factory: SessionFactory,
    coordination: CoordinationBackend,
    *,
    provider: RiskForecastProvider | None = None,
    job_lock_ttl_seconds: int = _ENSEMBLE_JOB_LOCK_TTL,
    renew_interval_seconds: float = _JOB_LEASE_RENEW_INTERVAL_SECONDS,
) -> None:
    """Persist accepted runs and notify only on semantic period changes."""

    job_guard = await RenewingLease.acquire(
        coordination,
        "job:weather-risk-check",
        ttl_seconds=job_lock_ttl_seconds,
        renew_interval_seconds=renew_interval_seconds,
    )
    if job_guard is None:
        logger.info("Weather-risk screening skipped: another process owns the job lock")
        return

    risk_provider = provider or OpenMeteoEnsembleProvider()
    logger.info(
        "[%s] Ensemble weather-risk screening started",
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
                    local_now = _local_datetime(target.timezone)
                    delivery_mode, quiet_start, quiet_end = (
                        _risk_delivery_preferences(target)
                    )
                    forecast = await job_guard.run(
                        risk_provider.fetch(target.latitude, target.longitude)
                    )
                    outlook = calc_ensemble_risks(
                        forecast,
                        as_of_date=local_now.date(),
                    )
                    if not outlook.available:
                        if is_quiet_time(local_now, quiet_start, quiet_end):
                            logger.info(
                                "Risk-data-unavailable notice deferred by quiet hours "
                                "for user %s field %s",
                                target.telegram_id,
                                target.field_id,
                            )
                            continue
                        unavailable_key = (
                            "notification:weather-risk-data-unavailable:"
                            f"{target.telegram_id}:{target.field_id}:"
                            f"{local_now.date().isoformat()}"
                        )

                        async def send_unavailable(
                            target=target,
                            reason: str = outlook.status,
                        ) -> object:
                            return await bot.send_message(
                                target.telegram_id,
                                format_ensemble_data_unavailable(
                                    target.field_name,
                                    reason,
                                ),
                            )

                        job_guard.ensure_owned()
                        await job_guard.run(
                            _send_once(
                                coordination,
                                unavailable_key,
                                _ENSEMBLE_UNAVAILABLE_DEDUP_TTL,
                                send_unavailable,
                            )
                        )
                        continue

                    stored_run = await job_guard.run(
                        _record_risk_run(
                            session_factory,
                            field_id=target.field_id,
                            meta=forecast.meta,
                            outlook=outlook,
                        )
                    )
                    previous_state = await job_guard.run(
                        _load_delivery_state(
                            session_factory,
                            field_id=target.field_id,
                            model=forecast.meta.model,
                            delivery_mode=delivery_mode,
                        )
                    )
                    decision = plan_risk_delivery(
                        outlook.events,
                        mode=delivery_mode,
                        local_datetime=local_now,
                        previous_state=previous_state,
                        quiet_hours_start=quiet_start,
                        quiet_hours_end=quiet_end,
                        max_events=_MAX_RISK_ALERTS_PER_FIELD,
                    )
                    if decision.deferred:
                        logger.info(
                            "Weather-risk delivery deferred for user %s field %s: %s",
                            target.telegram_id,
                            target.field_id,
                            decision.reason,
                        )
                        continue
                    if not decision.changes or decision.dedup_token is None:
                        await job_guard.run(
                            _store_delivery_state(
                                session_factory,
                                field_id=target.field_id,
                                model=forecast.meta.model,
                                delivery_mode=delivery_mode,
                                episodes=decision.current_state,
                                observed_at=forecast.meta.retrieved_at,
                            )
                        )
                        continue

                    signal_ids: list[int] = []
                    for event in decision.events:
                        signal_id = stored_run.signal_ids.get(
                            (event.risk_type, event.event_date)
                        )
                        if signal_id is None:
                            raise RuntimeError(
                                "Persisted risk signal is missing from the run"
                            )
                        signal_ids.append(signal_id)
                    selected_signal_ids = tuple(signal_ids)
                    alert_key = (
                        "notification:weather-risk-digest:"
                        f"{target.telegram_id}:{target.field_id}:"
                        f"{decision.dedup_token}"
                    )

                    async def send_digest(
                        target=target,
                        events=decision.events,
                        changes=decision.changes,
                        priority_bypass: bool = decision.priority_bypass,
                    ) -> object:
                        return await bot.send_message(
                            target.telegram_id,
                            format_ensemble_risk_digest(
                                events,
                                outlook,
                                field_name=target.field_name,
                                crop=target.selected_crop,
                                crops=target.crop_keys,
                                phase=target.phenological_phase,
                                delivery_mode=delivery_mode,
                                priority_bypass=priority_bypass,
                                changes=changes,
                            ),
                        )

                    await job_guard.run(
                        _set_many_risk_deliveries(
                            session_factory,
                            signal_ids=selected_signal_ids,
                            state="sending",
                        )
                    )
                    try:
                        sent = await job_guard.run(
                            _send_once(
                                coordination,
                                alert_key,
                                _ENSEMBLE_RISK_DEDUP_TTL,
                                send_digest,
                            )
                        )
                    except LeaseLostError:
                        raise
                    except Exception:
                        await job_guard.run(
                            _set_many_risk_deliveries(
                                session_factory,
                                signal_ids=selected_signal_ids,
                                state="failed",
                            )
                        )
                        raise
                    notified_at = datetime.now(timezone.utc) if sent else None
                    await job_guard.run(
                        _set_many_risk_deliveries(
                            session_factory,
                            signal_ids=selected_signal_ids,
                            state="sent" if sent else "deduplicated",
                            notified_at=notified_at,
                        )
                    )
                    await job_guard.run(
                        _store_delivery_state(
                            session_factory,
                            field_id=target.field_id,
                            model=forecast.meta.model,
                            delivery_mode=delivery_mode,
                            episodes=decision.current_state,
                            observed_at=forecast.meta.retrieved_at,
                            notified_at=notified_at,
                        )
                    )
                except LeaseLostError:
                    raise
                except OpenMeteoEnsembleError as exc:
                    logger.warning(
                        "Ensemble provider unavailable for user %s field %s: %s",
                        target.telegram_id,
                        target.field_id,
                        exc,
                    )
                except Exception:
                    logger.exception(
                        "Weather-risk alert failed for user %s field %s",
                        target.telegram_id,
                        target.field_id,
                    )
            job_guard.ensure_owned()
            deleted = await job_guard.run(_prune_risk_history(session_factory))
            if deleted:
                logger.info("Pruned %s expired risk forecast runs", deleted)
    except LeaseLostError as exc:
        logger.error(
            "Weather-risk screening lost its distributed lock; aborting: %s",
            exc,
        )


async def check_frost_alerts(
    bot: Bot,
    session_factory: SessionFactory,
    coordination: CoordinationBackend,
    *,
    job_lock_ttl_seconds: int = _FROST_JOB_LOCK_TTL,
    renew_interval_seconds: float = _JOB_LEASE_RENEW_INTERVAL_SECONDS,
) -> None:
    """Retained deterministic 7-day frost screen for compatibility and manual use."""

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
                            target=target,
                            reason: str = str(risk["status_note"]),
                        ) -> object:
                            return await bot.send_message(
                                target.telegram_id,
                                format_frost_data_unavailable(
                                    target.field_name,
                                    reason,
                                ),
                            )

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
                            target=target,
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
                local_today = _local_datetime(target.timezone).date()
                digest_key = (
                    f"notification:digest:{target.telegram_id}:{target.field_id}:"
                    f"{local_today.isoformat()}"
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
                    report_text = compact_agro_report(
                        report.text,
                        season_start_date=target.season_start_date,
                        today=local_today,
                        source="Open-Meteo",
                    )

                    async def send(
                        report_text: str = report_text,
                        target=target,
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
