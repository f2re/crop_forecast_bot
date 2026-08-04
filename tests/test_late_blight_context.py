from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.late_blight_monitoring import (
    enable_open_field_late_blight_monitor,
    set_open_field_late_blight_inoculum_context,
)
from src.bot.handlers.markers import (
    _late_blight_context_keyboard,
    _with_monitor_status,
    format_late_blight_context,
)
from src.database.biological_monitoring import disable_late_blight_monitor
from src.database.crud import save_coordinates, update_user_crop
from src.database.models import Base
from src.database.phenology import set_growth_context
from src.domain.late_blight import LateBlightPeriod
from src.domain.late_blight_delivery import (
    LateBlightDeliveryState,
    LateBlightEpisodeState,
    plan_late_blight_delivery,
)


@pytest.mark.asyncio
async def test_user_context_is_persisted_without_rewriting_delivered_state(
    tmp_path,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'late-blight-context.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 9101, 55.75, 37.62)
            await update_user_crop(session, 9101, "potato")
            await set_growth_context(
                session,
                9101,
                production_system="open_field",
            )
            enabled = await enable_open_field_late_blight_monitor(session, 9101)
            assert enabled.inoculum_context == "unknown"
            assert enabled.delivery_state.inoculum_context == "unknown"

            saved = await set_open_field_late_blight_inoculum_context(
                session,
                9101,
                "regional_alert_confirmed",
            )

            assert saved.inoculum_context == "regional_alert_confirmed"
            # The old semantic state is retained so the manual view or scheduler
            # can detect and deliver a context-confirmed transition exactly once.
            assert saved.delivery_state.inoculum_context == "unknown"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_context_requires_enabled_open_field_potato_monitor(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'late-blight-context-scope.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 9102, 55.75, 37.62)
            await update_user_crop(session, 9102, "potato")
            await set_growth_context(
                session,
                9102,
                production_system="open_field",
            )
            await enable_open_field_late_blight_monitor(session, 9102)
            await disable_late_blight_monitor(session, 9102)

            with pytest.raises(ValueError, match="Сначала включите"):
                await set_open_field_late_blight_inoculum_context(
                    session,
                    9102,
                    "nearby_outbreak_confirmed",
                )
    finally:
        await engine.dispose()


def test_context_change_is_a_high_priority_semantic_transition() -> None:
    previous_period = LateBlightEpisodeState(
        date(2026, 8, 5),
        date(2026, 8, 7),
    )
    current_period = LateBlightPeriod(
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 7),
        day_count=3,
        data_kind="forecast",
    )
    previous = LateBlightDeliveryState(
        active_periods=(previous_period,),
        withdrawn_periods=(),
        inoculum_context="unknown",
    )
    decision = plan_late_blight_delivery(
        (current_period,),
        previous_state=previous,
        inoculum_context="regional_alert_confirmed",
        mode="high_only",
        local_datetime=datetime(2026, 8, 5, 8, tzinfo=ZoneInfo("Europe/Moscow")),
        quiet_hours_start=22,
        quiet_hours_end=7,
    )

    assert decision.change is not None
    assert decision.change.kind == "context_confirmed"
    assert decision.priority_bypass is True
    assert decision.dedup_token is not None


def test_context_message_and_keyboard_are_cautious_and_complete() -> None:
    text = format_late_blight_context("field_symptoms_observed")
    keyboard = _late_blight_context_keyboard("field_symptoms_observed")
    callbacks = {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data is not None
    }

    assert "пользователь отметил подозрительные симптомы" in text
    assert "диагноз ещё не подтверждён" in text
    assert "не доказывает заражение" in text
    assert "late_blight:context:set:unknown" in callbacks
    assert "late_blight:context:set:regional_alert_confirmed" in callbacks
    assert "late_blight:context:set:nearby_outbreak_confirmed" in callbacks
    assert "late_blight:context:set:field_source_suspected" in callbacks
    assert "late_blight:context:set:field_symptoms_observed" in callbacks
    assert any(
        button.text.startswith("✅ ")
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data == "late_blight:context:set:field_symptoms_observed"
    )


def test_manual_report_discloses_that_context_was_user_provided() -> None:
    text = _with_monitor_status(
        "Отчёт",
        enabled=True,
        inoculum_context="nearby_outbreak_confirmed",
    )

    assert "Фоновые предупреждения: <b>включены</b>" in text
    assert "пользователь указал подтверждённый очаг рядом" in text
    assert len(text) < 4096
