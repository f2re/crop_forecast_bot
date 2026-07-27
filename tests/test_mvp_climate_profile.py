from __future__ import annotations

from datetime import date

import pytest

from config.settings import get_settings
from src.api.open_meteo_climate import (
    OpenMeteoClimateError,
    OpenMeteoClimateProvider,
)


@pytest.mark.asyncio
async def test_production_mvp_skips_multi_decadal_climate_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CLIMATE_REFERENCE_ENABLED", "false")
    get_settings.cache_clear()
    try:
        provider = OpenMeteoClimateProvider()
        with pytest.raises(OpenMeteoClimateError, match="disabled"):
            await provider.fetch_reference(
                55.75,
                37.62,
                timezone="Europe/Moscow",
                season_start=date(2026, 4, 15),
            )
    finally:
        get_settings.cache_clear()


def test_mvp_resource_defaults_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BLOCKING_IO_WORKERS", raising=False)
    monkeypatch.delenv("CLIMATE_REFERENCE_ENABLED", raising=False)
    monkeypatch.delenv("RISK_CHECK_ON_STARTUP", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.blocking_io_workers == 2
        assert settings.climate_reference_enabled is False
        assert settings.risk_check_on_startup is True
        assert settings.risk_check_startup_delay_seconds == 120
    finally:
        get_settings.cache_clear()
