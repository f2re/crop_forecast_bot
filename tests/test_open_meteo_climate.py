from datetime import date

from src.api import open_meteo_climate as climate


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def _payload(days: list[str], *, trailing_missing: bool = False) -> dict:
    length = len(days)
    t_max: list[float | None] = [-2.0 + index for index in range(length)]
    t_min: list[float | None] = [-8.0 + index for index in range(length)]
    t_mean: list[float | None] = [-5.0 + index for index in range(length)]
    precip: list[float | None] = [float(index) for index in range(length)]
    et0: list[float | None] = [0.1 + index * 0.1 for index in range(length)]
    if trailing_missing:
        t_max[-1] = None
        t_min[-1] = None
        t_mean[-1] = None
        precip[-1] = None
        et0[-1] = None
    return {
        "latitude": 55.7,
        "longitude": 37.6,
        "elevation": 170.0,
        "timezone": "Europe/Moscow",
        "daily": {
            "time": days,
            "temperature_2m_max": t_max,
            "temperature_2m_min": t_min,
            "temperature_2m_mean": t_mean,
            "precipitation_sum": precip,
            "et0_fao_evapotranspiration": et0,
        },
    }


def test_fixed_era5_land_contract_and_homogeneous_current_series(monkeypatch) -> None:
    monkeypatch.setattr(climate, "REFERENCE_START", date(1991, 1, 1))
    monkeypatch.setattr(climate, "REFERENCE_END", date(1991, 1, 3))
    session = FakeSession(
        [
            FakeResponse(_payload(["1991-01-01", "1991-01-02", "1991-01-03"])),
            FakeResponse(
                _payload(
                    ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04"],
                    trailing_missing=True,
                )
            ),
        ]
    )
    monkeypatch.setattr(climate, "_get_http_session", lambda: session)

    data = climate._fetch_climate_reference_sync(
        55.75,
        37.62,
        "Europe/Moscow",
        date(2026, 4, 1),
        date(2026, 4, 4),
    )

    assert len(session.calls) == 2
    reference_url, reference_kwargs = session.calls[0]
    current_url, current_kwargs = session.calls[1]
    assert reference_url == current_url == climate.ARCHIVE_URL
    for kwargs in (reference_kwargs, current_kwargs):
        assert kwargs["params"]["models"] == "era5_land"
        assert kwargs["params"]["cell_selection"] == "land"
        assert "temperature_2m_max" in kwargs["params"]["daily"]
        assert "temperature_2m_min" in kwargs["params"]["daily"]
        assert "temperature_2m_mean" in kwargs["params"]["daily"]
        assert kwargs["timeout"] == (5, 90)
    assert reference_kwargs["params"]["start_date"] == "1991-01-01"
    assert reference_kwargs["params"]["end_date"] == "1991-01-03"
    assert reference_kwargs["expire_after"] == climate.REFERENCE_CACHE_TTL_SECONDS
    assert current_kwargs["params"]["start_date"] == "2026-04-01"
    assert current_kwargs["params"]["end_date"] == "2026-04-04"
    assert current_kwargs["expire_after"] == climate.CURRENT_CACHE_TTL_SECONDS

    assert data.meta.model == "era5_land"
    assert data.meta.source == climate.CLIMATE_SOURCE
    assert data.meta.spatial_resolution_km == 11.0
    assert data.meta.comparison_start == date(2026, 4, 1)
    assert data.meta.comparison_end == date(2026, 4, 3)
    assert len(data.reference_daily) == 3
    assert len(data.current_daily) == 3
    assert set(data.reference_daily["data_source"]) == {climate.CLIMATE_SOURCE}
    assert set(data.current_daily["data_source"]) == {climate.CLIMATE_SOURCE}
