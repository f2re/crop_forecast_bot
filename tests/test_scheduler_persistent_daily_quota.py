from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import src.bot.scheduler as scheduler_module
from src.bot.scheduler import check_weather_risk_alerts
from src.database.notification_targets import EnabledNotificationTarget
from src.database.risk_delivery_state import StoredRiskDeliveryState
from src.database.risk_history import StoredRiskRun
from src.domain.risk import EnsembleForecastData, EnsembleForecastMeta
from src.infrastructure.coordination import MemoryCoordination


class ElevatedHeatProvider:
    async def fetch(self, latitude: float, longitude: float) -> EnsembleForecastData:
        rows = [
            {
                "local_date": date(2026, 8, 5),
                "member_id": f"m{member:02d}",
                "t_min_c": 18.0,
                "t_max_c": 33.0 if member < 10 else 28.0,
                "precip_mm": 0.0,
                "wind_gust_ms": 5.0,
                "cape_j_kg": 100.0,
            }
            for member in range(31)
        ]
        return EnsembleForecastData(
            meta=EnsembleForecastMeta(
                latitude=latitude,
                longitude=longitude,
                elevation_m=100.0,
                timezone="Europe/Moscow",
                source="test",
                model="gfs_seamless",
                retrieved_at=datetime(2026, 8, 3, 12, tzinfo=timezone.utc),
                member_count=31,
                forecast_days=1,
            ),
            daily_members=pd.DataFrame(rows),
        )


class NoTelegramBot:
    async def send_message(self, chat_id: int, text: str) -> object:
        raise AssertionError("Telegram must not be called")


def _target() -> EnabledNotificationTarget:
    return EnabledNotificationTarget(
        telegram_id=1001,
        field_id=42,
        field_name="Северное",
        latitude=55.75,
        longitude=37.62,
        timezone="Europe/Moscow",
        elevation_m=100.0,
        elevation_source="test",
        selected_crop="wheat",
        season_start_date=None,
        phenological_phase=None,
        daily_digest_enabled=False,
        frost_alerts_enabled=True,
        risk_delivery_mode="digest",
        quiet_hours_start=None,
        quiet_hours_end=None,
        crop_keys=("wheat",),
    )


def _patch_shared(monkeypatch: pytest.MonkeyPatch, delivery_states: list[str]) -> None:
    async def fake_targets(session_factory, **kwargs):
        return [_target()]

    async def fake_record(session_factory, **kwargs):
        return StoredRiskRun(
            run_id=1,
            signal_ids={("heat", date(2026, 8, 5)): 99},
            created=True,
        )

    async def fake_delivery(session_factory, *, state, **kwargs):
        delivery_states.append(state)
        return True

    async def fake_prune(session_factory):
        return 0

    monkeypatch.setattr(scheduler_module, "_targets", fake_targets)
    monkeypatch.setattr(scheduler_module, "_record_risk_run", fake_record)
    monkeypatch.setattr(scheduler_module, "_set_risk_delivery", fake_delivery)
    monkeypatch.setattr(scheduler_module, "_prune_risk_history", fake_prune)
    monkeypatch.setattr(
        scheduler_module,
        "_local_datetime",
        lambda timezone_name, now_utc=None: datetime(
            2026,
            8,
            3,
            16,
            tzinfo=ZoneInfo("Europe/Moscow"),
        ),
    )


@pytest.mark.asyncio
async def test_postgresql_last_notified_at_blocks_second_daily_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery_states: list[str] = []
    stored_baselines: list[object] = []
    _patch_shared(monkeypatch, delivery_states)

    async def fake_load(session_factory, **kwargs):
        return StoredRiskDeliveryState(
            field_id=42,
            model="gfs_seamless",
            delivery_mode="digest",
            episodes=(),
            last_observed_at=datetime(2026, 8, 3, 6),
            last_notified_at=datetime(2026, 8, 3, 10),
        )

    async def fake_store(session_factory, **kwargs):
        stored_baselines.append(kwargs)

    async def forbidden_transition(*args, **kwargs):
        raise AssertionError("Redis transition path must not be entered")

    monkeypatch.setattr(scheduler_module, "_load_delivery_state", fake_load)
    monkeypatch.setattr(scheduler_module, "_store_delivery_state", fake_store)
    monkeypatch.setattr(
        scheduler_module,
        "send_risk_transition_once",
        forbidden_transition,
    )

    coordination = MemoryCoordination(namespace="persistent-daily-quota")
    try:
        await check_weather_risk_alerts(
            NoTelegramBot(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            coordination,
            provider=ElevatedHeatProvider(),
        )
    finally:
        await coordination.close()

    assert delivery_states == ["deferred"]
    assert stored_baselines == []


@pytest.mark.asyncio
async def test_already_delivered_transition_restores_durable_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery_states: list[str] = []
    stored_baselines: list[dict[str, object]] = []
    _patch_shared(monkeypatch, delivery_states)

    async def fake_load(session_factory, **kwargs):
        return None

    async def fake_store(session_factory, **kwargs):
        stored_baselines.append(kwargs)

    async def recovered_transition(*args, **kwargs):
        return "already_delivered"

    monkeypatch.setattr(scheduler_module, "_load_delivery_state", fake_load)
    monkeypatch.setattr(scheduler_module, "_store_delivery_state", fake_store)
    monkeypatch.setattr(
        scheduler_module,
        "send_risk_transition_once",
        recovered_transition,
    )

    coordination = MemoryCoordination(namespace="persistent-daily-recovery")
    try:
        await check_weather_risk_alerts(
            NoTelegramBot(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            coordination,
            provider=ElevatedHeatProvider(),
        )
    finally:
        await coordination.close()

    assert delivery_states == ["sending", "deduplicated"]
    assert len(stored_baselines) == 1
    notified_at = stored_baselines[0]["notified_at"]
    assert isinstance(notified_at, datetime)
    assert notified_at.tzinfo is timezone.utc
