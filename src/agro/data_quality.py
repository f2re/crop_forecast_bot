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
        raise ValueError("Missing weather columns: " + ", ".join(sorted(missing)))

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
