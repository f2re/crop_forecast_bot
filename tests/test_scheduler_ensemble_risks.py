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


def _target(
    *,
    mode: str = "immediate",
    quiet_hours_start: int | None = None,
    quiet_hours_end: int | None = None,
) -> EnabledNotificationTarget:
    return EnabledNotificationTarget(
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
        risk_delivery_mode=mode,  # type: ignore[arg-type]
        quiet_hours_start=quiet_hours_start,
        quiet_hours_end=quiet_hours_end,
        crop_keys=("wheat", "potato"),
    )


def _ensemble(
    *,
    rain_members: int = 22,
    wind_members: int = 0,
    retrieved_hour: int = 0,
) -> EnsembleForecastData:
    rows = [
        {
            "local_date": date(2026, 7, 29),
            "member_id": f"m{member:02d}",
            "t_min_c": 8.0,
            "t_max_c": 25.0,
            "precip_mm": 40.0 if member < rain_members else 2.0,
            "wind_gust_ms": 17.0 if member < wind_members else 6.0,
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
            retrieved_at=datetime(
                2026,
                7,
                17,
                retrieved_hour,
                tzinfo=timezone.utc,
            ),
            member_count=31,
            forecast_days=1,
        ),
        daily_members=pd.DataFrame(rows),
    )


class FakeProvider:
    def __init__(self, data: EnsembleForecastData | None = None) -> None:
        self.data = data or _ensemble()

    async def fetch(self, latitude: float, longitude: float) -> EnsembleForecastData:
        assert latitude == 55.75
        assert longitude == 37.62
        return self.data


class RecordingBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        self.messages.append((chat_id, text))
        return object()


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    *,
    target: EnabledNotificationTarget,
    hour: int,
    signal_ids: dict[tuple[str, date], int],
) -> tuple[list[str], list[bool], list[tuple[RiskEpisodeState, ...]]]:
    stored_flags: list[bool] = []
    delivery_states: list[str] = []
    semantic_states: list[tuple[RiskEpisodeState, ...]] = []
    baseline: tuple[RiskEpisodeState, ...] = ()
    last_observed_at = datetime(2026, 7, 17, tzinfo=timezone.utc)
    last_notified_at: datetime | None = None

    async def fake_targets(
        session_factory,
        *,
        daily_digest_only: bool = False,
        frost_alerts_only: bool = False,
    ) -> list[EnabledNotificationTarget]:
        assert daily_digest_only is False
        assert frost_alerts_only is True
        return [target]

    async def fake_record(session_factory, *, field_id, meta, outlook):
        assert field_id == 42
        assert outlook.available is True
        stored_flags.append(True)
        return StoredRiskRun(
            run_id=len(stored_flags),
            signal_ids=signal_ids,  # type: ignore[arg-type]
            created=True,
        )

    async def fake_load(
        session_factory,
        *,
        field_id: int,
        model: str,
        delivery_mode: str,
    ) -> StoredRiskDeliveryState | None:
        assert field_id == 42
        assert model == "gfs_seamless"
        assert delivery_mode == target.risk_delivery_mode
        if not baseline and last_notified_at is None:
            return None
        return StoredRiskDeliveryState(
            field_id=42,
            model=model,
            delivery_mode=target.risk_delivery_mode,
            episodes=baseline,
            last_observed_at=last_observed_at,
            last_notified_at=last_notified_at,
        )

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
        nonlocal baseline, last_observed_at, last_notified_at
        assert field_id == 42
        assert model == "gfs_seamless"
        assert delivery_mode == target.risk_delivery_mode
        assert observed_at.tzinfo is not None
        baseline = episodes
        last_observed_at = observed_at
        if notified_at is not None:
            last_notified_at = notified_at
        semantic_states.append(episodes)

    async def fake_delivery(
        session_factory,
        *,
        signal_id,
        state,
        notified_at=None,
    ) -> bool:
        assert stored_flags
        assert signal_id in signal_ids.values()
        delivery_states.append(state)
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
            hour,
            tzinfo=timezone.utc,
        ),
    )
    return delivery_states, stored_flags, semantic_states


