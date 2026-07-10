from __future__ import annotations

import ast
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_function(path: Path, name: str, source: str) -> None:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == name
        ),
        None,
    )
    if node is None or node.end_lineno is None:
        raise RuntimeError(f"{name} not found in {path}")
    lines = text.splitlines(keepends=True)
    lines[node.lineno - 1 : node.end_lineno] = [
        textwrap.dedent(source).strip() + "\n\n"
    ]
    path.write_text("".join(lines), encoding="utf-8")


def write(relative: str, source: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")


write(
    "src/agro/data_quality.py",
    '''
    """Quality gates and source partitioning for daily weather data.

    Production provider rows are labelled ``reanalysis``, ``operational_past``
    or ``forecast``.  Those labels are authoritative: a daily timestamp can
    represent local midnight and therefore must not be classified by comparing
    it with the current UTC clock time.
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

        columns = ["date", *sorted(required - {"date"})]
        for optional in ("data_kind", "data_source"):
            if optional in frame.columns:
                columns.append(optional)
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
        counts = frame["data_kind"].value_counts(dropna=False)
        return {str(kind): int(count) for kind, count in counts.items()}
    ''',
)

indices_path = ROOT / "src/agro/indices.py"
replace_function(
    indices_path,
    "calc_htc",
    '''
    def calc_htc(
        df_daily: pd.DataFrame,
        window_days: int = 30,
        min_valid_days: int = 20,
    ) -> dict:
        """Calculate Selyaninov HTC from completed past warm days only.

        ``HTC = 10 * sum(P) / sum(Tmean)`` for days with ``Tmean > 10 °C``.
        Forecast precipitation is excluded and the value is suppressed when
        coverage is insufficient.
        """
        from src.agro.data_quality import past_rows, prepare_daily_frame, source_counts

        if window_days <= 0:
            raise ValueError("window_days must be positive")
        if min_valid_days <= 0 or min_valid_days > window_days:
            raise ValueError("min_valid_days must be within window_days")

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
                "interpretation": "нет завершённых прошлых данных",
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
        warm_days = int(warm["date"].dt.normalize().nunique())
        sum_precip = float(warm["precip_sum"].clip(lower=0).sum())
        sum_t = float(warm["t_mean"].sum())

        if warm_days < min_valid_days:
            value = None
            interpretation = (
                f"недостаточно валидных тёплых суток: {warm_days}; "
                f"требуется не менее {min_valid_days}"
            )
        elif sum_t <= 0:
            value = None
            interpretation = "период с Tср > 10°C не выделен"
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
            "available_days": warm_days,
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
    indices_path,
    "calc_gdd",
    '''
    def calc_gdd(
        df_daily: pd.DataFrame,
        crop: str = "wheat",
        season_start: pd.Timestamp | None = None,
        *,
        phase: str | None = None,
        t_upper: float | None = None,
    ) -> dict:
        """Calculate GDD and keep past sources separate from forecast."""
        from src.agro.crop_catalog import get_crop
        from src.agro.data_quality import past_rows, prepare_daily_frame

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

        valid = frame.dropna(subset=["t_max", "t_min"]).copy()
        if t_upper is not None:
            if t_upper <= t_base:
                raise ValueError("t_upper must be greater than Tbase")
            valid["t_max_used"] = valid["t_max"].clip(upper=t_upper)
            valid["t_min_used"] = valid["t_min"].clip(upper=t_upper)
        else:
            valid["t_max_used"] = valid["t_max"]
            valid["t_min_used"] = valid["t_min"]
        valid["gdd_day"] = (
            (valid["t_max_used"] + valid["t_min_used"]) / 2.0 - t_base
        ).clip(lower=0)

        past = past_rows(frame)
        past_kinds = {"observation", "reanalysis", "operational_past"}
        valid_past = valid[valid["data_kind"].isin(past_kinds)].copy()
        valid_forecast = valid[valid["data_kind"] == "forecast"].copy()
        gdd_by_source = {
            str(kind): round(float(group["gdd_day"].sum()), 1)
            for kind, group in valid_past.groupby("data_kind")
        }
        past_gdd = round(float(valid_past["gdd_day"].sum()), 1)
        forecast_gdd = round(float(valid_forecast["gdd_day"].sum()), 1)

        period_is_season = False
        if normalized_start is not None and not past.empty:
            period_is_season = bool(
                past["date"].dt.normalize().min() <= normalized_start
            )

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
                f"Фактическая фаза «{phase}» указана пользователем и не "
                "рассчитана по ГДД."
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
                "McMaster & Wilhelm (1997), Agricultural and Forest "
                "Meteorology 87:291-300, simple mean-temperature method"
            ),
            "units": "°C·day",
            "source_partition": (
                "past observation/reanalysis/operational rows accumulated; "
                "forecast reported separately"
            ),
        }
    ''',
)
replace_function(
    indices_path,
    "calc_frost_risk",
    '''
    def calc_frost_risk(
        df_daily: pd.DataFrame,
        utc_offset_seconds: int = 0,
        *,
        crop: str | None = None,
        phase: str | None = None,
        elevation_m: float | None = None,
    ) -> dict:
        """Screen forecast Tmin at 2 m without damage-probability claims."""
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
            local_date = row["date"] + offset
            alerts.append(
                {
                    "date": row["date"].strftime("%d.%m %H:%M UTC"),
                    "date_local": local_date.strftime("%d.%m %H:%M"),
                    "event_date": local_date.strftime("%Y-%m-%d"),
                    "t_min": round(t_min, 1),
                    "min_temp": round(t_min, 1),
                    "lead_hours": max(
                        0,
                        int((row["date"] - now).total_seconds() // 3600),
                    ),
                    "level": "critical" if t_min <= FROST_CRITICAL_T else "warning",
                    "data_kind": "forecast",
                    "action": (
                        "уточнить локальный прогноз, фактическую фазу и "
                        "условия понижений рельефа"
                    ),
                }
            )

        context = []
        if crop:
            context.append(f"crop={crop}")
        if phase:
            context.append(f"phase={phase}")
        if elevation_m is not None:
            context.append(f"model_elevation={elevation_m:.0f} m")
        return {
            "alerts": alerts,
            "frost_free_days_7d": max(0, int(len(future) - len(alerts))),
            "forecast_contains_48h": bool(len(future) >= 2),
            "forecast_days": int(len(future)),
            "method_note": (
                "общий скрининг по прогнозной Tmin воздуха 2 м; это не "
                "температура растений и не crop-specific damage threshold"
            ),
            "context_note": ", ".join(context) if context else None,
            "method_reference": "provider daily minimum air temperature at 2 m",
            "units": "°C",
        }
    ''',
)
replace_function(
    indices_path,
    "calc_et0_balance",
    '''
    def calc_et0_balance(
        df_daily: pd.DataFrame,
        window_days: int = 7,
        min_valid_days: int | None = None,
    ) -> dict:
        """Calculate P - provider ET0 when paired past data are sufficient."""
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
            raise ValueError("min_valid_days must be within window_days")

        frame = prepare_daily_frame(df_daily, {"precip_sum", "et0_sum"})
        past = past_rows(frame)
        if past.empty:
            valid_days = 0
            missing_days = window_days
            window = past
        else:
            end_day = past["date"].dt.normalize().max()
            start_day = end_day - pd.Timedelta(days=window_days - 1)
            window = past[
                (past["date"].dt.normalize() >= start_day)
                & (past["date"].dt.normalize() <= end_day)
            ].copy()
            valid_days = int(
                window.dropna(subset=["precip_sum", "et0_sum"])["date"]
                .dt.normalize()
                .nunique()
            )
            missing_days = max(0, window_days - valid_days)
        missing_fraction = round(missing_days / window_days, 4)
        common = {
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
                **common,
            }

        valid = window.dropna(subset=["precip_sum", "et0_sum"]).copy()
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
            **common,
        }
    ''',
)
replace_function(
    indices_path,
    "compute_all_indices",
    '''
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
replace_function(
    indices_path,
    "format_indices_for_rag",
    '''
    def format_indices_for_rag(
        indices: dict,
        crop: str,
        crop_phase: str | None = None,
    ) -> str:
        lines = ["=== ОПЕРАТИВНОЕ СОСТОЯНИЕ ПОЛЯ ===", f"Культура: {crop}"]
        phase = crop_phase or indices.get("gdd", {}).get("current_phase")
        lines.append(
            f"Фактическая фаза: {phase} (наблюдение пользователя)"
            if phase
            else "Фактическая фаза: не указана"
        )

        htc = indices.get("htc", {})
        if htc.get("htc") is not None:
            lines.append(f"ГТК: {htc['htc']:.2f} — {htc.get('interpretation', '')}")
        else:
            lines.append(f"ГТК: не рассчитан — {htc.get('interpretation', 'нет данных')}")

        gdd = indices.get("gdd", {})
        label = "с начала сезона" if gdd.get("period_is_season") else "за доступный период"
        lines.append(f"ГДД {label}: {gdd.get('gdd_past', 0):.1f} °C·сут")
        lines.append(f"Прогнозный прирост ГДД: {gdd.get('gdd_forecast_7d', 0):.1f} °C·сут")

        alerts = indices.get("frost", {}).get("alerts", [])
        if alerts:
            event = alerts[0]
            lines.append(
                f"Общий температурный риск: Tmin воздуха 2 м "
                f"{event['t_min']}°C, {event['date_local']}"
            )

        water = indices.get("et0_bal", {})
        if water.get("available") and water.get("balance_mm") is not None:
            lines.append(f"Баланс осадки − ET0: {water['balance_mm']:.1f} мм")
        else:
            lines.append(f"Баланс осадки − ET0: не рассчитан — {water.get('status', 'нет данных')}")
        lines.append(
            "Источники разделены: реанализ, оперативное прошлое модели и прогноз; "
            "это не климатическая норма и не прогноз урожайности"
        )
        lines.append("=== КОНЕЦ ДАННЫХ ===")
        return "\\n".join(lines)
    ''',
)

