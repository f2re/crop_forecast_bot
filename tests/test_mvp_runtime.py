from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.fsm.storage.memory import MemoryStorage

import src.bot.main as main_module
from src.bot.main import _run_startup_risk_check, build_dispatcher
from src.infrastructure.coordination import MemoryCoordination


@pytest.mark.asyncio
async def test_mvp_dispatcher_loads_farmer_flow_without_rag_by_default() -> None:
    storage = MemoryStorage()
    coordination = MemoryCoordination(namespace="mvp-router-test")
    dispatcher = build_dispatcher(
        storage=storage,
        session_factory=lambda: None,
        coordination=coordination,
    )
    try:
        router_names = {router.name for router in dispatcher.sub_routers}
        assert {
            "settings",
            "profile",
            "crops",
            "season-calendar",
            "phenology",
            "soil-temperature",
            "pests",
            "marker-catalog",
            "report-help",
            "report",
            "risks",
            "risk-history",
            "core",
        }.issubset(router_names)
        assert "rag" not in router_names
    finally:
        await storage.close()
        await coordination.close()


@pytest.mark.asyncio
async def test_optional_rag_router_is_loaded_only_when_enabled() -> None:
    storage = MemoryStorage()
    coordination = MemoryCoordination(namespace="rag-router-test")
    dispatcher = build_dispatcher(
        storage=storage,
        session_factory=lambda: None,
        coordination=coordination,
        rag_enabled=True,
    )
    try:
        assert "rag" in {router.name for router in dispatcher.sub_routers}
    finally:
        await storage.close()
        await coordination.close()


@pytest.mark.asyncio
async def test_startup_risk_check_runs_once_after_configured_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[int] = []
    calls: list[tuple[object, object, object]] = []

    async def fake_sleep(delay: int) -> None:
        sleeps.append(delay)

    async def fake_check(bot, session_factory, coordination) -> None:
        calls.append((bot, session_factory, coordination))

    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main_module, "check_weather_risk_alerts", fake_check)

    bot = SimpleNamespace()
    session_factory = object()
    coordination = SimpleNamespace()
    await _run_startup_risk_check(
        bot,
        session_factory,  # type: ignore[arg-type]
        coordination,  # type: ignore[arg-type]
        120,
    )

    assert sleeps == [120]
    assert calls == [(bot, session_factory, coordination)]


@pytest.mark.asyncio
async def test_startup_provider_failure_does_not_stop_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_sleep(delay: int) -> None:
        assert delay == 60

    async def failing_check(bot, session_factory, coordination) -> None:
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main_module, "check_weather_risk_alerts", failing_check)

    await _run_startup_risk_check(
        SimpleNamespace(),
        object(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        60,
    )
