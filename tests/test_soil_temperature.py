from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from src.api.open_meteo_soil import (
    FORECAST_VARIABLE,
    HISTORY_VARIABLE,
    _forecast_params,
    _history_params,
    _parse_hourly_payload,
)
from src.application.soil_temperature import generate_soil_temperature_report
from src.domain.soil_temperature import (
    SoilTemperatureCoverage,
    SoilTemperatureData,
    SoilTemperatureMeta,
)
from src.ops.soil_temperature_smoke import validate_soil_temperature_data


def _hourly_payload(
    start: datetime,
    hours: int,
    values: list[float | None],
    *,
    variable: str,
):
    assert len(values) == hours
    return {
        "latitude": 45.75,
        "longitude": 33.875,
        "elevation": 25.0,
        "timezone": "Europe/Simferopol",
        "hourly": {
            "time": [
                (start + timedelta(hours=offset)).strftime("%Y-%m-%dT%H:%M")
                for offset in range(hours)
            ],
            variable: values,
        },
    }


def test_open_meteo_endpoints_use_live_soil_variable_contract() -> None:
    assert FORECAST_VARIABLE == "soil_temperature_0_to_7cm"
    assert HISTORY_VARIABLE == "soil_temperature_0_to_7cm"
    assert _forecast_params(45.75, 33.875)["hourly"] == FORECAST_VARIABLE
    assert (
        _history_params(
            45.75,
            33.875,
            date(2026, 3, 1),
            date(2026, 3, 31),
            "Europe/Simferopol",
        )["hourly"]
        == HISTORY_VARIABLE
    )


def test_hourly_soil_temperature_is_aggregated_by_local_day() -> None:
    start = datetime(2026, 4, 1)
    values = [float(hour) for hour in range(24)]
    frame, timezone_name = _parse_hourly_payload(
        _hourly_payload(
            start,
            24,
            values,
            variable=HISTORY_VARIABLE,
        ),
        variable=HISTORY_VARIABLE,
        source="test",
        history=True,
    )

    assert timezone_name == "Europe/Simferopol"
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["local_date"] == date(2026, 4, 1)
    assert row["t_min"] == pytest.approx(0.0)
    assert row["t_max"] == pytest.approx(23.0)
    assert row["t_mean"] == pytest.approx(11.5)
    assert row["valid_hours"] == 24
    assert row["data_kind"] == "reanalysis"


def test_incomplete_soil_day_is_not_silently_accepted() -> None:
    start = datetime(2026, 4, 1)
    values: list[float | None] = [float(hour) for hour in range(24)]
    for index in range(7):
        values[index] = None
    frame, _ = _parse_hourly_payload(
        _hourly_payload(
            start,
            24,
            values,
            variable=FORECAST_VARIABLE,
        ),
        variable=FORECAST_VARIABLE,
        source="test",
        history=False,
    )

    assert frame.iloc[0]["valid_hours"] == 17
    assert pd.isna(frame.iloc[0]["t_min"])
    assert pd.isna(frame.iloc[0]["t_max"])
    assert pd.isna(frame.iloc[0]["t_mean"])


class _SoilProvider:
    async def fetch(self, latitude, longitude, *, season_start=None):
        assert (latitude, longitude) == (45.75, 33.875)
        assert season_start is None
        rows = []
        for offset in range(6):
            day = date(2026, 4, 1) + timedelta(days=offset)
            rows.append(
                {
                    "date": pd.Timestamp(day, tz="UTC"),
                    "local_date": day,
                    "t_min": 8.0 + offset,
                    "t_max": 12.0 + offset,
                    "t_mean": 10.0 + offset,
                    "valid_hours": 24,
                    "data_kind": (
                        "operational_past" if offset < 3 else "forecast"
                    ),
                    "data_source": "test soil model",
                }
            )
        return SoilTemperatureData(
            meta=SoilTemperatureMeta(
                latitude=latitude,
                longitude=longitude,
                elevation_m=25.0,
                timezone="Europe/Simferopol",
                source="test soil model",
                model="test",
                depth_label="модельный слой почвы 0–7 см",
                retrieved_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
                cache_ttl_seconds=3600,
                spatial_resolution_km=9.0,
            ),
            daily=pd.DataFrame(rows),
            forecast_days=3,
            coverage=SoilTemperatureCoverage(
                actual_start=date(2026, 4, 1),
                actual_end=date(2026, 4, 6),
                notes=("model layer",),
            ),
        )


@pytest.mark.asyncio
async def test_soil_temperature_report_separates_completed_and_forecast_days() -> None:
    report = await generate_soil_temperature_report(
        45.75,
        33.875,
        provider=_SoilProvider(),
    )

    assert report.latest_completed is not None
    assert report.latest_completed.local_date == date(2026, 4, 3)
    assert report.latest_completed.mean_c == pytest.approx(12.0)
    assert report.recent_mean_c == pytest.approx(11.0)
    assert report.recent_change_c == pytest.approx(2.0)
    assert [day.local_date for day in report.forecast] == [
        date(2026, 4, 4),
        date(2026, 4, 5),
        date(2026, 4, 6),
    ]
    assert report.depth_label == "модельный слой почвы 0–7 см"
    assert report.spatial_resolution_km == pytest.approx(9.0)


def test_soil_temperature_smoke_rejects_missing_history_provenance() -> None:
    data = SoilTemperatureData(
        meta=SoilTemperatureMeta(
            latitude=45.75,
            longitude=33.875,
            elevation_m=25.0,
            timezone="UTC",
            source="Open-Meteo ECMWF",
            model="test",
            depth_label="модельный слой почвы 0–7 см",
            retrieved_at=datetime(2026, 4, 3, tzinfo=timezone.utc),
            cache_ttl_seconds=3600,
        ),
        daily=pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-04-01", tz="UTC"),
                    "local_date": date(2026, 4, 1),
                    "t_min": 8.0,
                    "t_max": 12.0,
                    "t_mean": 10.0,
                    "valid_hours": 24,
                    "data_kind": "reanalysis",
                    "data_source": "Open-Meteo ERA5-Land",
                },
                {
                    "date": pd.Timestamp("2026-04-02", tz="UTC"),
                    "local_date": date(2026, 4, 2),
                    "t_min": 9.0,
                    "t_max": 13.0,
                    "t_mean": 11.0,
                    "valid_hours": 24,
                    "data_kind": "current_forecast",
                    "data_source": "Open-Meteo ECMWF",
                },
            ]
        ),
        forecast_days=1,
        coverage=SoilTemperatureCoverage(
            requested_start=date(2026, 4, 1),
            actual_start=date(2026, 4, 1),
            actual_end=date(2026, 4, 2),
            history_source=None,
            start_covered=True,
        ),
    )

    with pytest.raises(ValueError, match="provenance"):
        validate_soil_temperature_data(
            data,
            expected_start=date(2026, 4, 1),
            as_of=datetime(2026, 4, 2, 12, tzinfo=timezone.utc),
        )
