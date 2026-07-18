from __future__ import annotations

from typing import Literal

from src.domain.risk import RiskLevel

RiskTrend = Literal["new", "strengthening", "stable", "weakening", "cleared"]

_LEVEL_RANK: dict[RiskLevel, int] = {"watch": 1, "elevated": 2, "high": 3}
DEFAULT_SIGNIFICANT_FRACTION_DELTA = 0.10


def classify_risk_trend(
    *,
    current_fraction: float,
    current_level: RiskLevel,
    previous_fraction: float | None,
    previous_level: RiskLevel | None,
    significant_fraction_delta: float = DEFAULT_SIGNIFICANT_FRACTION_DELTA,
) -> RiskTrend:
    """Compare two model signals without treating the result as probability.

    A level change always wins. Within the same level, a change of at least
    ``significant_fraction_delta`` is considered strengthening or weakening.
    Smaller changes are stable.
    """

    if not 0 <= current_fraction <= 1:
        raise ValueError("current_fraction must be between 0 and 1")
    if previous_fraction is not None and not 0 <= previous_fraction <= 1:
        raise ValueError("previous_fraction must be between 0 and 1")
    if significant_fraction_delta <= 0 or significant_fraction_delta > 1:
        raise ValueError("significant_fraction_delta must be in (0, 1]")

    if previous_fraction is None or previous_level is None:
        return "new"

    current_rank = _LEVEL_RANK[current_level]
    previous_rank = _LEVEL_RANK[previous_level]
    if current_rank > previous_rank:
        return "strengthening"
    if current_rank < previous_rank:
        return "weakening"

    delta = current_fraction - previous_fraction
    if delta >= significant_fraction_delta:
        return "strengthening"
    if delta <= -significant_fraction_delta:
        return "weakening"
    return "stable"
