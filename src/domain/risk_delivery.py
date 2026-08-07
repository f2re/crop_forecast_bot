from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from typing import Literal, Protocol, Sequence, cast

from src.domain.risk import RiskEvent, RiskLevel, RiskType

RiskDeliveryMode = Literal["immediate", "digest", "high_only"]

_DELIVERY_MODES = frozenset({"immediate", "digest", "high_only"})
_MODE_LABELS: dict[RiskDeliveryMode, str] = {
    "immediate": "только при подтверждённом существенном изменении ближайших суток",
    "digest": "не более одного сообщения в сутки о подтверждённых изменениях",
    "high_only": "только подтверждённый высокий риск ближайших суток и его отмена",
}
_LEVEL_ORDER: dict[RiskLevel, int] = {"watch": 0, "elevated": 1, "high": 2}
_RISK_ORDER: dict[RiskType, int] = {
    "frost": 0,
    "heat": 1,
    "heavy_rain": 2,
    "strong_wind": 3,
    "convection": 4,
}

# A background Telegram message is an interruption, not a full forecast.
# The full ensemble horizon remains available in history and /risks, while push
# delivery only acts on the next 72 hours. This prevents a volatile day-10/16
# boundary from looking like an operational promise to the farmer.
_AUTOMATIC_LEAD_DAYS = 3
_URGENT_HIGH_LEAD_DAYS = 1
_MATERIAL_DATE_SHIFT_DAYS = 2
_BOUNDARY_DECISION_HORIZON_DAYS = 3


class RiskSignalLike(Protocol):
    risk_type: RiskType
    event_date: date
    level: RiskLevel


@dataclass(frozen=True, slots=True)
class RiskEpisodeState:
    """One contiguous serious period used as the last-notified baseline."""

    risk_type: RiskType
    start_date: date
    end_date: date
    highest_level: RiskLevel


@dataclass(frozen=True, slots=True)
class RiskStateChange:
    """Qualitative change between the last notification and current forecast."""

    risk_type: RiskType
    previous: tuple[RiskEpisodeState, ...]
    current: tuple[RiskEpisodeState, ...]


@dataclass(frozen=True, slots=True)
class RiskDeliveryDecision:
    events: tuple[RiskEvent, ...]
    changes: tuple[RiskStateChange, ...]
    current_state: tuple[RiskEpisodeState, ...]
    deferred: bool
    reason: str
    dedup_token: str | None
    daily_quota_token: str | None = None
    priority_bypass: bool = False


def validate_risk_delivery_mode(value: str) -> RiskDeliveryMode:
    if value not in _DELIVERY_MODES:
        raise ValueError("Неизвестный режим доставки погодных рисков.")
    return cast(RiskDeliveryMode, value)


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


def _make_episode(
    risk_type: RiskType,
    signals: Sequence[RiskSignalLike],
) -> RiskEpisodeState:
    return RiskEpisodeState(
        risk_type=risk_type,
        start_date=signals[0].event_date,
        end_date=signals[-1].event_date,
        highest_level=max(
            (signal.level for signal in signals),
            key=_LEVEL_ORDER.__getitem__,
        ),
    )


def _episode_is_actionable(
    episode: RiskEpisodeState,
    *,
    as_of_date: date,
) -> bool:
    if episode.highest_level == "watch":
        return False
    lead_days = max(0, (episode.start_date - as_of_date).days)
    return lead_days <= _AUTOMATIC_LEAD_DAYS


def _episode_states(
    signals: Sequence[RiskSignalLike],
    *,
    as_of_date: date,
) -> tuple[RiskEpisodeState, ...]:
    by_type: dict[RiskType, list[RiskSignalLike]] = {}
    for signal in signals:
        if signal.event_date < as_of_date:
            continue
        by_type.setdefault(signal.risk_type, []).append(signal)

    episodes: list[RiskEpisodeState] = []
    for risk_type, typed_signals in by_type.items():
        ordered = sorted(typed_signals, key=lambda item: item.event_date)
        current: list[RiskSignalLike] = []
        for signal in ordered:
            if current and (signal.event_date - current[-1].event_date).days > 1:
                episode = _make_episode(risk_type, current)
                if _episode_is_actionable(episode, as_of_date=as_of_date):
                    episodes.append(episode)
                current = []
            current.append(signal)
        if current:
            episode = _make_episode(risk_type, current)
            if _episode_is_actionable(episode, as_of_date=as_of_date):
                episodes.append(episode)

    episodes.sort(
        key=lambda episode: (
            episode.start_date,
            -_LEVEL_ORDER[episode.highest_level],
            _RISK_ORDER[episode.risk_type],
            episode.end_date,
        )
    )
    return tuple(episodes)


