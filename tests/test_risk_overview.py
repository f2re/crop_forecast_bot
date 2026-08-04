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


def _forecast(
    *,
    rain_members: int = 20,
    convection_members: int = 0,
) -> EnsembleForecastData:
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
                    "cape_j_kg": (
                        1400.0
                        if day_offset == 2 and member < convection_members
                        else 150.0
                    ),
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
async def test_generate_and_format_manual_risk_overview_for_farmer() -> None:
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
        crop="tomato",
        crops=("tomato", "potato"),
        phase="Цветение",
    )

    assert provider.calls == [(55.75, 37.62)]
    assert "Погодные риски: Северное" in text
    assert "🔴" in text
    assert "Сильные осадки — действовать" in text
    assert "осадки 2–40 мм" in text
    assert "Действие:" in text
    assert "Томат, Картофель" in text
    assert "Данные: ансамбль GFS" in text
    assert "вариант" not in text
    assert "Как читать прогноз" not in text
    assert "Надёжность данных" not in text
    assert "Когда проверить снова" not in text
    assert len(text) < 900


@pytest.mark.asyncio
async def test_manual_overview_explains_convection_without_hail_claim() -> None:
    overview = await generate_risk_overview(
        55.75,
        37.62,
        provider=FakeRiskProvider(
            _forecast(rain_members=0, convection_members=20)
        ),
        as_of_date=date(2026, 7, 18),
    )
    text = format_risk_overview(
        overview,
        field_name="Поле 1",
        crop="sunflower",
    )

    assert "Неустойчивая атмосфера" in text
    assert "CAPE" in text
    assert "не прогноз грозы" in text
    assert "вероятность града" not in text


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
    assert "🟢" in text
    assert "Существенных погодных рисков не выявлено" in text
    assert "обычный контроль поля" in text


@pytest.mark.asyncio
async def test_manual_overview_fails_closed_for_unavailable_outlook() -> None:
    data = _forecast(rain_members=0)
    data.daily_members = data.daily_members.head(10)

    overview = await generate_risk_overview(
        55.75,
        37.62,
        provider=FakeRiskProvider(data),
        as_of_date=date(2026, 7, 18),
    )
    text = format_risk_overview(
        overview,
        field_name="Поле 1",
        crop="wheat",
    )

    assert "⚪" in text
    assert "Данные временно недоступны" in text
    assert "проверьте официальный прогноз" in text