report = ROOT / "src/application/agro_report.py"
report_text = report.read_text(encoding="utf-8")
old = '''    lines.append(\n        f"• Баланс осадки − ET₀ за {water['window_days']} сут.: "\n        f"{water['balance_mm']:+.1f} мм. {water['status']}"\n    )\n'''
new = '''    if water.get("available") and water.get("balance_mm") is not None:\n        lines.append(\n            f"• Баланс осадки − ET₀ за {water['window_days']} сут.: "\n            f"{water['balance_mm']:+.1f} мм. {water['status']}"\n        )\n    else:\n        lines.append(\n            f"• Баланс осадки − ET₀ не рассчитан: {water['status']}. "\n            f"Валидных суток: {water.get('valid_days', 0)}/"\n            f"{water.get('expected_days', water['window_days'])}."\n        )\n'''
if old not in report_text:
    raise RuntimeError("ET0 report block not found")
report_text = report_text.replace(old, new, 1)
forecast_line = '''    lines.append(f"• Прогноз прироста за 7 суток: {gdd['gdd_forecast_7d']:.1f}°C·сут")\n'''
source_lines = '''    lines.append(f"• Прогноз прироста за 7 суток: {gdd['gdd_forecast_7d']:.1f}°C·сут")\n    source_parts = []\n    if gdd.get("gdd_reanalysis"):\n        source_parts.append(f"реанализ {gdd['gdd_reanalysis']:.1f}")\n    if gdd.get("gdd_operational_past"):\n        source_parts.append(f"оперативное прошлое {gdd['gdd_operational_past']:.1f}")\n    if source_parts:\n        lines.append("• Состав прошлой суммы ГДД: " + "; ".join(source_parts) + " °C·сут")\n'''
if forecast_line in report_text:
    report_text = report_text.replace(forecast_line, source_lines, 1)
