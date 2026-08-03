from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

import src.bot.scheduler as scheduler_module
from src.bot.scheduler import check_weather_risk_alerts
from src.database.notification_targets import EnabledNotificationTarget
from src.database.risk_history import StoredRiskRun
from src.domain.risk import EnsembleForecastData, EnsembleForecastMeta
from src.infrastructure.coordination import MemoryCoordination


class FakeProvider:
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


class RecordingBot:
    async def send_message(self, chat_id: int, text: str) -> object:
        raise AssertionError("deferred digest must not call Telegram")


@pytest.mark.asyncio
async def test_daily_quota_deferral_does_not_advance_postgresql_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = EnabledNotificationTarget(
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
    delivery_states: list[str] = []
    stored_baselines: list[object] = []

    async def fake_targets(session_factory, **kwargs):
        return [target]

    async def fake_record(session_factory, **kwargs):
        return StoredRiskRun(
            run_id=1,
            signal_ids={("heat", date(2026, 8, 5)): 99},
            created=True,
        )

    async def fake_load(session_factory, **kwargs):
        return ()

    async def fake_store(session_factory, **kwargs):
        stored_baselines.append(kwargs["episodes"])

    async def fake_delivery(session_factory, *, state, **kwargs):
        delivery_states.append(state)
        return True

    async def fake_send_transition(*args, **kwargs):
        assert kwargs["daily_quota_key"] is not None
        assert "transition:" in kwargs["transition_key"]
        return "deferred_daily"

    async def fake_prune(session_factory):
        return 0

    monkeypatch.setattr(scheduler_module, "_targets", fake_targets)
    monkeypatch.setattr(scheduler_module, "_record_risk_run", fake_record)
    monkeypatch.setattr(scheduler_module, "_load_delivery_state", fake_load)
    monkeypatch.setattr(scheduler_module, "_store_delivery_state", fake_store)
    monkeypatch.setattr(scheduler_module, "_set_risk_delivery", fake_delivery)
    monkeypatch.setattr(
        scheduler_module,
        "send_risk_transition_once",
        fake_send_transition,
    )
    monkeypatch.setattr(scheduler_module, "_prune_risk_history", fake_prune)
    monkeypatch.setattr(
        scheduler_module,
        "_local_datetime",
        lambda timezone_name, now_utc=None: datetime(
            2026,
            8,
            3,
            16,
            tzinfo=timezone.utc,
        ),
    )

    coordination = MemoryCoordination(namespace="scheduler-digest-deferral")
    try:
        await check_weather_risk_alerts(
            RecordingBot(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            coordination,
            provider=FakeProvider(),
        )
    finally:
        await coordination.close()

    assert delivery_states == ["sending", "deferred"]
    assert stored_baselines == []
