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
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_fixed_era5_land_contract_and_metadata(monkeypatch) -> None:
    monkeypatch.setattr(climate, "REFERENCE_START", date(1991, 1, 1))
    monkeypatch.setattr(climate, "REFERENCE_END", date(1991, 1, 3))
    payload = {
        "latitude": 55.7,
        "longitude": 37.6,
        "elevation": 170.0,
        "timezone": "Europe/Moscow",
        "daily": {
            "time": ["1991-01-01", "1991-01-02", "1991-01-03"],
            "temperature_2m_max": [-2.0, -1.0, 0.0],
            "temperature_2m_min": [-8.0, -7.0, -6.0],
            "temperature_2m_mean": [-5.0, -4.0, -3.0],
            "precipitation_sum": [0.0, 1.0, 2.0],
            "et0_fao_evapotranspiration": [0.1, 0.1, 0.2],
        },
    }
    session = FakeSession(FakeResponse(payload))
    monkeypatch.setattr(climate, "_get_http_session", lambda: session)

    data = climate._fetch_climate_reference_sync(
        55.75,
        37.62,
        "Europe/Moscow",
    )

    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == climate.ARCHIVE_URL
    assert kwargs["params"]["models"] == "era5_land"
    assert kwargs["params"]["start_date"] == "1991-01-01"
    assert kwargs["params"]["end_date"] == "1991-01-03"
    assert kwargs["params"]["cell_selection"] == "land"
    assert "temperature_2m_max" in kwargs["params"]["daily"]
    assert "temperature_2m_min" in kwargs["params"]["daily"]
    assert "temperature_2m_mean" in kwargs["params"]["daily"]
    assert kwargs["expire_after"] == climate.CLIMATE_CACHE_TTL_SECONDS
    assert kwargs["timeout"] == (5, 90)
    assert data.meta.model == "era5_land"
    assert data.meta.source == climate.CLIMATE_SOURCE
    assert data.meta.spatial_resolution_km == 11.0
    assert set(data.daily["data_source"]) == {climate.CLIMATE_SOURCE}