def _future_state(
    episodes: Sequence[RiskEpisodeState],
    *,
    as_of_date: date,
) -> tuple[RiskEpisodeState, ...]:
    normalized: list[RiskEpisodeState] = []
    for episode in episodes:
        if episode.end_date < as_of_date:
            continue
        normalized.append(
            RiskEpisodeState(
                risk_type=episode.risk_type,
                start_date=max(episode.start_date, as_of_date),
                end_date=episode.end_date,
                highest_level=episode.highest_level,
            )
        )
    normalized.sort(
        key=lambda episode: (
            episode.start_date,
            -_LEVEL_ORDER[episode.highest_level],
            _RISK_ORDER[episode.risk_type],
            episode.end_date,
        )
    )
    return tuple(normalized)


def _for_mode(
    episodes: tuple[RiskEpisodeState, ...],
    *,
    mode: RiskDeliveryMode,
) -> tuple[RiskEpisodeState, ...]:
    serious = tuple(
        episode for episode in episodes if episode.highest_level != "watch"
    )
    if mode != "high_only":
        return serious
    return tuple(
        episode for episode in serious if episode.highest_level == "high"
    )


def _canonical(
    episodes: Sequence[RiskEpisodeState],
) -> tuple[RiskEpisodeState, ...]:
    return tuple(
        sorted(
            episodes,
            key=lambda episode: (
                _RISK_ORDER[episode.risk_type],
                episode.start_date,
                episode.end_date,
                _LEVEL_ORDER[episode.highest_level],
            ),
        )
    )


def _state_for_changes(
    episodes: Sequence[RiskEpisodeState],
    changes: Sequence[RiskStateChange],
) -> tuple[RiskEpisodeState, ...]:
    changed_types = {change.risk_type for change in changes}
    return _canonical(
        episode for episode in episodes if episode.risk_type in changed_types
    )


def _accepted_changed_state(
    previous: tuple[RiskEpisodeState, ...],
    current: tuple[RiskEpisodeState, ...],
    changes: tuple[RiskStateChange, ...],
) -> tuple[RiskEpisodeState, ...]:
    accepted_types = {change.risk_type for change in changes}
    retained = [
        episode for episode in previous if episode.risk_type not in accepted_types
    ]
    retained.extend(
        episode for episode in current if episode.risk_type in accepted_types
    )
    return _canonical(retained)


def _state_signature(episodes: tuple[RiskEpisodeState, ...]) -> str:
    return "|".join(
        f"{episode.risk_type}:{episode.start_date.isoformat()}:"
        f"{episode.end_date.isoformat()}:{episode.highest_level}"
        for episode in _canonical(episodes)
    )


def _transition_token(
    previous: tuple[RiskEpisodeState, ...],
    current: tuple[RiskEpisodeState, ...],
    *,
    urgent: bool,
) -> str:
    signature = f"{_state_signature(previous)}->{_state_signature(current)}"
    digest = sha256(signature.encode("utf-8")).hexdigest()[:20]
    prefix = "urgent-transition" if urgent else "confirmable-transition"
    return f"{prefix}:{digest}"


def _urgency_band(value: date, *, as_of_date: date) -> int:
    lead_days = max(0, (value - as_of_date).days)
    if lead_days <= 1:
        return 0
    if lead_days <= _AUTOMATIC_LEAD_DAYS:
        return 1
    return 2


def _within_boundary_horizon(value: date, *, as_of_date: date) -> bool:
    return (value - as_of_date).days <= _BOUNDARY_DECISION_HORIZON_DAYS


