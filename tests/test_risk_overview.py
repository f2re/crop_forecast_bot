from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from src.application.risk_overview import generate_risk_overview
from src.bot.risk_overview import format_risk_overview
from src.domain.risk import EnsembleForecastData, EnsembleForecastMeta


class FakeRiskProvider:
    def __init__(self, data: EnsembleForecastData) -> None:
        self.data = data
        self.calls: list[tuple[float, float]] = []

    async def fetch(self, latitude: float, longitude: float) -> EnsembleForecastData:
        self.calls.append((latitude, longitude))
        return self.data


def _forecast(*, rain_members: int = 20) -> EnsembleForecastData:
    rows: list[dict] = []
    for day_offset in range(3):
        local_day = date(2026, 7, 19 + day_offset)
        for member in range(31):
            rows.append(
                {
                    "local_date": local_day,
                    "member_id": f"m{member:02d}",
                    "t_min_c": 8.0,
                    "t_max_c": 27.0,
                    "precip_mm": (
                        40.0 if day_offset == 1 and member < rain_members else 2.0
                    ),
                    "wind_gust_ms": 7.0,
                    "cape_j_kg": 150.0,
                }
            )
    return EnsembleForecastData(
        meta=EnsembleForecastMeta(
            latitude=55.75,
            longitude=37.62,
            elevation_m=150.0,
            timezone="Europe/Moscow",
            source="test ensemble provider",
            model="gfs_seamless",
            retrieved_at=datetime(2026, 7, 18, 9, 0, tzinfo=timezone.utc),
            member_count=31,
            forecast_days=3,
            cache_ttl_seconds=10_800,
        ),
        daily_members=pd.DataFrame(rows),
    )


@pytest.mark.asyncio
async def test_generate_and_format_manual_risk_overview() -> None:
    provider = FakeRiskProvider(_forecast(rain_members=20))

    overview = await generate_risk_overview(
        55.75,
        37.62,
        provider=provider,
        as_of_date=date(2026, 7, 18),
    )
    text = format_risk_overview(
        overview,
        field_name="Северное",
        crop="wheat",
        phase="Колошение",
    )

    assert provider.calls == [(55.75, 37.62)]
    assert "Погодные риски на 16 суток" in text
    assert "20/31 сценариев" in text
    assert "сильные осадки" in text
    assert "сырая доля модельных сценариев" in text
    assert "не является прогнозом грозы или града" in text
    assert "Что делать сейчас" in text
    assert len(text) <= 4096


@pytest.mark.asyncio
async def test_manual_overview_distinguishes_valid_no_signal() -> None:
    overview = await generate_risk_overview(
        55.75,
        37.62,
        provider=FakeRiskProvider(_forecast(rain_members=0)),
        as_of_date=date(2026, 7, 18),
    )
    text = format_risk_overview(
        overview,
        field_name="Поле 1",
        crop="sunflower",
    )

    assert overview.outlook.available is True
    assert overview.outlook.events == ()
    assert "сигналы выше операционных порогов уведомления не выявлены" in text
    assert "отсутствие сигнала не исключает локальное явление" in text


def test_manual_overview_fails_closed_for_unavailable_outlook() -> None:
    data = _forecast(rain_members=0)
    data.daily_members = data.daily_members.head(10)
    provider = FakeRiskProvider(data)

    async def run() -> str:
        overview = await generate_risk_overview(
            55.75,
            37.62,
            provider=provider,
            as_of_date=date(2026, 7, 18),
        )
        return format_risk_overview(
            overview,
            field_name="Поле 1",
            crop="wheat",
        )

    text = __import__("asyncio").run(run())
    assert "Анализ не выполнен" in text
    assert "Отсутствие полного ансамбля не означает отсутствие локального риска" in text
