from datetime import date, datetime, timezone

import pandas as pd
import pytest

from src.domain.weather import AgroWeatherData, WeatherCoverage, WeatherMeta
from src.ops.provider_smoke import validate_weather_data

_AS_OF = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
_SEASON_START = date(2026, 7, 10)


def _data(
    frame: pd.DataFrame,
    *,
    model: str | None = "auto",
    retrieved_at: datetime | None = datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
    requested_season_start: date | None = _SEASON_START,
    season_coverage_complete: bool = True,
    history_source: str | None = "Open-Meteo Historical Weather API",
    actual_start: date | None = None,
    actual_end: date | None = None,
) -> AgroWeatherData:
    local_dates = list(frame["local_date"])
    return AgroWeatherData(
        meta=WeatherMeta(
            latitude=55.75,
            longitude=37.62,
            elevation_m=150.0,
            utc_offset_seconds=3 * 3600,
            timezone="Europe/Moscow",
            source="Open-Meteo Forecast API",
            model=model,
            retrieved_at=retrieved_at,
            cache_ttl_seconds=3600,
        ),
        daily=frame,
        hourly=pd.DataFrame(),
        past_days=14,
        forecast_days=7,
        coverage=WeatherCoverage(
            requested_season_start=requested_season_start,
            actual_start=actual_start or min(local_dates),
            actual_end=actual_end or max(local_dates),
            season_coverage_complete=season_coverage_complete,
            history_source=history_source,
        ),
    )


def _valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-09T21:00:00Z", "2026-07-10T21:00:00Z"]),
            "local_date": [date(2026, 7, 10), date(2026, 7, 11)],
            "t_max": [24.0, 25.0],
            "t_min": [14.0, 15.0],
            "t_mean": [19.0, 20.0],
            "precip_sum": [1.0, 0.0],
            "et0_sum": [3.0, 3.2],
            "data_kind": ["operational_past", "forecast"],
            "data_source": ["forecast-api", "forecast-api"],
        }
    )


def test_provider_smoke_accepts_gap_free_partitioned_contract() -> None:
    result = validate_weather_data(
        _data(_valid_frame()),
        expected_season_start=_SEASON_START,
        as_of=_AS_OF,
    )

    assert result.completed_rows == 1
    assert result.forecast_rows == 1
    assert result.current_local_date == "2026-07-11"
    assert result.actual_start == "2026-07-10"
    assert result.actual_end == "2026-07-11"
    assert result.season_coverage_complete is True
    assert result.model == "auto"
    assert result.retrieved_at == "2026-07-10T12:00:00+00:00"
    assert result.cache_ttl_seconds == 3600


def test_provider_smoke_rejects_dataset_without_forecast() -> None:
    frame = _valid_frame().iloc[[0]].copy()
    with pytest.raises(ValueError, match="no forecast rows"):
        validate_weather_data(
            _data(frame),
            as_of=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        )


def test_provider_smoke_rejects_missing_provenance() -> None:
    with pytest.raises(ValueError, match="model provenance"):
        validate_weather_data(_data(_valid_frame(), model=None), as_of=_AS_OF)
    with pytest.raises(ValueError, match="retrieval timestamp"):
        validate_weather_data(_data(_valid_frame(), retrieved_at=None), as_of=_AS_OF)


def test_provider_smoke_rejects_duplicate_local_dates() -> None:
    frame = pd.concat([_valid_frame(), _valid_frame().iloc[[1]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate local dates"):
        validate_weather_data(_data(frame), as_of=_AS_OF)


def test_provider_smoke_rejects_local_calendar_gap() -> None:
    frame = _valid_frame().copy()
    frame.loc[0, "date"] = pd.Timestamp("2026-07-08T21:00:00Z")
    frame.loc[0, "local_date"] = date(2026, 7, 9)
    with pytest.raises(ValueError, match="local-calendar gap"):
        validate_weather_data(_data(frame), as_of=_AS_OF)


def test_provider_smoke_rejects_current_day_in_completed_partition() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2026-07-09T21:00:00Z",
                    "2026-07-10T21:00:00Z",
                    "2026-07-11T21:00:00Z",
                ]
            ),
            "local_date": [
                date(2026, 7, 10),
                date(2026, 7, 11),
                date(2026, 7, 12),
            ],
            "t_max": [24.0, 25.0, 26.0],
            "t_min": [14.0, 15.0, 16.0],
            "t_mean": [19.0, 20.0, 21.0],
            "precip_sum": [1.0, 0.0, 0.0],
            "et0_sum": [3.0, 3.2, 3.3],
            "data_kind": ["operational_past", "operational_past", "forecast"],
            "data_source": ["forecast-api"] * 3,
        }
    )
    with pytest.raises(ValueError, match="current local calendar day"):
        validate_weather_data(_data(frame), as_of=_AS_OF)


def test_provider_smoke_rejects_incomplete_requested_season() -> None:
    with pytest.raises(ValueError, match="complete requested season coverage"):
        validate_weather_data(
            _data(_valid_frame(), season_coverage_complete=False),
            expected_season_start=_SEASON_START,
            as_of=_AS_OF,
        )


def test_provider_smoke_rejects_coverage_metadata_mismatch() -> None:
    with pytest.raises(ValueError, match="Coverage metadata"):
        validate_weather_data(
            _data(_valid_frame(), actual_start=date(2026, 7, 9)),
            as_of=_AS_OF,
        )