report.write_text(report_text, encoding="utf-8")

# Delete only unmistakably synthetic ML prototypes.  Provider, DB, RAG and
# deterministic agronomic modules are not touched.
deleted: list[str] = []
for path in sorted(ROOT.rglob("*.py")):
    relative = path.relative_to(ROOT)
    if relative.parts[0] not in {"src", "scripts"}:
        continue
    if relative.name.startswith("_apply_scientific_audit_fixes"):
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    synthetic = (
        "synthetic_crop_data" in text
        or "RandomForestClassifier" in text
        or ("RandomForest" in text and "synthetic" in text.casefold())
    )
    prototype_path = (
        path.name == "train_basic_model.py"
        or "ml" in relative.parts
        or "yield" in path.stem.casefold()
        or "crop_recommender" in path.stem.casefold()
    )
    if synthetic and prototype_path:
        path.unlink()
        deleted.append(str(relative))

write(
    "tests/test_scientific_data_quality.py",
    '''
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
        result = calc_et0_balance(
            frame(["operational_past"] * 4 + ["forecast"] * 3)
        )
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
    ''',
)
write(
    "tests/test_no_production_placeholders.py",
    '''
    from __future__ import annotations

    import ast
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[1]


    def test_runtime_contains_no_synthetic_ml_training() -> None:
        forbidden = ("RandomForestClassifier", "synthetic_crop_data", "train_basic_model.py")
        paths = list((ROOT / "src").rglob("*.py")) + list(
            (ROOT / "scripts").rglob("*.py")
        )
        for path in paths:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in forbidden:
                assert marker not in text, f"{marker} in {path.relative_to(ROOT)}"


    def test_critical_runtime_files_do_not_raise_not_implemented() -> None:
        paths = (
            ROOT / "src/bot/main.py",
            ROOT / "src/bot/scheduler.py",
            ROOT / "src/application/agro_report.py",
            ROOT / "src/api/open_meteo.py",
            ROOT / "src/agro/indices.py",
        )
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                    if isinstance(node.exc.func, ast.Name):
                        assert node.exc.func.id != "NotImplementedError", path


    def test_unimplemented_products_are_explicitly_disabled() -> None:
        matrix = (ROOT / "docs/PRODUCTION_CAPABILITIES.md").read_text(encoding="utf-8")
        assert "Прогноз урожайности | ❌ не реализован" in matrix
        assert "Синтетическая ML-модель | ❌ запрещена" in matrix
        assert "SPI | ❌ не рассчитывается" in matrix
    ''',
)

