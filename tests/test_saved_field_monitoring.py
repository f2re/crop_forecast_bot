from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

import src.bot.scheduler as scheduler_module
from src.bot.scheduler import check_weather_risk_alerts
from src.database.notification_targets import EnabledNotificationTarget
from src.database.risk_delivery_state import StoredRiskDeliveryState
from src.database.risk_history import StoredRiskRun
from src.domain.risk import EnsembleForecastData, EnsembleForecastMeta
from src.domain.risk_delivery import RiskEpisodeState
from src.infrastructure.coordination import MemoryCoordination

_EVENT_DATE = date(2026, 7, 29)


def _target(
    field_id: int,
    field_name: str,
    latitude: float,
    longitude: float,
) -> EnabledNotificationTarget:
    return EnabledNotificationTarget(
        telegram_id=1001,
        field_id=field_id,
        field_name=field_name,
        latitude=latitude,
        longitude=longitude,
        timezone="Europe/Moscow",
        elevation_m=120.0,
        elevation_source="Open-Meteo Forecast API",
        selected_crop="wheat",
        season_start_date=None,
        phenological_phase="Колошение",
        daily_digest_enabled=False,
        frost_alerts_enabled=True,
        risk_delivery_mode="immediate",
        quiet_hours_start=None,
        quiet_hours_end=None,
    )


def _ensemble(latitude: float, longitude: float) -> EnsembleForecastData:
    rows = [
        {
            "local_date": _EVENT_DATE,
            "member_id": f"m{member:02d}",
            "t_min_c": 8.0,
            "t_max_c": 25.0,
            "precip_mm": 40.0 if member < 22 else 2.0,
            "wind_gust_ms": 6.0,
            "cape_j_kg": 100.0,
        }
        for member in range(31)
    ]
    return EnsembleForecastData(
        meta=EnsembleForecastMeta(
            latitude=latitude,
            longitude=longitude,
            elevation_m=120.0,
            timezone="Europe/Moscow",
            source="test",
            model="gfs_seamless",
            retrieved_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
            member_count=31,
            forecast_days=1,
        ),
        daily_members=pd.DataFrame(rows),
    )


class RecordingProvider:
    def __init__(self) -> None:
        self.coordinates: list[tuple[float, float]] = []

    async def fetch(self, latitude: float, longitude: float) -> EnsembleForecastData:
        self.coordinates.append((latitude, longitude))
        return _ensemble(latitude, longitude)


class RecordingBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        self.messages.append((chat_id, text))
        return object()


@pytest.mark.asyncio
async def test_scheduler_calculates_each_saved_enabled_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets = [
        _target(42, "Северное", 55.75, 37.62),
        _target(43, "Южное", 45.04, 38.98),
    ]
    stored_fields: list[int] = []
    delivery_states: list[tuple[int, str]] = []
    semantic_states: dict[int, tuple[RiskEpisodeState, ...]] = {}

    async def fake_targets(
        session_factory,
        *,
        daily_digest_only: bool = False,
        frost_alerts_only: bool = False,
    ) -> list[EnabledNotificationTarget]:
        assert daily_digest_only is False
        assert frost_alerts_only is True
        return targets

    async def fake_record(session_factory, *, field_id, meta, outlook):
        assert outlook.available is True
        stored_fields.append(field_id)
        return StoredRiskRun(
            run_id=field_id,
            signal_ids={("heavy_rain", _EVENT_DATE): field_id * 10},
            created=True,
        )

    async def fake_load(
        session_factory,
        *,
        field_id: int,
        model: str,
        delivery_mode: str,
    ) -> StoredRiskDeliveryState | None:
        assert model == "gfs_seamless"
        assert delivery_mode == "immediate"
        return None

    async def fake_store(
        session_factory,
        *,
        field_id: int,
        model: str,
        delivery_mode: str,
        episodes: tuple[RiskEpisodeState, ...],
        observed_at: datetime,
        notified_at: datetime | None = None,
    ) -> None:
        assert model == "gfs_seamless"
        assert delivery_mode == "immediate"
        assert observed_at.tzinfo is not None
        semantic_states[field_id] = episodes

    async def fake_delivery(
        session_factory,
        *,
        signal_id,
        state,
        notified_at=None,
    ) -> bool:
        delivery_states.append((signal_id, state))
        return True

    async def fake_prune(session_factory) -> int:
        return 0

    monkeypatch.setattr(scheduler_module, "_targets", fake_targets)
    monkeypatch.setattr(scheduler_module, "_record_risk_run", fake_record)
    monkeypatch.setattr(scheduler_module, "_load_delivery_state", fake_load)
    monkeypatch.setattr(scheduler_module, "_store_delivery_state", fake_store)
    monkeypatch.setattr(scheduler_module, "_set_risk_delivery", fake_delivery)
    monkeypatch.setattr(scheduler_module, "_prune_risk_history", fake_prune)
    monkeypatch.setattr(
        scheduler_module,
        "_local_datetime",
        lambda timezone_name, now_utc=None: datetime(
            2026,
            7,
            17,
            10,
            tzinfo=timezone.utc,
        ),
    )

    provider = RecordingProvider()
    bot = RecordingBot()
    coordination = MemoryCoordination(namespace="saved-field-monitoring")
    try:
        await check_weather_risk_alerts(
            bot,
            object(),
            coordination,
            provider=provider,
        )
    finally:
        await coordination.close()

    assert provider.coordinates == [(55.75, 37.62), (45.04, 38.98)]
    assert stored_fields == [42, 43]
    assert len(bot.messages) == 2
    assert "Северное" in bot.messages[0][1]
    assert "Южное" in bot.messages[1][1]
    assert semantic_states[42][0].risk_type == "heavy_rain"
    assert semantic_states[43][0].risk_type == "heavy_rain"
    assert delivery_states == [
        (420, "sending"),
        (420, "sent"),
        (430, "sending"),
        (430, "sent"),
    ]
