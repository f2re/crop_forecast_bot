from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.risk_history import (
    RiskRunSnapshot,
    RiskSignalSnapshot,
    list_recent_risk_runs,
)
from src.domain.risk_trend import RiskTrend, classify_risk_trend


@dataclass(frozen=True, slots=True)
class RiskHistoryItem:
    trend: RiskTrend
    current: RiskSignalSnapshot | None
    previous: RiskSignalSnapshot | None

    @property
    def signal(self) -> RiskSignalSnapshot:
        signal = self.current or self.previous
        if signal is None:  # pragma: no cover - constructor invariant
            raise RuntimeError("Risk history item has no signal")
        return signal


@dataclass(frozen=True, slots=True)
class RiskHistory:
    available: bool
    status: str
    current_run: RiskRunSnapshot | None = None
    previous_run: RiskRunSnapshot | None = None
    items: tuple[RiskHistoryItem, ...] = ()


_TREND_ORDER: dict[RiskTrend, int] = {
    "strengthening": 0,
    "new": 1,
    "weakening": 2,
    "stable": 3,
    "cleared": 4,
}
_LEVEL_ORDER = {"high": 0, "elevated": 1, "watch": 2}


def build_risk_history(runs: tuple[RiskRunSnapshot, ...]) -> RiskHistory:
    if not runs:
        return RiskHistory(
            available=False,
            status="журнал ещё пуст; дождитесь фонового анализа рисков",
        )

    current_run = runs[0]
    previous_run = runs[1] if len(runs) > 1 else None
    if previous_run is not None and previous_run.model != current_run.model:
        previous_run = None

    current_by_key = {
        (signal.risk_type, signal.event_date): signal
        for signal in current_run.signals
    }
    previous_by_key = (
        {
            (signal.risk_type, signal.event_date): signal
            for signal in previous_run.signals
        }
        if previous_run is not None
        else {}
    )

    items: list[RiskHistoryItem] = []
    for key, current in current_by_key.items():
        previous = previous_by_key.get(key)
        items.append(
            RiskHistoryItem(
                trend=classify_risk_trend(
                    current_fraction=current.member_fraction,
                    current_level=current.level,
                    previous_fraction=(
                        None if previous is None else previous.member_fraction
                    ),
                    previous_level=None if previous is None else previous.level,
                ),
                current=current,
                previous=previous,
            )
        )

    for key, previous in previous_by_key.items():
        if key in current_by_key:
            continue
        if previous.event_date < current_run.analysis_date:
            continue
        items.append(
            RiskHistoryItem(
                trend="cleared",
                current=None,
                previous=previous,
            )
        )

    items.sort(
        key=lambda item: (
            _TREND_ORDER[item.trend],
            _LEVEL_ORDER[item.signal.level],
            item.signal.event_date,
            item.signal.risk_type,
        )
    )
    return RiskHistory(
        available=True,
        status=current_run.status,
        current_run=current_run,
        previous_run=previous_run,
        items=tuple(items),
    )


async def load_risk_history(
    session: AsyncSession,
    *,
    field_id: int,
) -> RiskHistory:
    runs = await list_recent_risk_runs(session, field_id=field_id, limit=2)
    return build_risk_history(runs)
