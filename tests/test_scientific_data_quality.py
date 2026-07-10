from __future__ import annotations

import math

import pandas as pd

from src.agro.indices import calc_et0_balance, calc_frost_risk, calc_gdd, calc_htc


def frame(kinds: list[str]) -> pd.DataFrame:
    size = len(kinds)
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-05-01", periods=size, freq="D", tz="UTC"),
            "t_max": [25.0] * size,
            "t_min": [15.0] * size,
            "t_mean": [20.0] * size,
            "precip_sum": [2.0] * size,
            "et0_sum": [3.0] * size,
            "data_kind": kinds,
            "data_source": ["contract-test"] * size,
        }
    )


def test_gdd_partitions_by_provider_source_label() -> None:
    result = calc_gdd(
        frame(["reanalysis", "operational_past", "forecast"]),
        crop="corn",
    )
    assert result["gdd_past"] == 20.0
    assert result["gdd_forecast_7d"] == 10.0
    assert result["gdd_reanalysis"] == 10.0
    assert result["gdd_operational_past"] == 10.0


def test_htc_excludes_forecast_precipitation() -> None:
    data = frame(["operational_past"] * 20 + ["forecast"] * 10)
    data.loc[data["data_kind"] == "forecast", "precip_sum"] = 1000.0
    result = calc_htc(data, window_days=30, min_valid_days=20)
    assert result["htc"] == 1.0
    assert result["sum_precip_mm"] == 40.0
    assert result["data_sources"] == {"operational_past": 20}


def test_et0_missing_values_do_not_become_zero() -> None:
    data = frame(["operational_past"] * 7)
    data[["precip_sum", "et0_sum"]] = math.nan
    result = calc_et0_balance(data)
    assert result["available"] is False
    assert result["precip_sum_mm"] is None
    assert result["et0_sum_mm"] is None
    assert result["balance_mm"] is None
    assert result["missing_fraction"] == 1.0


def test_et0_requires_paired_past_days() -> None:
    result = calc_et0_balance(frame(["operational_past"] * 4 + ["forecast"] * 3))
    assert result["available"] is False
    assert result["valid_days"] == 4


def test_frost_uses_forecast_rows_only() -> None:
    data = frame(["operational_past", "forecast"])
    data.loc[0, "t_min"] = -10.0
    data.loc[1, "t_min"] = -1.0
    result = calc_frost_risk(data)
    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["t_min"] == -1.0
    assert result["alerts"][0]["data_kind"] == "forecast"