removed_lines = "\n".join(f"- `{item}`" for item in deleted) or "- не обнаружены"
write(
    "docs/PRODUCTION_CAPABILITIES.md",
    f'''
    # Фактические production-возможности

    Наличие исходного модуля или зависимости не означает доступность функции.
    Матрица ниже описывает только реально подключённый Telegram/runtime flow.

    | Функция | Статус | Источник и ограничение |
    |---|---|---|
    | Оперативная погода | ✅ production | Open-Meteo Forecast API |
    | Сезонный прошлый ряд | ⚠️ условно | Historical Weather API, реанализ, не полевая станция |
    | ГДД | ✅ при покрытии | mean-temperature method; Tbase из crop catalogue |
    | ГТК | ⚠️ прошлое окно | прогноз исключён; при нехватке дней значение скрыто |
    | Баланс осадки − ET₀ | ⚠️ диагностический | ET₀ провайдера; пропуски не заменяются нулём |
    | Скрининг заморозка | ⚠️ общий | Tmin воздуха 2 м; не вероятность повреждения растений |
    | Ежедневные отчёты | ✅ production | активное поле, Redis lock/deduplication |
    | RAG-советник | ⚠️ optional | только индексированная литература с источниками |
    | ERA5-Land/CDS в Telegram flow | ❌ не подключён | legacy/experimental код не является функцией продукта |
    | SoilGrids | ❌ не подключён | пользовательский результат не формируется |
    | Спутниковые NDVI/LAI | ❌ не подключены | пользовательский результат не формируется |
    | SPI | ❌ не рассчитывается | короткого прогноза недостаточно |
    | Прогноз урожайности | ❌ не реализован | нет валидированной полевой выборки |
    | Синтетическая ML-модель | ❌ запрещена | не поставляется в runtime |

    Удалённые синтетические prototype-файлы:
    {removed_lines}
    ''',
)
write(
    "docs/END_TO_END_AUDIT_2026-07-10.md",
    f'''
    # Сквозной аудит runtime и расчётов — 2026-07-10

    Проверен путь Telegram/FSM → PostgreSQL/Alembic → Open-Meteo → расчёты →
    отчёт/RAG → scheduler/Redis → Bash/systemd.

    ## Исправленные P0/P1-дефекты

    1. Прошлое и прогноз теперь разделяются по `data_kind`, а не сравнением
       суточного timestamp с текущим UTC-моментом.
    2. Баланс осадки − ET₀ не возвращает фиктивный ноль при отсутствии данных.
       Требуются парные значения, публикуются valid/missing days.
    3. ГТК использует только завершённое прошлое окно; прогнозные осадки исключены.
    4. Frost screening использует только `forecast` и не выдаётся за вероятность
       повреждения культуры.
    5. Удалены синтетические ML prototypes: {', '.join(deleted) if deleted else 'не обнаружены'}.

    ## Научные и эксплуатационные инварианты

    - reanalysis, operational past и forecast не смешиваются;
    - NaN не превращается в ноль;
    - каждый расчёт сообщает единицы, метод, покрытие и пропуски;
    - Historical Weather API называется реанализом, а не наблюдением;
    - недоступная функция явно выключена в capability matrix;
    - schema head, PostgreSQL, Redis, heartbeat и systemd проверяются до readiness.

    ## Не реализовано и не должно имитироваться

    SoilGrids, satellite NDVI/LAI, SPI, прогноз урожайности, локальный FAO-56
    Penman–Monteith и crop/phase-specific probability повреждения заморозком.
    ''',
)

