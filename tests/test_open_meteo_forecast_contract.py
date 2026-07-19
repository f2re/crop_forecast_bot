from src.api.open_meteo import _FORECAST_MODEL, _forecast_params


def test_generic_forecast_uses_default_best_match_without_model_alias() -> None:
    params = _forecast_params(55.75, 37.62)

    assert "models" not in params
    assert _FORECAST_MODEL == "best_match"
    assert params["timezone"] == "auto"
    assert params["forecast_days"] == 7
    assert "et0_fao_evapotranspiration" in params["daily"]