def _pair_is_material(
    previous: RiskEpisodeState,
    current: RiskEpisodeState,
    *,
    as_of_date: date,
) -> bool:
    if previous.highest_level != current.highest_level:
        return True

    start_shift = abs((current.start_date - previous.start_date).days)
    if start_shift >= _MATERIAL_DATE_SHIFT_DAYS:
        return True
    if _urgency_band(
        previous.start_date,
        as_of_date=as_of_date,
    ) != _urgency_band(current.start_date, as_of_date=as_of_date):
        return True

    # The end of a long period is not an operationally stable quantity. For
    # example, 7–22 -> 7–13 August on 7 August must not interrupt the user: both
    # possible endings are outside the decision window. It becomes relevant only
    # when at least one ending is within the next 72 hours.
    end_shift = abs((current.end_date - previous.end_date).days)
    if end_shift < _MATERIAL_DATE_SHIFT_DAYS:
        return False
    return _within_boundary_horizon(
        previous.end_date,
        as_of_date=as_of_date,
    ) or _within_boundary_horizon(
        current.end_date,
        as_of_date=as_of_date,
    )


def _episode_distance(
    previous: RiskEpisodeState,
    current: RiskEpisodeState,
) -> tuple[int, int, int]:
    overlap = not (
        previous.end_date < current.start_date
        or current.end_date < previous.start_date
    )
    return (
        0 if overlap else 1,
        abs((current.start_date - previous.start_date).days),
        abs((current.end_date - previous.end_date).days),
    )


def _match_episodes(
    previous: tuple[RiskEpisodeState, ...],
    current: tuple[RiskEpisodeState, ...],
) -> tuple[
    tuple[tuple[RiskEpisodeState, RiskEpisodeState], ...],
    tuple[RiskEpisodeState, ...],
    tuple[RiskEpisodeState, ...],
]:
    remaining = list(current)
    pairs: list[tuple[RiskEpisodeState, RiskEpisodeState]] = []
    unmatched_previous: list[RiskEpisodeState] = []
    for old in previous:
        if not remaining:
            unmatched_previous.append(old)
            continue
        index = min(
            range(len(remaining)),
            key=lambda item: _episode_distance(old, remaining[item]),
        )
        candidate = remaining[index]
        if _episode_distance(old, candidate)[0] > 0:
            unmatched_previous.append(old)
            continue
        pairs.append((old, remaining.pop(index)))
    return tuple(pairs), tuple(unmatched_previous), tuple(remaining)


def _material_change_plan(
    previous: tuple[RiskEpisodeState, ...],
    current: tuple[RiskEpisodeState, ...],
    *,
    as_of_date: date,
) -> tuple[tuple[RiskStateChange, ...], tuple[RiskEpisodeState, ...]]:
    previous_by_type: dict[RiskType, tuple[RiskEpisodeState, ...]] = {}
    current_by_type: dict[RiskType, tuple[RiskEpisodeState, ...]] = {}
    for risk_type in _RISK_ORDER:
        previous_by_type[risk_type] = tuple(
            episode for episode in previous if episode.risk_type == risk_type
        )
        current_by_type[risk_type] = tuple(
            episode for episode in current if episode.risk_type == risk_type
        )

    changes: list[RiskStateChange] = []
    candidate_state: list[RiskEpisodeState] = []
    for risk_type in _RISK_ORDER:
        old = previous_by_type[risk_type]
        new = current_by_type[risk_type]
        if not old and not new:
            continue
        if not old:
            changes.append(RiskStateChange(risk_type, (), new))
            candidate_state.extend(new)
            continue
        if not new:
            changes.append(RiskStateChange(risk_type, old, ()))
            continue

        pairs, removed, added = _match_episodes(old, new)
        material = bool(removed or added)
        if not material:
            material = any(
                _pair_is_material(
                    previous_episode,
                    current_episode,
                    as_of_date=as_of_date,
                )
                for previous_episode, current_episode in pairs
            )
        if material:
            changes.append(RiskStateChange(risk_type, old, new))
            candidate_state.extend(new)
        else:
            # Keep the last-notified baseline. Far-horizon boundary noise never
            # becomes a stream of messages; the boundary is reconsidered only
            # after it enters the 72-hour decision window.
            candidate_state.extend(old)

    return tuple(changes), _canonical(candidate_state)


def _events_for_episodes(
    events: tuple[RiskEvent, ...],
    episodes: tuple[RiskEpisodeState, ...],
) -> tuple[RiskEvent, ...]:
    selected: list[RiskEvent] = []
    for event in events:
        for episode in episodes:
            if (
                event.risk_type == episode.risk_type
                and episode.start_date <= event.event_date <= episode.end_date
            ):
                selected.append(event)
                break
    selected.sort(
        key=lambda event: (
            event.event_date,
            -_LEVEL_ORDER[event.level],
            _RISK_ORDER[event.risk_type],
        )
    )
    return tuple(selected)


