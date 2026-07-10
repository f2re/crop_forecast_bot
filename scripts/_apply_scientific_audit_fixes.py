from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_function(path: Path, function_name: str, source: str) -> None:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == function_name
        ),
        None,
    )
    if node is None or node.end_lineno is None:
        raise RuntimeError(f"Function {function_name} not found in {path}")
    lines = text.splitlines(keepends=True)
    replacement = textwrap.dedent(source).strip() + "\n\n"
    lines[node.lineno - 1 : node.end_lineno] = [replacement]
    path.write_text("".join(lines), encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


write(
    "src/agro/data_quality.py",
    r'''
    """Shared quality rules for daily agrometeorological series.

    Production providers must label every row as ``reanalysis``,
    ``operational_past`` or ``forecast``.  Timestamp comparison is retained only
    as a compatibility fallback for hand-built test frames; source labels are the
    authoritative partition because daily timestamps may represent local midnight
    rather than the moment when the forecast becomes valid.
    """
    from __future__ import annotations

    from collections.abc import Iterable

    import pandas as pd

    PAST_KINDS = frozenset({"observation", "reanalysis", "operational_past"})
    FORECAST_KINDS = frozenset({"forecast"})


    def prepare_daily_frame(
        frame: pd.DataFrame,
        required_columns: Iterable[str],
    ) -> pd.DataFrame:
        required = {"date", *required_columns}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(
                "Missing weather columns: " + ", ".join(sorted(missing))
            )

        columns = list(required)
        if "data_kind" in frame.columns:
            columns.append("data_kind")
        if "data_source" in frame.columns:
            columns.append("data_source")
        result = frame.loc[:, list(dict.fromkeys(columns))].copy()
        result["date"] = pd.to_datetime(result["date"], utc=True, errors="coerce")
        result = result.dropna(subset=["date"])

        if "data_kind" not in result.columns:
            today = pd.Timestamp.now(tz="UTC").normalize()
            result["data_kind"] = "operational_past"
            result.loc[
                result["date"].dt.normalize() > today,
                "data_kind",
            ] = "forecast"
        else:
            result["data_kind"] = (
                result["data_kind"].fillna("unknown").astype(str).str.casefold()
            )

        if "data_source" not in result.columns:
            result["data_source"] = "unspecified"
        else:
            result["data_source"] = result["data_source"].fillna("unspecified")

        return (
            result.sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
            .reset_index(drop=True)
        )


    def past_rows(frame: pd.DataFrame) -> pd.DataFrame:
        return frame[frame["data_kind"].isin(PAST_KINDS)].copy()


    def forecast_rows(frame: pd.DataFrame) -> pd.DataFrame:
        return frame[frame["data_kind"].isin(FORECAST_KINDS)].copy()


    def source_counts(frame: pd.DataFrame) -> dict[str, int]:
        if frame.empty:
            return {}
        values = frame["data_kind"].value_counts(dropna=False)
        return {str(kind): int(count) for kind, count in values.items()}
    ''',
)

indices = ROOT / "src/agro/indices.py"
replace_function(
    indices,
    "calc_htc",
    r'''
    def calc_htc(
        df_daily: pd.DataFrame,
        window_days: int = 30,
        min_valid_days: int = 20,
    ) -> dict:
        """Calculate Selyaninov HTC from completed past warm days only.

        Formula: ``HTC = 10 * sum(P) / sum(Tmean)`` for days with
        ``Tmean > 10 °C``. Forecast rows are excluded.  The result is suppressed
        when the requested window has insufficient warm-day coverage.
        """
        from src.agro.data_quality import past_rows, prepare_daily_frame, source_counts

        if window_days <= 0:
            raise ValueError("window_days must be positive")
        if min_valid_days <= 0 or min_valid_days > window_days:
            raise ValueError("min_valid_days must be within the requested window")

        frame = prepare_daily_frame(df_daily, {"t_mean", "precip_sum"})
        past = past_rows(frame)
        if past.empty:
            return {
                "htc": None,
                "sum_precip_mm": None,
                "sum_t_above10": None,
                "window_days": window_days,
                "available_days": 0,
                "valid_days": 0,
                "expected_days": window_days,
                "missing_days": window_days,
                "missing_fraction": 1.0,
                "min_valid_days": min_valid_days,
                "interpretation": "нет завершённых прошлых данных для расчёта",
                "data_sources": {},
                "method_reference": "Selyaninov hydrothermal coefficient",
                "units": "dimensionless",
            }

        end_day = past["date"].dt.normalize().max()
        start_day = end_day - pd.Timedelta(days=window_days - 1)
        window = past[
            (past["date"].dt.normalize() >= start_day)
            & (past["date"].dt.normalize() <= end_day)
        ].copy()
        valid = window.dropna(subset=["t_mean", "precip_sum"]).copy()
        valid_days = int(valid["date"].dt.normalize().nunique())
        missing_days = max(0, window_days - valid_days)
        missing_fraction = round(missing_days / window_days, 4)
        warm = valid[valid["t_mean"] > 10.0].copy()
        available_days = int(warm["date"].dt.normalize().nunique())

        if available_days:
            sum_precip = float(warm["precip_sum"].clip(lower=0).sum())
            sum_t = float(warm["t_mean"].sum())
        else:
            sum_precip = 0.0
            sum_t = 0.0

        if available_days < min_valid_days:
            value = None
            interpretation = (
                f"недостаточно валидных тёплых суток: {available_days}; "
                f"требуется не менее {min_valid_days}"
            )
        elif sum_t <= 0:
            value = None
            interpretation = "вегетационный период с Tср > 10°C не выделен"
        else:
            value = round(10.0 * sum_precip / sum_t, 3)
            if value < 0.5:
                interpretation = "засушливые условия"
            elif value < 1.0:
                interpretation = "недостаточное увлажнение"
            elif value < 1.5:
                interpretation = "умеренное увлажнение"
            else:
                interpretation = "повышенное увлажнение"

        return {
            "htc": value,
            "sum_precip_mm": round(sum_precip, 1),
            "sum_t_above10": round(sum_t, 1),
            "window_days": window_days,
            "available_days": available_days,
            "valid_days": valid_days,
            "expected_days": window_days,
            "missing_days": missing_days,
            "missing_fraction": missing_fraction,
            "min_valid_days": min_valid_days,
            "interpretation": interpretation,
            "data_sources": source_counts(window),
            "method_reference": "Selyaninov hydrothermal coefficient",
            "units": "dimensionless",
        }
    ''',
)
replace_function(
    indices,
    "calc_gdd",
    r'''
    def calc_gdd(
        df_daily: pd.DataFrame,
        crop: str = "wheat",
        season_start: pd.Timestamp | None = None,
        *,
        phase: str | None = None,
        t_upper: float | None = None,
    ) -> dict:
        """Calculate growing degree days with explicit source partitioning.

        Daily contribution uses the simple mean-temperature method
        ``max(0, (Tmax + Tmin) / 2 - Tbase)``.  An upper cutoff is applied only
        when explicitly supplied; the catalogue does not invent one.
        """
        from src.agro.crop_catalog import get_crop
        from src.agro.data_quality import forecast_rows, past_rows, prepare_daily_frame

        crop_data = get_crop(crop)
        t_base = float(crop_data.get("t_base", 5.0))
        frame = prepare_daily_frame(df_daily, {"t_max", "t_min"})

        normalized_start: pd.Timestamp | None = None
        if season_start is not None:
            normalized_start = pd.Timestamp(season_start)
            if normalized_start.tzinfo is None:
                normalized_start = normalized_start.tz_localize("UTC")
            else:
                normalized_start = normalized_start.tz_convert("UTC")
            normalized_start = normalized_start.normalize()
            frame = frame[frame["date"].dt.normalize() >= normalized_start].copy()

        valid_temperature = frame.dropna(subset=["t_max", "t_min"]).copy()
        if t_upper is not None:
            if t_upper <= t_base:
                raise ValueError("t_upper must be greater than Tbase")
            valid_temperature["t_max_used"] = valid_temperature["t_max"].clip(
                upper=t_upper
            )
            valid_temperature["t_min_used"] = valid_temperature["t_min"].clip(
                upper=t_upper
            )
        else:
            valid_temperature["t_max_used"] = valid_temperature["t_max"]
            valid_temperature["t_min_used"] = valid_temperature["t_min"]
        valid_temperature["gdd_day"] = (
            (valid_temperature["t_max_used"] + valid_temperature["t_min_used"])
            / 2.0
            - t_base
        ).clip(lower=0)

        past = past_rows(frame)
        forecast = forecast_rows(frame)
        valid_past = valid_temperature[
            valid_temperature["data_kind"].isin(
                {"observation", "reanalysis", "operational_past"}
            )
        ].copy()
        valid_forecast = valid_temperature[
            valid_temperature["data_kind"] == "forecast"
        ].copy()

        gdd_by_source = {
            str(kind): round(float(group["gdd_day"].sum()), 1)
            for kind, group in valid_past.groupby("data_kind")
        }
        past_gdd = round(float(valid_past["gdd_day"].sum()), 1)
        forecast_gdd = round(float(valid_forecast["gdd_day"].sum()), 1)

        period_is_season = False
        if normalized_start is not None and not past.empty:
            earliest_past = past["date"].dt.normalize().min()
            period_is_season = bool(earliest_past <= normalized_start)

        if not past.empty:
            actual_start = past["date"].dt.normalize().min()
            actual_end = past["date"].dt.normalize().max()
            expected_start = normalized_start if period_is_season else actual_start
            expected_days = int((actual_end - expected_start).days) + 1
            valid_days = int(valid_past["date"].dt.normalize().nunique())
        else:
            actual_start = None
            actual_end = None
            expected_days = 0
            valid_days = 0
        missing_days = max(0, expected_days - valid_days)
        missing_fraction = (
            round(missing_days / expected_days, 4) if expected_days else 0.0
        )

        if phase:
            phenology_note = (
                f"Фактическая фаза «{phase}» указана пользователем; "
                "она не рассчитана по ГДД."
            )
        else:
            phenology_note = (
                "Автоматическая фенофаза не выводится: пороги требуют "
                "независимой региональной валидации."
            )

        return {
            "crop": crop,
            "t_base": t_base,
            "t_upper": t_upper,
            "gdd_past": past_gdd,
            "gdd_forecast_7d": forecast_gdd,
            "gdd_by_source": gdd_by_source,
            "gdd_reanalysis": gdd_by_source.get("reanalysis", 0.0),
            "gdd_operational_past": gdd_by_source.get("operational_past", 0.0),
            "current_phase": phase,
            "next_phase": None,
            "period_is_season": period_is_season,
            "period_start": actual_start.isoformat() if actual_start is not None else None,
            "period_end": actual_end.isoformat() if actual_end is not None else None,
            "valid_days": valid_days,
            "expected_days": expected_days,
            "missing_days": missing_days,
            "missing_fraction": missing_fraction,
            "phenology_note": phenology_note,
            "phenology_thresholds": crop_data.get("gdd_stages", {}),
            "method_reference": (
                "McMaster & Wilhelm (1997), Agricultural and Forest Meteorology "
                "87:291-300, simple mean-temperature GDD method"
            ),
            "units": "°C·day",
            "source_partition": (
                "observation/reanalysis/operational_past are accumulated; "
                "forecast is reported separately"
            ),
        }
    ''',
)
replace_function(
    indices,
    "calc_frost_risk",
    r'''
    def calc_frost_risk(
        df_daily: pd.DataFrame,
        utc_offset_seconds: int = 0,
        *,
        crop: str | None = None,
        phase: str | None = None,
        elevation_m: float | None = None,
    ) -> dict:
        """Screen forecast Tmin at 2 m without fabricating damage probability."""
        from src.agro.data_quality import forecast_rows, prepare_daily_frame

        frame = prepare_daily_frame(df_daily, {"t_min"})
        future = forecast_rows(frame).dropna(subset=["t_min"]).copy()
        alerts: list[dict] = []
        offset = timedelta(seconds=utc_offset_seconds)
        now = _now_utc()

        for _, row in future.iterrows():
            t_min = float(row["t_min"])
            if t_min > FROST_WARNING_T:
                continue
            lead_hours = max(0, int((row["date"] - now).total_seconds() // 3600))
            local_date = row["date"] + offset
            level = "critical" if t_min <= FROST_CRITICAL_T else "warning"
            alerts.append(
                {
                    "date": row["date"].strftime("%d.%m %H:%M UTC"),
                    "date_local": local_date.strftime("%d.%m %H:%M"),
                    "event_date": local_date.strftime("%Y-%m-%d"),
                    "t_min": round(t_min, 1),
                    "min_temp": round(t_min, 1),
                    "lead_hours": lead_hours,
                    "level": level,
                    "data_kind": "forecast",
                    "action": (
                        "уточнить локальный прогноз, фактическую фазу и условия "
                        "понижений рельефа"
                    ),
                }
            )

        context_parts = []
        if crop:
            context_parts.append(f"crop={crop}")
        if phase:
            context_parts.append(f"phase={phase}")
        if elevation_m is not None:
            context_parts.append(f"model_elevation={elevation_m:.0f} m")
        return {
            "alerts": alerts,
            "frost_free_days_7d": max(0, int(len(future) - len(alerts))),
            "forecast_contains_48h": bool(len(future) >= 2),
            "forecast_days": int(len(future)),
            "method_note": (
                "общий скрининг только по прогнозной Tmin воздуха на высоте 2 м; "
                "это не температура растений и не crop-specific damage threshold"
            ),
            "context_note": ", ".join(context_parts) if context_parts else None,
            "method_reference": "provider daily minimum air temperature at 2 m",
            "units": "°C",
        }
    ''',
)
replace_function(
    indices,
    "calc_et0_balance",
    r'''
    def calc_et0_balance(
        df_daily: pd.DataFrame,
        window_days: int = 7,
        min_valid_days: int | None = None,
    ) -> dict:
        """Calculate P - provider ET0 only when paired past data are sufficient."""
        import math

        from src.agro.data_quality import past_rows, prepare_daily_frame, source_counts

        if window_days <= 0:
            raise ValueError("window_days must be positive")
        required_days = (
            max(1, math.ceil(window_days * 0.7))
            if min_valid_days is None
            else min_valid_days
        )
        if required_days <= 0 or required_days > window_days:
            raise ValueError("min_valid_days must be within the requested window")

        frame = prepare_daily_frame(df_daily, {"precip_sum", "et0_sum"})
        past = past_rows(frame)
        if past.empty:
            return {
                "available": False,
                "precip_sum_mm": None,
                "et0_sum_mm": None,
                "balance_mm": None,
                "status": "нет завершённых прошлых данных",
                "window_days": window_days,
                "valid_days": 0,
                "expected_days": window_days,
                "missing_days": window_days,
                "missing_fraction": 1.0,
                "min_valid_days": required_days,
                "et0_source": "Open-Meteo et0_fao_evapotranspiration",
                "data_sources": {},
                "method_reference": "P - ET0 diagnostic balance; ET0 is provider data",
                "units": "mm",
            }

        end_day = past["date"].dt.normalize().max()
        start_day = end_day - pd.Timedelta(days=window_days - 1)
        window = past[
            (past["date"].dt.normalize() >= start_day)
            & (past["date"].dt.normalize() <= end_day)
        ].copy()
        valid = window.dropna(subset=["precip_sum", "et0_sum"]).copy()
        valid_days = int(valid["date"].dt.normalize().nunique())
        missing_days = max(0, window_days - valid_days)
        missing_fraction = round(missing_days / window_days, 4)

        if valid_days < required_days:
            return {
                "available": False,
                "precip_sum_mm": None,
                "et0_sum_mm": None,
                "balance_mm": None,
                "status": (
                    f"недостаточно парных данных: {valid_days} сут.; "
                    f"требуется не менее {required_days}"
                ),
                "window_days": window_days,
                "valid_days": valid_days,
                "expected_days": window_days,
                "missing_days": missing_days,
                "missing_fraction": missing_fraction,
                "min_valid_days": required_days,
                "et0_source": "Open-Meteo et0_fao_evapotranspiration",
                "data_sources": source_counts(window),
                "method_reference": "P - ET0 diagnostic balance; ET0 is provider data",
                "units": "mm",
            }

        precip = float(valid["precip_sum"].clip(lower=0).sum())
        et0 = float(valid["et0_sum"].clip(lower=0).sum())
        balance = round(precip - et0, 1)
        if balance >= 0:
            status = "профицит по диагностическому балансу"
        elif balance >= -30:
            status = "умеренный дефицит по диагностическому балансу"
        else:
            status = "выраженный дефицит; требуется проверка влажности почвы"
        return {
            "available": True,
            "precip_sum_mm": round(precip, 1),
            "et0_sum_mm": round(et0, 1),
            "balance_mm": balance,
            "status": status,
            "window_days": window_days,
            "valid_days": valid_days,
            "expected_days": window_days,
            "missing_days": missing_days,
            "missing_fraction": missing_fraction,
            "min_valid_days": required_days,
            "et0_source": "Open-Meteo et0_fao_evapotranspiration",
            "data_sources": source_counts(window),
            "method_reference": "P - ET0 diagnostic balance; ET0 is provider data",
            "units": "mm",
        }
    ''',
)
replace_function(
    indices,
    "compute_all_indices",
    r'''
    def compute_all_indices(
        df_daily: pd.DataFrame,
        crop: str = "wheat",
        *,
        utc_offset_seconds: int = 0,
        season_start: pd.Timestamp | None = None,
        phase: str | None = None,
        elevation_m: float | None = None,
    ) -> dict:
        return {
            "htc": calc_htc(df_daily),
            "gdd": calc_gdd(
                df_daily,
                crop,
                season_start=season_start,
                phase=phase,
            ),
            "frost": calc_frost_risk(
                df_daily,
                utc_offset_seconds=utc_offset_seconds,
                crop=crop,
                phase=phase,
                elevation_m=elevation_m,
            ),
            "et0_bal": calc_et0_balance(df_daily),
        }
    ''',
)

report_path = ROOT / "src/application/agro_report.py"
report_text = report_path.read_text(encoding="utf-8")
old_water = '''    lines.append(\n        f"• Баланс осадки − ET₀ за {water['window_days']} сут.: "\n        f"{water['balance_mm']:+.1f} мм. {water['status']}"\n    )\n'''
new_water = '''    if water.get("available") and water.get("balance_mm") is not None:\n        lines.append(\n            f"• Баланс осадки − ET₀ за {water['window_days']} сут.: "\n            f"{water['balance_mm']:+.1f} мм. {water['status']}"\n        )\n    else:\n        lines.append(\n            f"• Баланс осадки − ET₀ не рассчитан: {water['status']}. "\n            f"Валидных суток: {water.get('valid_days', 0)}/"\n            f"{water.get('expected_days', water['window_days'])}."\n        )\n'''
if old_water not in report_text:
    raise RuntimeError("ET0 formatting block was not found")
report_text = report_text.replace(old_water, new_water, 1)
old_forecast = '''    lines.append(f"• Прогноз прироста за 7 суток: {gdd['gdd_forecast_7d']:.1f}°C·сут")\n'''
new_forecast = '''    lines.append(f"• Прогноз прироста за 7 суток: {gdd['gdd_forecast_7d']:.1f}°C·сут")\n    source_parts = []\n    if gdd.get("gdd_reanalysis"):\n        source_parts.append(f"реанализ {gdd['gdd_reanalysis']:.1f}")\n    if gdd.get("gdd_operational_past"):\n        source_parts.append(f"оперативное прошлое {gdd['gdd_operational_past']:.1f}")\n    if source_parts:\n        lines.append("• Состав прошлой суммы ГДД: " + "; ".join(source_parts) + " °C·сут")\n'''
if old_forecast in report_text:
    report_text = report_text.replace(old_forecast, new_forecast, 1)
report_path.write_text(report_text, encoding="utf-8")

# Remove only clearly synthetic, unreachable training/prototype code.  Real provider,
# database and RAG modules are never deleted by this policy.
deleted: list[str] = []
for path in sorted(ROOT.rglob("*.py")):
    relative = path.relative_to(ROOT)
    if relative == Path("scripts/_apply_scientific_audit_fixes.py"):
        continue
    if relative.parts[0] not in {"src", "scripts"}:
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    synthetic_markers = (
        "synthetic_crop_data" in text
        or "RandomForestClassifier" in text
        or ("RandomForest" in text and "synthetic" in text.casefold())
    )
    prototype_location = (
        path.name == "train_basic_model.py"
        or "ml" in relative.parts
        or "yield" in path.stem.casefold()
        or "crop_recommender" in path.stem.casefold()
    )
    if synthetic_markers and prototype_location:
        path.unlink()
        deleted.append(str(relative))

write(
    "tests/test_scientific_data_quality.py",
    r'''
    from __future__ import annotations

    import math

    import pandas as pd

    from src.agro.indices import (
        calc_et0_balance,
        calc_frost_risk,
        calc_gdd,
        calc_htc,
    )


    def _frame(kinds: list[str]) -> pd.DataFrame:
        dates = pd.date_range("2026-05-01", periods=len(kinds), freq="D", tz="UTC")
        return pd.DataFrame(
            {
                "date": dates,
                "t_max": [25.0] * len(kinds),
                "t_min": [15.0] * len(kinds),
                "t_mean": [20.0] * len(kinds),
                "precip_sum": [2.0] * len(kinds),
                "et0_sum": [3.0] * len(kinds),
                "data_kind": kinds,
                "data_source": ["test-provider"] * len(kinds),
            }
        )


    def test_gdd_uses_source_labels_not_wall_clock_boundary() -> None:
        frame = _frame(["reanalysis", "operational_past", "forecast"])
        result = calc_gdd(frame, crop="corn")
        assert result["gdd_past"] == 20.0
        assert result["gdd_forecast_7d"] == 10.0
        assert result["gdd_reanalysis"] == 10.0
        assert result["gdd_operational_past"] == 10.0


    def test_htc_never_uses_forecast_precipitation() -> None:
        frame = _frame(["operational_past"] * 20 + ["forecast"] * 10)
        frame.loc[frame["data_kind"] == "forecast", "precip_sum"] = 1000.0
        result = calc_htc(frame, window_days=30, min_valid_days=20)
        assert result["htc"] == 0.1
        assert result["sum_precip_mm"] == 40.0
        assert result["data_sources"] == {"operational_past": 20}


    def test_et0_balance_does_not_fabricate_zero_from_missing_values() -> None:
        frame = _frame(["operational_past"] * 7)
        frame[["precip_sum", "et0_sum"]] = math.nan
        result = calc_et0_balance(frame)
        assert result["available"] is False
        assert result["precip_sum_mm"] is None
        assert result["et0_sum_mm"] is None
        assert result["balance_mm"] is None
        assert result["missing_fraction"] == 1.0


    def test_et0_balance_requires_paired_past_data() -> None:
        frame = _frame(["operational_past"] * 4 + ["forecast"] * 3)
        result = calc_et0_balance(frame, window_days=7)
        assert result["available"] is False
        assert result["valid_days"] == 4


    def test_frost_screening_uses_forecast_rows_only() -> None:
        frame = _frame(["operational_past", "forecast"])
        frame.loc[0, "t_min"] = -10.0
        frame.loc[1, "t_min"] = -1.0
        result = calc_frost_risk(frame)
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["t_min"] == -1.0
        assert result["alerts"][0]["data_kind"] == "forecast"
    ''',
)

write(
    "tests/test_no_production_placeholders.py",
    r'''
    from __future__ import annotations

    import ast
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[1]


    def test_no_synthetic_ml_or_yield_model_is_shipped_in_runtime() -> None:
        forbidden = (
            "RandomForestClassifier",
            "synthetic_crop_data",
            "train_basic_model.py",
        )
        checked = list((ROOT / "src").rglob("*.py")) + list(
            (ROOT / "scripts").rglob("*.py")
        )
        for path in checked:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in forbidden:
                assert marker not in text, f"{marker} found in {path.relative_to(ROOT)}"


    def test_reachable_runtime_has_no_not_implemented_placeholders() -> None:
        roots = [
            ROOT / "src/bot/main.py",
            ROOT / "src/bot/scheduler.py",
            ROOT / "src/application/agro_report.py",
            ROOT / "src/api/open_meteo.py",
            ROOT / "src/agro/indices.py",
        ]
        for path in roots:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                    func = node.exc.func
                    if isinstance(func, ast.Name):
                        assert func.id != "NotImplementedError", path


    def test_capability_matrix_explicitly_disables_unimplemented_products() -> None:
        matrix = (ROOT / "docs/PRODUCTION_CAPABILITIES.md").read_text(
            encoding="utf-8"
        )
        assert "Прогноз урожайности | ❌ не реализован" in matrix
        assert "Синтетическая ML-модель | ❌ запрещена" in matrix
        assert "SPI | ❌ не рассчитывается" in matrix
    ''',
)

write(
    "docs/PRODUCTION_CAPABILITIES.md",
    f'''
    # Фактические production-возможности

    Этот файл является проверяемой матрицей возможностей. Наличие модуля или
    зависимости не означает, что функция доступна пользователю.

    | Функция | Статус | Источник/ограничение |
    |---|---|---|
    | Оперативная погода | ✅ production | Open-Meteo Forecast API |
    | Сезонный прошлый ряд | ⚠️ условно | Open-Meteo Historical Weather API, реанализ, не полевая станция |
    | ГДД | ✅ при достаточном покрытии | простая mean-temperature формула, Tbase из crop catalogue |
    | ГТК | ⚠️ только валидное прошлое окно | прогнозные строки исключаются; при нехватке дней значение не выводится |
    | Баланс осадки − ET₀ | ⚠️ диагностический | ET₀ приходит от провайдера; при пропусках ноль не подставляется |
    | Скрининг заморозка | ⚠️ общий | Tmin воздуха 2 м; не вероятность повреждения растений |
    | Ежедневные отчёты | ✅ production | только активное поле, Redis deduplication |
    | RAG-советник | ⚠️ optional | только при индексированной литературе, с источниками |
    | ERA5-Land/CDS в Telegram flow | ❌ не подключён | экспериментальные/legacy модули не считаются production-функцией |
    | SoilGrids | ❌ не подключён | не показывается пользователю |
    | Спутниковые NDVI/LAI | ❌ не подключены | не показываются пользователю |
    | SPI | ❌ не рассчитывается | короткий прогноз недостаточен |
    | Прогноз урожайности | ❌ не реализован | нет валидированной полевой выборки |
    | Синтетическая ML-модель | ❌ запрещена | не поставляется в runtime и не имеет заявленной точности |

    Удалённые синтетические prototype-файлы этого среза:
    {chr(10).join(f'- `{item}`' for item in deleted) if deleted else '- не обнаружены'}
    ''',
)

write(
    "docs/END_TO_END_AUDIT_2026-07-10.md",
    f'''
    # Сквозной аудит runtime и расчётов — 2026-07-10

    Проверен путь: Telegram/FSM → PostgreSQL/Alembic → Open-Meteo → расчёты →
    отчёт/RAG → scheduler/Redis → Bash/systemd.

    ## Исправленные критические дефекты

    1. Суточные строки больше не делятся на прошлое и прогноз сравнением timestamp
       с текущим UTC-моментом. Авторитетна метка `data_kind`, заданная provider
       adapter. Это исключает утечку локального календарного дня между суммой ГДД
       и прогнозным приростом.
    2. Баланс осадки − ET₀ больше не возвращает фиктивные `0.0 мм` при полном
       отсутствии парных данных. Значение становится недоступным с числом валидных
       и пропущенных суток.
    3. ГТК использует только завершённые прошлые строки; прогнозные осадки не
       участвуют в коэффициенте.
    4. Frost screening использует только строки `forecast` и остаётся общим
       температурным screening, а не вероятностью повреждения культуры.
    5. Удалены явно синтетические Random Forest/training prototypes:
       {', '.join(deleted) if deleted else 'не обнаружены'}.

    ## Проверяемые инварианты

    - production provider не содержит генерации случайных погодных данных;
    - reanalysis, operational past и forecast имеют разные `data_kind`;
    - NaN не заменяется нулём в ET₀-балансе;
    - формулы возвращают единицы, ссылку на метод, покрытие и долю пропусков;
    - недоступные продукты перечислены в `docs/PRODUCTION_CAPABILITIES.md` и не
      рекламируются как работающие;
    - schema revision, PostgreSQL, Redis, heartbeat и systemd проверяются до
      объявления сервиса готовым.

    ## Что всё ещё не является production-функцией

    SoilGrids, спутниковые NDVI/LAI, SPI, прогноз урожайности, локальный FAO-56
    Penman–Monteith и crop/phase-specific damage probability. Эти возможности
    должны оставаться выключенными до реализации provider contracts, источников,
    валидации и интеграционных тестов.
    ''',
)

# Add an honest capability link and updated limitations without rewriting the
# operator-oriented README structure.
readme = ROOT / "README.md"
readme_text = readme.read_text(encoding="utf-8")
if "PRODUCTION_CAPABILITIES.md" not in readme_text:
    marker = "## 📚 Документация"
    insertion = (
        "## 🔎 Проверенные возможности и ограничения\n\n"
        "Полная матрица реально подключённых и отключённых функций: "
        "[production capabilities](docs/PRODUCTION_CAPABILITIES.md). "
        "Отсутствующая функция не заменяется синтетическими данными или "
        "эвристическим результатом.\n\n"
    )
    readme_text = readme_text.replace(marker, insertion + marker, 1)
readme.write_text(readme_text, encoding="utf-8")

plan = ROOT / "docs/DEVELOPMENT_PLAN.md"
plan_text = plan.read_text(encoding="utf-8")n