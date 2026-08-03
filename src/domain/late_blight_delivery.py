from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from typing import Any, Literal, Sequence, cast

from src.domain.late_blight import LateBlightPeriod
from src.domain.risk_delivery import (
    RiskDeliveryMode,
    is_quiet_time,
    validate_risk_delivery_mode,
)

LATE_BLIGHT_MODEL_KEY = "potato_late_blight_hutton_v1"
LATE_BLIGHT_STATE_VERSION = 1

InoculumContext = Literal[
    "unknown",
    "regional_alert_confirmed",
    "nearby_outbreak_confirmed",
    "field_source_suspected",
    "field_symptoms_observed",
]
LateBlightChangeKind = Literal[
    "new",
    "restored",
    "withdrawn",
    "starts_earlier",
    "starts_later",
    "extended",
    "shortened",
    "shifted",
    "split",
    "merged",
    "updated",
    "context_confirmed",
    "context_cleared",
    "context_changed",
]

_INOCULUM_CONTEXTS = frozenset(
    {
        "unknown",
        "regional_alert_confirmed",
        "nearby_outbreak_confirmed",
        "field_source_suspected",
        "field_symptoms_observed",
    }
)


@dataclass(frozen=True, slots=True)
class LateBlightEpisodeState:
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class LateBlightDeliveryState:
    active_periods: tuple[LateBlightEpisodeState, ...]
    withdrawn_periods: tuple[LateBlightEpisodeState, ...]
    inoculum_context: InoculumContext


@dataclass(frozen=True, slots=True)
class LateBlightStateChange:
    kind: LateBlightChangeKind
    previous: tuple[LateBlightEpisodeState, ...]
    current: tuple[LateBlightEpisodeState, ...]
    previous_context: InoculumContext
    current_context: InoculumContext


@dataclass(frozen=True, slots=True)
class LateBlightDeliveryDecision:
    current_state: LateBlightDeliveryState
    change: LateBlightStateChange | None
    deferred: bool
    silent_advance: bool
    reason: str
    dedup_token: str | None
    daily_quota_token: str | None
    priority_bypass: bool


def validate_inoculum_context(value: str) -> InoculumContext:
    if value not in _INOCULUM_CONTEXTS:
        raise ValueError("Неизвестный контекст источника фитофтороза.")
    return cast(InoculumContext, value)


def empty_late_blight_delivery_state(
    *,
    inoculum_context: str = "unknown",
) -> LateBlightDeliveryState:
    return LateBlightDeliveryState(
        active_periods=(),
        withdrawn_periods=(),
        inoculum_context=validate_inoculum_context(inoculum_context),
    )


def _canonical(
    periods: Sequence[LateBlightEpisodeState],
) -> tuple[LateBlightEpisodeState, ...]:
    unique = {
        (period.start_date, period.end_date): period
        for period in periods
        if period.end_date >= period.start_date
    }
    return tuple(
        unique[key]
        for key in sorted(unique, key=lambda item: (item[0], item[1]))
    )


def _future_state(
    periods: Sequence[LateBlightEpisodeState],
    *,
    as_of_date: date,
) -> tuple[LateBlightEpisodeState, ...]:
    return _canonical(
        LateBlightEpisodeState(
            start_date=max(period.start_date, as_of_date),
            end_date=period.end_date,
        )
        for period in periods
        if period.end_date >= as_of_date
    )


def episodes_from_outlook(
    periods: Sequence[LateBlightPeriod],
    *,
    as_of_date: date,
) -> tuple[LateBlightEpisodeState, ...]:
    return _future_state(
        tuple(
            LateBlightEpisodeState(
                start_date=period.start_date,
                end_date=period.end_date,
            )
            for period in periods
        ),
        as_of_date=as_of_date,
    )


def _overlaps(
    left: Sequence[LateBlightEpisodeState],
    right: Sequence[LateBlightEpisodeState],
) -> bool:
    return any(
        first.start_date <= second.end_date
        and second.start_date <= first.end_date
        for first in left
        for second in right
    )


def _period_change_kind(
    previous: tuple[LateBlightEpisodeState, ...],
    current: tuple[LateBlightEpisodeState, ...],
    withdrawn: tuple[LateBlightEpisodeState, ...],
) -> LateBlightChangeKind | None:
    if previous == current:
        return None
    if not previous and current:
        if withdrawn and _overlaps(withdrawn, current):
            return "restored"
        return "new"
    if previous and not current:
        return "withdrawn"
    if len(previous) == 1 and len(current) > 1:
        return "split"
    if len(previous) > 1 and len(current) == 1:
        return "merged"
    if len(previous) == 1 and len(current) == 1:
        old = previous[0]
        new = current[0]
        if old.start_date == new.start_date:
            if new.end_date > old.end_date:
                return "extended"
            if new.end_date < old.end_date:
                return "shortened"
        if old.end_date == new.end_date:
            if new.start_date < old.start_date:
                return "starts_earlier"
            if new.start_date > old.start_date:
                return "starts_later"
        if (
            old.start_date != new.start_date
            and old.end_date != new.end_date
        ):
            return "shifted"
    return "updated"


def _context_change_kind(
    previous: InoculumContext,
    current: InoculumContext,
) -> LateBlightChangeKind | None:
    if previous == current:
        return None
    if previous == "unknown" and current != "unknown":
        return "context_confirmed"
    if previous != "unknown" and current == "unknown":
        return "context_cleared"
    return "context_changed"


