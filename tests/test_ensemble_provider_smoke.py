from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from src.domain.risk import EnsembleForecastData, EnsembleForecastMeta
from src.ops.ensemble_smoke import validate_ensemble_data


def _data(*, member_count: int = 31, forecast_days: int = 10) -> EnsembleForecastData:
    start = date(2026, 7, 17)
    rows: list[dict] = []
    for day_offset in range(forecast_days):
        local_day = start + timedelta(days=day_offset)
        for member in range(member_count):
            rows.append(
                {
                    "local_date": local_day,
                    "member_id": f"member{member:02d}",
                    "t_min_c": 8.0 + member / 100,
                    "t_max_c": 24.0 + member / 100,
                    "precip_mm": 2.0,
                    "wind_gust_ms": 7.0,
                    "cape_j_kg": 200.0,
                }
            )
    return EnsembleForecastData(
        meta=EnsembleForecastMeta(
            latitude=55.75,
            longitude=37.62,
            elevation_m=150.0,
            timezone="UTC",
            source="test ensemble",
            model="gfs_seamless",
            retrieved_at=datetime(2026, 7, 17, 1, tzinfo=timezone.utc),
            member_count=member_count,
            forecast_days=forecast_days,
            cache_ttl_seconds=3600,
        ),
        daily_members=pd.DataFrame(rows),
    )


def test_validate_ensemble_data_accepts_complete_member_horizon() -> None:
    result = validate_ensemble_data(
        _data(),
        as_of=datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
    )

    assert result.member_count == 31
    assert result.forecast_days == 10
    assert result.rows == 310
    assert result.complete_days == 10
    assert result.incomplete_days == 0
    assert result.local_date_start == "2026-07-17"
    assert result.local_date_end == "2026-07-26"


def test_validate_ensemble_data_rejects_too_few_members() -> None:
    with pytest.raises(ValueError, match="expected at least 20"):
        validate_ensemble_data(
            _data(member_count=19),
            as_of=datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
        )


def test_validate_ensemble_data_rejects_incomplete_variable_day() -> None:
    data = _data()
    mask = data.daily_members["local_date"] == date(2026, 7, 20)
    affected = data.daily_members.index[mask][:12]
    data.daily_members.loc[affected, "cape_j_kg"] = float("nan")

    with pytest.raises(ValueError, match="only 19 valid members for cape_j_kg"):
        validate_ensemble_data(
            data,
            as_of=datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
        )


def test_validate_ensemble_data_rejects_negative_precipitation() -> None:
    data = _data()
    data.daily_members.loc[0, "precip_mm"] = -1.0

    with pytest.raises(ValueError, match="negative precip_mm"):
        validate_ensemble_data(
            data,
            as_of=datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
        )


def test_validate_ensemble_data_rejects_tmin_above_tmax() -> None:
    data = _data()
    data.daily_members.loc[0, "t_min_c"] = 30.0

    with pytest.raises(ValueError, match="Tmin exceeds Tmax"):
        validate_ensemble_data(
            data,
            as_of=datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
        )
