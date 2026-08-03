from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

import src.bot.pest_scheduler as scheduler_module
from src.agro.pest_phenology import calculate_pest_outlook
from src.application.pest_monitoring import PestMonitorRequest, PestMonitorResult
from src.bot.pest_scheduler import check_pest_monitoring
from src.database.pest_monitoring import PestMonitoringTarget
from src.domain.pests import get_pest_model
from src.infrastructure.coordination import MemoryCoordination


def _outlook():
    biofix = date(2026, 6, 1)
    today = date(2026, 6, 5)
    values = [
        (11.1, 51.1, "reanalysis"),
        (11.1, 51.1, "reanalysis"),
        (11.1, 51.1, "operational_past"),
        (11.1, 51.1, "operational_past"),
        (11.1, 51.1, "current_forecast"),
        (11.1, 51.1, "forecast"),
    ]
    frame = pd.DataFrame(
        [
            {
                "date": pd.Timestamp(biofix + timedelta(days=offset), tz="UTC"),
                "local_date": (biofix + timedelta(days=offset)).isoformat(),
                "t_min": t_min,
                "t_max": t_max,
                "data_kind": kind,
                "data_source": "test",
            }
            for offset, (t_min, t_max, kind) in enumerate(values)
        ]
    )
    return calculate_pest_outlook(
        frame,
        "colorado_potato_beetle",
        biofix_date=biofix,
        today=today,
    )


class _Bot:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        assert chat_id == 3001
        self.messages.append(text)
        return object()


@pytest.mark.asyncio
async def test_scheduler_persists_state_key_but_deduplicates_transition_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outlook = replace(
        _outlook(),
        projected_crossing_date=date(2026, 6, 8),
    )
    model = get_pest_model("colorado_potato_beetle")
    stage_key = (
        f"{model.model_version}:2026-06-01:current:eggs"
    )
    previous_advance = (
        f"{model.model_version}:2026-06-01:"
        "approaching:larva_1:expected:2026-06-06"
    )
    target = PestMonitoringTarget(
        telegram_id=3001,
        field_id=42,
        field_name="Северное",
        latitude=45.75,
        longitude=33.875,
        timezone="UTC",
        season_id=7,
        crop_key="potato",
        monitor_id=11,
        pest_key="colorado_potato_beetle",
        biofix_date=date(2026, 6, 1),
        biofix_type=model.biofix_type,
        model_version=model.model_version,
        last_checked_local_date=None,
        last_notified_stage=stage_key,
        last_notified_advance=previous_advance,
    )
    saved: list[dict[str, object]] = []

    async def fake_targets(session_factory):
        return [target]

    async def fake_evaluate(*args, **kwargs):
        request = PestMonitorRequest(
            monitor_id=11,
            pest_key=target.pest_key,
            biofix_date=target.biofix_date,
        )
        return (
            PestMonitorResult(
                request=request,
                outlook=outlook,
                timezone="UTC",
                source="test",
                retrieved_at=datetime(2026, 6, 5, 6, tzinfo=timezone.utc),
            ),
        )

    async def fake_mark(session_factory, monitor_id, **kwargs):
        assert monitor_id == 11
        saved.append(kwargs)
        return True

    monkeypatch.setattr(scheduler_module, "_targets", fake_targets)
    monkeypatch.setattr(
        scheduler_module,
        "evaluate_pest_monitors",
        fake_evaluate,
    )
    monkeypatch.setattr(scheduler_module, "_mark_checked", fake_mark)

    bot = _Bot()
    coordination = MemoryCoordination(namespace="pest-semantic-scheduler")
    try:
        await check_pest_monitoring(
            bot,  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            coordination,
            due_only=False,
            now_utc=datetime(2026, 6, 5, 8, tzinfo=timezone.utc),
            job_lock_ttl_seconds=60,
            renew_interval_seconds=5,
        )
    finally:
        await coordination.close()

    assert len(bot.messages) == 1
    assert "ожидается позже" in bot.messages[0]
    assert len(saved) == 1
    assert saved[0]["advance_event_key"] == (
        f"{model.model_version}:2026-06-01:"
        "approaching:larva_1:expected:2026-06-08"
    )
    assert saved[0]["notified_at"] is not None
