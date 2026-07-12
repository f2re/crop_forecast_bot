from types import SimpleNamespace

import pytest

import src.bot.scheduler as scheduler_module
from src.agro.indices import FROST_STATUS_INSUFFICIENT
from src.bot.scheduler import check_frost_alerts
from src.database.crud import NotificationTarget
from src.infrastructure.coordination import MemoryCoordination


@pytest.mark.asyncio
async def test_frost_data_unavailable_warning_is_sent_once_per_field_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = NotificationTarget(
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
        phenological_phase="Кущение",
        daily_digest_enabled=False,
        frost_alerts_enabled=True,
    )

    async def fake_targets(
        session_factory,
        *,
        daily_digest_only=False,
        frost_alerts_only=False,
    ):
        assert frost_alerts_only is True
        return [target]

    async def fake_weather(latitude: float, longitude: float):
        return SimpleNamespace(
            daily=object(),
            meta=SimpleNamespace(
                utc_offset_seconds=3 * 3600,
                elevation_m=120.0,
            ),
        )

    risk = {
        "status": FROST_STATUS_INSUFFICIENT,
        "status_note": "в прогнозе отсутствует Tmin воздуха",
        "alerts": [],
    }

    class FakeBot:
        def __init__(self) -> None:
            self.messages: list[tuple[int, str]] = []

        async def send_message(self, chat_id: int, text: str) -> object:
            self.messages.append((chat_id, text))
            return object()

    bot = FakeBot()
    coordination = MemoryCoordination(namespace="frost-unavailable-test")
    monkeypatch.setattr(scheduler_module, "_targets", fake_targets)
    monkeypatch.setattr(scheduler_module, "fetch_agro_data", fake_weather)
    monkeypatch.setattr(
        scheduler_module,
        "calc_frost_risk",
        lambda daily, **kwargs: risk,
    )

    await check_frost_alerts(bot, object(), coordination)
    await check_frost_alerts(bot, object(), coordination)

    assert len(bot.messages) == 1
    assert bot.messages[0][0] == 1001
    assert "Температурный риск не оценён" in bot.messages[0][1]
    assert "Северное" in bot.messages[0][1]
