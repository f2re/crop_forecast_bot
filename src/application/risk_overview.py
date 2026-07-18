from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.agro.ensemble_risks import calc_ensemble_risks
from src.api.open_meteo_ensemble import OpenMeteoEnsembleProvider
from src.application.ports.risk import RiskForecastProvider
from src.domain.risk import EnsembleForecastMeta, RiskOutlook


@dataclass(frozen=True, slots=True)
class RiskOverview:
    """Application result for one on-demand field risk analysis."""

    outlook: RiskOutlook
    meta: EnsembleForecastMeta
    generated_at: datetime


async def generate_risk_overview(
    latitude: float,
    longitude: float,
    *,
    provider: RiskForecastProvider | None = None,
    as_of_date: date | None = None,
) -> RiskOverview:
    """Fetch ensemble members and calculate the same risks as the scheduler."""

    resolved_provider = provider or OpenMeteoEnsembleProvider()
    forecast = await resolved_provider.fetch(latitude, longitude)
    analysis_date = as_of_date or datetime.now(timezone.utc).date()
    outlook = calc_ensemble_risks(forecast, as_of_date=analysis_date)
    return RiskOverview(
        outlook=outlook,
        meta=forecast.meta,
        generated_at=datetime.now(timezone.utc),
    )
