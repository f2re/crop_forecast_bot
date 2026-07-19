from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Literal

from src.domain.risk import RiskEvent

RiskDeliveryMode = Literal["immediate", "digest", "high_only"]

_DELIVERY_MODES = frozenset({"immediate", "digest", "high_only"})
_MODE_LABELS: dict[RiskDeliveryMode, str] = {
    "immediate": "сразу при новом сигнале",
    "digest": "один дайджест в сутки",
    "high_only": "только высокий риск",
}


@dataclass(frozen=True, slots=True)
class RiskDeliveryDecision:
    events: tuple[RiskEvent, ...]
    deferred: bool
    reason: str
    dedup_token: str | None
    priority_bypass: bool = False


def validate_risk_delivery_mode(value: str) -> RiskDeliveryMode:
    if value not in _DELIVERY_MODES:
        raise ValueError("Неизвестный режим доставки погодных рисков.")
    return value  # type: ignore[return-value]


def risk_delivery_mode_label(value: str) -> str:
    return _MODE_LABELS[validate_risk_delivery_mode(value)]


def validate_quiet_hours(
    start_hour: int | None,
    end_hour: int | None,
) -> tuple[int | None, int | None]:
    if start_hour is None and end_hour is None:
        return None, None
    if start_hour is None or end_hour is None:
        raise ValueError("Начало и конец тихих часов задаются вместе.")
    if not 0 <= start_hour <= 23 or not 0 <= end_hour <= 23:
        raise ValueError("Часы должны быть в диапазоне от 0 до 23.")
    if start_hour == end_hour:
        raise ValueError("Начало и конец тихих часов не должны совпадать.")
    return start_hour, end_hour


def quiet_hours_label(start_hour: int | None, end_hour: int | None) -> str:
    start_hour, end_hour = validate_quiet_hours(start_hour, end_hour)
    if start_hour is None or end_hour is None:
        return "выключены"
    return f"{start_hour:02d}:00–{end_hour:02d}:00"


def is_quiet_time(
    local_datetime: datetime,
    start_hour: int | None,
    end_hour: int | None,
) -> bool:
    start_hour, end_hour = validate_quiet_hours(start_hour, end_hour)
    if start_hour is None or end_hour is None:
        return False
    hour = local_datetime.hour
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _state_token(events: tuple[RiskEvent, ...]) -> str:
    signature = "|".join(
        f"{event.risk_type}:{event.event_date.isoformat()}:{event.level}"
        for event in events
    )
    digest = sha256(signature.encode("utf-8")).hexdigest()[:16]
    return f"state:{digest}"


def plan_risk_delivery(
    events: tuple[RiskEvent, ...],
    *,
    mode: str,
    local_datetime: datetime,
    quiet_hours_start: int | None = None,
    quiet_hours_end: int | None = None,
    max_events: int = 5,
) -> RiskDeliveryDecision:
    """Choose a compact delivery without pretending to calibrate event probability.

    Quiet hours defer watch/elevated signals. A high signal bypasses quiet hours.
    Daily digest mode is normally sent once per local date; a high signal bypasses
    that daily cadence using a state-based deduplication token.
    """
    if max_events <= 0:
        raise ValueError("max_events must be positive")

    resolved_mode = validate_risk_delivery_mode(mode)
    valid_events = tuple(
        event
        for event in events
        if event.event_date >= local_datetime.date()
    )
    if resolved_mode == "high_only":
        candidates = tuple(event for event in valid_events if event.level == "high")
    else:
        candidates = valid_events
    candidates = candidates[:max_events]

    if not candidates:
        return RiskDeliveryDecision(
            events=(),
            deferred=False,
            reason="нет событий для выбранного режима",
            dedup_token=None,
        )

    high_events = tuple(event for event in candidates if event.level == "high")
    quiet = is_quiet_time(
        local_datetime,
        quiet_hours_start,
        quiet_hours_end,
    )
    priority_bypass = bool(high_events) and (quiet or resolved_mode == "digest")

    if quiet and not high_events:
        return RiskDeliveryDecision(
            events=(),
            deferred=True,
            reason="доставка отложена до окончания тихих часов",
            dedup_token=None,
        )

    selected = high_events if quiet and high_events else candidates
    if resolved_mode == "digest" and not priority_bypass:
        dedup_token = f"daily:{local_datetime.date().isoformat()}"
    else:
        dedup_token = _state_token(selected)

    return RiskDeliveryDecision(
        events=selected,
        deferred=False,
        reason=(
            "высокий риск доставляется без ожидания дайджеста"
            if priority_bypass
            else "события готовы к доставке"
        ),
        dedup_token=dedup_token,
        priority_bypass=priority_bypass,
    )