def _urgent_high_change(
    change: RiskStateChange,
    events: tuple[RiskEvent, ...],
    *,
    as_of_date: date,
) -> bool:
    if not change.current:
        return False
    previous_high = any(
        episode.highest_level == "high" for episode in change.previous
    )
    current_high = any(
        episode.highest_level == "high" for episode in change.current
    )
    if not current_high:
        return False
    if previous_high and all(
        episode.highest_level == "high" for episode in change.previous
    ):
        return False
    return any(
        event.risk_type == change.risk_type
        and event.level == "high"
        and 0 <= (event.event_date - as_of_date).days <= _URGENT_HIGH_LEAD_DAYS
        for event in events
    )


def plan_risk_delivery(
    events: tuple[RiskEvent, ...],
    *,
    mode: str,
    local_datetime: datetime,
    previous_state: Sequence[RiskEpisodeState] = (),
    quiet_hours_start: int | None = None,
    quiet_hours_end: int | None = None,
    max_events: int = 5,
) -> RiskDeliveryDecision:
    """Deliver only close, qualitative and actionable risk transitions.

    The full ensemble horizon is still calculated and persisted, but background
    Telegram delivery uses a conservative 72-hour decision window. Raw values,
    ensemble fractions, weak signals and distant period endings do not create
    repeated notifications.
    """

    if max_events <= 0:
        raise ValueError("max_events must be positive")
    if local_datetime.tzinfo is None or local_datetime.utcoffset() is None:
        raise ValueError("local_datetime must be timezone-aware")

    resolved_mode = validate_risk_delivery_mode(mode)
    as_of_date = local_datetime.date()
    current_all = _for_mode(
        _episode_states(events, as_of_date=as_of_date),
        mode=resolved_mode,
    )
    old_state = _for_mode(
        _future_state(previous_state, as_of_date=as_of_date),
        mode=resolved_mode,
    )
    all_changes, candidate_state = _material_change_plan(
        old_state,
        current_all,
        as_of_date=as_of_date,
    )
    if not all_changes:
        return RiskDeliveryDecision(
            events=(),
            changes=(),
            current_state=candidate_state,
            deferred=False,
            reason="существенных подтверждаемых изменений ближайших суток нет",
            dedup_token=None,
        )

    urgent_changes = tuple(
        change
        for change in all_changes
        if _urgent_high_change(change, events, as_of_date=as_of_date)
    )
    quiet = is_quiet_time(
        local_datetime,
        quiet_hours_start,
        quiet_hours_end,
    )
    priority_bypass = bool(urgent_changes) and (
        quiet or resolved_mode == "digest"
    )

    if quiet and not urgent_changes:
        return RiskDeliveryDecision(
            events=(),
            changes=(),
            current_state=old_state,
            deferred=True,
            reason="доставка отложена до окончания тихих часов",
            dedup_token=None,
        )

    selected_changes = (
        urgent_changes[:max_events]
        if priority_bypass
        else all_changes[:max_events]
    )
    selected_state = _state_for_changes(candidate_state, selected_changes)
    selected_previous_state = _state_for_changes(old_state, selected_changes)
    accepted_state = _accepted_changed_state(
        old_state,
        candidate_state,
        selected_changes,
    )
    selected_events = _events_for_episodes(events, selected_state)
    urgent_types = {change.risk_type for change in urgent_changes}
    urgent_selected = any(
        change.risk_type in urgent_types for change in selected_changes
    )
    dedup_token = _transition_token(
        selected_previous_state,
        selected_state,
        urgent=urgent_selected,
    )
    daily_quota_token = (
        f"daily:{as_of_date.isoformat()}"
        if resolved_mode == "digest" and not priority_bypass
        else None
    )

    return RiskDeliveryDecision(
        events=selected_events,
        changes=selected_changes,
        current_state=accepted_state,
        deferred=False,
        reason=(
            "ближайший высокий риск требует сообщения без ожидания"
            if urgent_selected
            else "существенное изменение ближайших суток ожидает подтверждения"
        ),
        dedup_token=dedup_token,
        daily_quota_token=daily_quota_token,
        priority_bypass=priority_bypass,
    )
