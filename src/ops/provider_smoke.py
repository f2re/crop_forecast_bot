from __future__ import annotations

import argparse
import asyncio
import math
from datetime import date

from src.api.open_meteo import OpenMeteoProvider


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


async def check_provider(
    latitude: float,
    longitude: float,
    season_start: date | None,
) -> int:
    weather = await OpenMeteoProvider().fetch(
        latitude,
        longitude,
        season_start=season_start,
    )
    required = {
        "date",
        "t_max",
        "t_min",
        "t_mean",
        "precip_sum",
        "et0_sum",
        "data_kind",
        "data_source",
    }
    missing = required.difference(weather.daily.columns)
    if missing:
        raise RuntimeError(
            "Open-Meteo contract is incomplete: " + ", ".join(sorted(missing))
        )
    if weather.daily.empty:
        raise RuntimeError("Open-Meteo returned an empty daily series")
    kinds = set(weather.daily["data_kind"].dropna().astype(str))
    if "forecast" not in kinds:
        raise RuntimeError("Open-Meteo response has no forecast rows")
    temperatures = weather.daily[["t_max", "t_min", "t_mean"]]
    if temperatures.notna().sum().sum() == 0:
        raise RuntimeError("Open-Meteo returned no valid temperatures")
    if not math.isfinite(weather.meta.latitude) or not math.isfinite(
        weather.meta.longitude
    ):
        raise RuntimeError("Provider metadata contains non-finite coordinates")

    print("Open-Meteo contract: OK")
    print(f"Source: {weather.meta.source}")
    print(f"Coordinates: {weather.meta.latitude:.4f}, {weather.meta.longitude:.4f}")
    print(f"Timezone: {weather.meta.timezone}")
    print(f"Elevation: {weather.meta.elevation_m:.0f} m")
    print(f"Rows: {len(weather.daily)}")
    print(f"Data kinds: {', '.join(sorted(kinds))}")
    print(
        "Coverage: "
        f"{weather.coverage.actual_start} — {weather.coverage.actual_end}; "
        f"season_complete={weather.coverage.season_coverage_complete}"
    )
    for note in weather.coverage.notes:
        print(f"Note: {note}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a live, read-only Open-Meteo contract smoke check"
    )
    parser.add_argument("--latitude", type=float, default=55.75)
    parser.add_argument("--longitude", type=float, default=37.62)
    parser.add_argument(
        "--season-start",
        help="optional ISO date, for example 2026-04-15",
    )
    args = parser.parse_args()
    return asyncio.run(
        check_provider(
            args.latitude,
            args.longitude,
            _parse_date(args.season_start),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