readme = ROOT / "README.md"
text = readme.read_text(encoding="utf-8")
if "docs/PRODUCTION_CAPABILITIES.md" not in text:
    marker = "## 📚 Документация"
    block = (
        "## 🔎 Проверенные возможности и ограничения\n\n"
        "[Матрица production-возможностей](docs/PRODUCTION_CAPABILITIES.md) "
        "явно разделяет работающие, условные и отключённые функции. "
        "Отсутствующая функция не заменяется синтетическими данными.\n\n"
    )
    text = text.replace(marker, block + marker, 1)
readme.write_text(text, encoding="utf-8")

for relative in ("docs/AUDIT_2026-07-10.md", "docs/DEVELOPMENT_PLAN.md"):
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    note = (
        "\n\n## Сквозной scientific/data-quality срез 2026-07-10\n\n"
        "- [x] source-label partition для reanalysis/operational past/forecast;\n"
        "- [x] запрет фиктивного нуля ET₀-баланса при пропусках;\n"
        "- [x] прогноз исключён из ГТК;\n"
        "- [x] frost screening использует только forecast rows;\n"
        "- [x] capability matrix и запрет synthetic ML runtime;\n"
        "- [ ] реальные PostgreSQL/Redis/API integration tests на clean host.\n"
    )
    if "Сквозной scientific/data-quality срез" not in text:
        path.write_text(text.rstrip() + note, encoding="utf-8")

# Remove the intentionally one-off scripts before the workflow commits changes.
for name in (
    "scripts/_apply_scientific_audit_fixes.py",
    "scripts/_apply_scientific_audit_fixes_v2.py",
):
    path = ROOT / name
    if path.exists():
        path.unlink()
