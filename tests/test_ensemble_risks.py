from datetime import date, datetime, timezone

import pandas as pd

from src.agro.ensemble_risks import calc_ensemble_risks
from src.domain.risk import EnsembleForecastData, EnsembleForecastMeta


def _forecast(rows: list[dict], *, members: int = 31) -> EnsembleForecastData:
    return EnsembleForecastData(
        meta=EnsembleForecastMeta(
            latitude=55.75,
            longitude=37.62,
            elevation_m=150.0,
            timezone="Europe/Moscow",
            source="test",
            model="gfs_seamless",
            retrieved_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
            member_count=members,
            forecast_days=len({row["local_date"] for row in rows}),
        ),
        daily_members=pd.DataFrame(rows),
    )


def test_raw_member_fraction_is_exposed_without_probability_claim() -> None:
    rows = []
    for member in range(31):
        rows.append(
            {
                "local_date": date(2026, 7, 29),
                "member_id": f"m{member:02d}",
                "t_min_c": 6.0,
                "t_max_c": 30.0,
                "precip_mm": 40.0 if member < 22 else 2.0,
                "wind_gust_ms": 8.0,
                "cape_j_kg": 100.0,
            }
        )

    result = calc_ensemble_risks(
        _forecast(rows),
        as_of_date=date(2026, 7, 17),
    )

    event = next(event for event in result.events if event.risk_type == "heavy_rain")
    assert event.members_exceeding == 22
    assert event.valid_members == 31
    assert event.member_fraction == 0.7097
    assert event.lead_days == 12
    assert "дальний срок" in event.reliability_note
    assert "не откалиброванная вероятность" in result.method_reference


def test_convection_is_not_called_hail_probability() -> None:
    rows = []
    for member in range(31):
        rows.append(
            {
                "local_date": date(2026, 7, 20),
                "member_id": f"m{member:02d}",
                "t_min_c": 10.0,
                "t_max_c": 25.0,
                "precip_mm": 1.0,
                "wind_gust_ms": 5.0,
                "cape_j_kg": 1500.0 if member < 20 else 100.0,
            }
        )

    result = calc_ensemble_risks(
        _forecast(rows),
        as_of_date=date(2026, 7, 17),
    )

    event = next(event for event in result.events if event.risk_type == "convection")
    assert event.level == "high"
    assert "не прогноз грозы или града" in event.caveat


def test_insufficient_members_fail_closed() -> None:
    rows = [
        {
            "local_date": date(2026, 7, 18),
            "member_id": f"m{member:02d}",
            "t_min_c": -5.0,
            "t_max_c": 40.0,
            "precip_mm": 100.0,
            "wind_gust_ms": 30.0,
            "cape_j_kg": 3000.0,
        }
        for member in range(10)
    ]

    result = calc_ensemble_risks(
        _forecast(rows, members=10),
        as_of_date=date(2026, 7, 17),
    )

    assert result.available is False
    assert result.events == ()
    assert result.status == "недостаточно членов ансамбля"


def test_no_threshold_crossing_is_valid_no_risk() -> None:
    rows = [
        {
            "local_date": date(2026, 7, 18),
            "member_id": f"m{member:02d}",
            "t_min_c": 8.0,
            "t_max_c": 25.0,
            "precip_mm": 2.0,
            "wind_gust_ms": 6.0,
            "cape_j_kg": 100.0,
        }
        for member in range(31)
    ]

    result = calc_ensemble_risks(
        _forecast(rows),
        as_of_date=date(2026, 7, 17),
    )

    assert result.available is True
    assert result.events == ()
    assert "не выявлены" in result.status