def _signature(state: LateBlightDeliveryState) -> str:
    active = ",".join(
        f"{period.start_date.isoformat()}:{period.end_date.isoformat()}"
        for period in _canonical(state.active_periods)
    )
    withdrawn = ",".join(
        f"{period.start_date.isoformat()}:{period.end_date.isoformat()}"
        for period in _canonical(state.withdrawn_periods)
    )
    return f"active={active}|withdrawn={withdrawn}|context={state.inoculum_context}"


def _transition_token(
    previous: LateBlightDeliveryState,
    current: LateBlightDeliveryState,
) -> str:
    raw = f"{_signature(previous)}->{_signature(current)}"
    return "transition:" + sha256(raw.encode("utf-8")).hexdigest()[:20]


def plan_late_blight_delivery(
    periods: Sequence[LateBlightPeriod],
    *,
    previous_state: LateBlightDeliveryState | None,
    inoculum_context: str,
    mode: str,
    local_datetime: datetime,
    quiet_hours_start: int | None,
    quiet_hours_end: int | None,
) -> LateBlightDeliveryDecision:
    if local_datetime.tzinfo is None or local_datetime.utcoffset() is None:
        raise ValueError("local_datetime must be timezone-aware")

    resolved_mode: RiskDeliveryMode = validate_risk_delivery_mode(mode)
    resolved_context = validate_inoculum_context(inoculum_context)
    previous = previous_state or empty_late_blight_delivery_state()
    previous_active = _future_state(
        previous.active_periods,
        as_of_date=local_datetime.date(),
    )
    current_active = episodes_from_outlook(
        periods,
        as_of_date=local_datetime.date(),
    )

    if current_active:
        next_withdrawn: tuple[LateBlightEpisodeState, ...] = ()
    elif previous_active:
        next_withdrawn = previous_active
    else:
        next_withdrawn = _canonical(previous.withdrawn_periods)

    current_state = LateBlightDeliveryState(
        active_periods=current_active,
        withdrawn_periods=next_withdrawn,
        inoculum_context=resolved_context,
    )

    change_kind = _period_change_kind(
        previous_active,
        current_active,
        _canonical(previous.withdrawn_periods),
    )
    if change_kind is None and current_active:
        change_kind = _context_change_kind(
            previous.inoculum_context,
            resolved_context,
        )

    change = (
        None
        if change_kind is None
        else LateBlightStateChange(
            kind=change_kind,
            previous=previous_active,
            current=current_active,
            previous_context=previous.inoculum_context,
            current_context=resolved_context,
        )
    )

    confirmed_context = (
        previous.inoculum_context != "unknown" or resolved_context != "unknown"
    )
    priority_bypass = bool(
        confirmed_context and (previous_active or current_active)
    )

    if change is None:
        return LateBlightDeliveryDecision(
            current_state=current_state,
            change=None,
            deferred=False,
            silent_advance=True,
            reason="смысловое состояние не изменилось",
            dedup_token=None,
            daily_quota_token=None,
            priority_bypass=False,
        )

    if resolved_mode == "high_only" and not priority_bypass:
        return LateBlightDeliveryDecision(
            current_state=current_state,
            change=None,
            deferred=False,
            silent_advance=True,
            reason="режим только высокого риска требует подтверждённого источника",
            dedup_token=None,
            daily_quota_token=None,
            priority_bypass=False,
        )

    if (
        not priority_bypass
        and is_quiet_time(
            local_datetime,
            quiet_hours_start,
            quiet_hours_end,
        )
    ):
        return LateBlightDeliveryDecision(
            current_state=current_state,
            change=change,
            deferred=True,
            silent_advance=False,
            reason="действуют тихие часы",
            dedup_token=None,
            daily_quota_token=None,
            priority_bypass=False,
        )

    daily_token = (
        local_datetime.date().isoformat()
        if resolved_mode == "digest" and not priority_bypass
        else None
    )
    return LateBlightDeliveryDecision(
        current_state=current_state,
        change=change,
        deferred=False,
        silent_advance=False,
        reason="существенное изменение погодного окна",
        dedup_token=_transition_token(previous, current_state),
        daily_quota_token=daily_token,
        priority_bypass=priority_bypass,
    )


def serialize_late_blight_delivery_state(
    state: LateBlightDeliveryState,
) -> str:
    payload = {
        "active_periods": [
            {
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
            }
            for period in _canonical(state.active_periods)
        ],
        "withdrawn_periods": [
            {
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
            }
            for period in _canonical(state.withdrawn_periods)
        ],
        "inoculum_context": state.inoculum_context,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_period(item: Any) -> LateBlightEpisodeState:
    if not isinstance(item, dict):
        raise ValueError("late-blight state period is not an object")
    try:
        start_date = date.fromisoformat(str(item["start_date"]))
        end_date = date.fromisoformat(str(item["end_date"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid date in late-blight delivery state") from exc
    if end_date < start_date:
        raise ValueError("late-blight delivery period ends before it starts")
    return LateBlightEpisodeState(start_date=start_date, end_date=end_date)


def deserialize_late_blight_delivery_state(
    raw_value: str,
) -> LateBlightDeliveryState:
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError("late-blight delivery state is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("late-blight delivery state root is not an object")
    active = payload.get("active_periods")
    withdrawn = payload.get("withdrawn_periods")
    if not isinstance(active, list) or not isinstance(withdrawn, list):
        raise ValueError("late-blight delivery state period lists are invalid")
    return LateBlightDeliveryState(
        active_periods=_canonical(tuple(_decode_period(item) for item in active)),
        withdrawn_periods=_canonical(
            tuple(_decode_period(item) for item in withdrawn)
        ),
        inoculum_context=validate_inoculum_context(
            str(payload.get("inoculum_context") or "unknown")
        ),
    )
