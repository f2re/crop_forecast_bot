from datetime import date, datetime, timezone

import pandas as pd
import pytest

from src.api.open_meteo_climate import CLIMATE_MODEL, CLIMATE_SOURCE
from src.domain.climate import ClimateReferenceData, ClimateReferenceMeta
from src.ops.climate_smoke import validate_climate_data


def _frame(start: str, end: str, *, temperature: float, precipitation: float, et0: float):
    dates = pd.date_range(start, end, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "date": dates,
            "local_date": list(dates.date),
            "t_max": [temperature + 5.0] * len(dates),
            "t_min": [temperature - 5.0] * len(dates),
            "t_mean": [temperature] * len(dates),
            "precip_sum": [precipitation] * len(dates),
            "et0_sum": [et0] * len(dates),
            "wind_max": [7.0] * len(dates),
            "data_kind": ["reanalysis"] * len(dates),
            "data_source": [CLIMATE_SOURCE] * len(dates),
        }
    )


def _data() -> ClimateReferenceData:
    reference = _frame(
        "1991-01-01",
        "2020-12-31",
        temperature=14.0,
        precipitation=1.0,
        et0=2.0,
    )
    current = _frame(
        "2026-04-01",
        "2026-04-10",
        temperature=20.0,
        precipitation=2.0,
        et0=3.0,
    )
    return ClimateReferenceData(
        meta=ClimateReferenceMeta(
            latitude=55.75,
            longitude=37.62,
            elevation_m=170.0,
            timezone="UTC",
            source=CLIMATE_SOURCE,
            model=CLIMATE_MODEL,
            reference_start=date(1991, 1, 1),
            reference_end=date(2020, 12, 31),
            comparison_start=date(2026, 4, 1),
            comparison_end=date(2026, 4, 10),
            retrieved_at=datetime(2026, 4, 11, tzinfo=timezone.utc),
            reference_cache_ttl_seconds=30 * 24 * 60 * 60,
            current_cache_ttl_seconds=6 * 60 * 60,
            spatial_resolution_km=11.0,
        ),
        reference_daily=reference,
        current_daily=current,
    )


def test_live_climate_contract_validates_homogeneous_series() -> None:
    result = validate_climate_data(
        _data(),
        season_start=date(2026, 4, 1),
        crop="sunflower",
    )

    assert result.model == "era5_land"
    assert result.reference_start == "1991-01-01"
    assert result.reference_end == "2020-12-31"
    assert result.comparison_start == "2026-04-01"
    assert result.comparison_end == "2026-04-10"
    assert result.window_days == 10
    assert result.minimum_reference_years == 30
    assert {
        "mean_temperature_c",
        "precip_sum_mm",
        "et0_sum_mm",
        "gdd_c_day",
    }.issubset(result.available_metrics)


def test_live_climate_contract_rejects_mixed_forecast_rows() -> None:
    data = _data()
    data.current_daily.loc[data.current_daily.index[-1], "data_kind"] = "forecast"

    with pytest.raises(ValueError, match="not homogeneous reanalysis"):
        validate_climate_data(
            data,
            season_start=date(2026, 4, 1),
            crop="sunflower",
        )


def test_live_climate_contract_rejects_incomplete_accumulation() -> None:
    data = _data()
    data.current_daily.loc[data.current_daily.index[3], "precip_sum"] = float("nan")

    with pytest.raises(ValueError, match="missing required metrics: precip_sum_mm"):
        validate_climate_data(
            data,
            season_start=date(2026, 4, 1),
            crop="sunflower",
        )