@pytest.mark.asyncio
async def test_weather_risk_scheduler_persists_before_sending_and_reuses_db_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery_states, _, semantic_states = _patch_common(
        monkeypatch,
        target=_target(),
        hour=10,
        signal_ids={("heavy_rain", date(2026, 7, 29)): 99},
    )

    bot = RecordingBot()
    coordination = MemoryCoordination(namespace="test-ensemble-scheduler")
    try:
        await check_weather_risk_alerts(
            bot,
            object(),
            coordination,
            provider=FakeProvider(_ensemble(retrieved_hour=0)),
        )
        await check_weather_risk_alerts(
            bot,
            object(),
            coordination,
            provider=FakeProvider(_ensemble(rain_members=24, retrieved_hour=6)),
        )
    finally:
        await coordination.close()

    assert len(bot.messages) == 1
    chat_id, text = bot.messages[0]
    assert chat_id == 1001
    assert "Погода: Северное" in text
    assert "Что изменилось" in text
    assert "Сильные осадки" in text
    assert "🟡" in text
    assert "Пшеница, Картофель" in text
    assert "22 из 31" not in text
    assert "вероятность повреждения растений" not in text
    assert "Надёжность" not in text
    assert len(text) < 700
    assert delivery_states == ["sending", "sent"]
    assert len(semantic_states) == 2
    assert semantic_states[0] == semantic_states[1]


@pytest.mark.asyncio
async def test_weather_risk_scheduler_defers_non_high_change_in_quiet_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery_states, stored_flags, semantic_states = _patch_common(
        monkeypatch,
        target=_target(quiet_hours_start=22, quiet_hours_end=7),
        hour=23,
        signal_ids={("heavy_rain", date(2026, 7, 29)): 99},
    )

    bot = RecordingBot()
    coordination = MemoryCoordination(namespace="test-ensemble-quiet-hours")
    try:
        await check_weather_risk_alerts(
            bot,
            object(),
            coordination,
            provider=FakeProvider(_ensemble(rain_members=10)),
        )
    finally:
        await coordination.close()

    assert stored_flags == [True]
    assert bot.messages == []
    assert delivery_states == []
    assert semantic_states == []


@pytest.mark.asyncio
async def test_weather_risk_scheduler_sends_one_digest_for_multiple_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery_states, _, semantic_states = _patch_common(
        monkeypatch,
        target=_target(mode="digest"),
        hour=10,
        signal_ids={
            ("heavy_rain", date(2026, 7, 29)): 99,
            ("strong_wind", date(2026, 7, 29)): 100,
        },
    )

    bot = RecordingBot()
    coordination = MemoryCoordination(namespace="test-ensemble-digest")
    try:
        await check_weather_risk_alerts(
            bot,
            object(),
            coordination,
            provider=FakeProvider(_ensemble(rain_members=10, wind_members=10)),
        )
    finally:
        await coordination.close()

    assert len(bot.messages) == 1
    text = bot.messages[0][1]
    assert "Сильные осадки" in text
    assert "Сильные порывы ветра" in text
    assert "Действие:" in text
    assert "один дайджест" not in text
    assert "Режим уведомлений" not in text
    assert delivery_states == ["sending", "sending", "sent", "sent"]
    assert len(semantic_states) == 1


@pytest.mark.asyncio
async def test_weather_risk_scheduler_reports_clear_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery_states, _, semantic_states = _patch_common(
        monkeypatch,
        target=_target(),
        hour=10,
        signal_ids={("heavy_rain", date(2026, 7, 29)): 99},
    )

    bot = RecordingBot()
    coordination = MemoryCoordination(namespace="test-ensemble-clear")
    try:
        await check_weather_risk_alerts(
            bot,
            object(),
            coordination,
            provider=FakeProvider(_ensemble(rain_members=22, retrieved_hour=0)),
        )
        await check_weather_risk_alerts(
            bot,
            object(),
            coordination,
            provider=FakeProvider(_ensemble(rain_members=0, retrieved_hour=6)),
        )
        await check_weather_risk_alerts(
            bot,
            object(),
            coordination,
            provider=FakeProvider(_ensemble(rain_members=0, retrieved_hour=12)),
        )
    finally:
        await coordination.close()

    assert len(bot.messages) == 2
    assert "больше не подтверждается" in bot.messages[1][1]
    assert "больше не подтверждаются" in bot.messages[1][1]
    assert "🟢" in bot.messages[1][1]
    assert delivery_states == ["sending", "sent"]
    assert semantic_states[-1] == ()
