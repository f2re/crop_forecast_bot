from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

import src.bot.scheduler as scheduler_module
from src.bot.scheduler import check_weather_risk_alerts
from src.database.crud import NotificationTarget
from src.database.risk_history import StoredRiskRun
from src.domain.risk import EnsembleForecastData, EnsembleForecastMeta
from src.infrastructure.coordination import MemoryCoordination


def _target() -> NotificationTarget:
    return NotificationTarget(
        telegram_id=1001,
        field_id=42,
        field_name="Северное",
        latitude=55.75,
        longitude=37.62,
        timezone="Europe/Moscow",
        elevation_m=120.0,
        elevation_source="Open-Meteo Forecast API",
        selected_crop="wheat",
        season_start_date=None,
        phenological_phase="Колошение",
        daily_digest_enabled=False,
        frost_alerts_enabled=True,
    )


def _ensemble() -> EnsembleForecastData:
    rows = [
        {
            "local_date": date(2026, 7, 29),
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
            latitude=55.75,
            longitude=37.62,
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


class FakeProvider:
    async def fetch(self, latitude: float, longitude: float) -> EnsembleForecastData:
        assert latitude == 55.75
        assert longitude == 37.62
        return _ensemble()


class RecordingBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        self.messages.append((chat_id, text))
        return object()


@pytest.mark.asyncio
async def test_weather_risk_scheduler_persists_before_sending_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_targets(
        session_factory,
        *,
        daily_digest_only: bool = False,
        frost_alerts_only: bool = False,
    ) -> list[NotificationTarget]:
        assert daily_digest_only is False
        assert frost_alerts_only is True
        return [_target()]

    stored = False
    delivery_states: list[str] = []

    async def fake_record(session_factory, *, field_id, meta, outlook):
        nonlocal stored
        assert field_id == 42
        assert outlook.available is True
        stored = True
        return StoredRiskRun(
            run_id=1,
            signal_ids={("heavy_rain", date(2026, 7, 29)): 99},
            created=True,
        )

    async def fake_delivery(
        session_factory,
        *,
        signal_id,
        state,
        notified_at=None,
    ) -> bool:
        assert stored is True
        assert signal_id == 99
        delivery_states.append(state)
        return True

    async def fake_prune(session_factory) -> int:
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
            7,
            17,
            10,
            tzinfo=timezone.utc,
        ),
    )

    bot = RecordingBot()
    coordination = MemoryCoordination(namespace="test-ensemble-scheduler")
    try:
        await check_weather_risk_alerts(
            bot,
            object(),
            coordination,
            provider=FakeProvider(),
        )
        await check_weather_risk_alerts(
            bot,
            object(),
            coordination,
            provider=FakeProvider(),
        )
    finally:
        await coordination.close()

    assert len(bot.messages) == 1
    chat_id, text = bot.messages[0]
    assert chat_id == 1001
    assert "Сильные осадки" in text
    assert "22 из 31" in text
    assert "сырая доля модельных сценариев" in text
    assert delivery_states == ["sending", "sent", "sending", "deduplicated"]
