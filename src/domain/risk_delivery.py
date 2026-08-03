from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from typing import Literal, Protocol, Sequence, cast

from src.domain.risk import RiskEvent, RiskLevel, RiskType

RiskDeliveryMode = Literal["immediate", "digest", "high_only"]

_DELIVERY_MODES = frozenset({"immediate", "digest", "high_only"})
_MODE_LABELS: dict[RiskDeliveryMode, str] = {
    "immediate": "сразу при новом или существенно изменившемся периоде",
    "digest": "один дайджест в сутки при существенном изменении",
    "high_only": "только высокий риск и его существенные изменения",
}
_LEVEL_ORDER: dict[RiskLevel, int] = {"watch": 0, "elevated": 1, "high": 2}
_RISK_ORDER: dict[RiskType, int] = {
    "frost": 0,
    "heat": 1,
    "heavy_rain": 2,
    "strong_wind": 3,
    "convection": 4,
}


class RiskSignalLike(Protocol):
    risk_type: RiskType
    event_date: date
    level: RiskLevel


@dataclass(frozen=True, slots=True)
class RiskEpisodeState:
    """One contiguous period of one hazard used for delivery decisions."""

    risk_type: RiskType
    start_date: date
    end_date: date
    highest_level: RiskLevel


@dataclass(frozen=True, slots=True)
class RiskStateChange:
    """Semantic change for one hazard between delivered and current forecasts."""

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
                episodes.append(_make_episode(risk_type, current))
                current = []
            current.append(signal)
        if current:
            episodes.append(_make_episode(risk_type, current))

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
    if mode != "high_only":
        return episodes
    return tuple(
        episode for episode in episodes if episode.highest_level == "high"
    )


def _prioritized(
    episodes: tuple[RiskEpisodeState, ...],
    *,
    limit: int,
) -> tuple[RiskEpisodeState, ...]:
    prioritized = sorted(
        episodes,
        key=lambda episode: (
            -_LEVEL_ORDER[episode.highest_level],
            episode.start_date,
            _RISK_ORDER[episode.risk_type],
            episode.end_date,
        ),
    )
    selected = prioritized[:limit]
    selected.sort(
        key=lambda episode: (
            episode.start_date,
            -_LEVEL_ORDER[episode.highest_level],
            _RISK_ORDER[episode.risk_type],
            episode.end_date,
        )
    )
    return tuple(selected)


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


def _accepted_priority_state(
    previous: tuple[RiskEpisodeState, ...],
    current_high: tuple[RiskEpisodeState, ...],
    changes: tuple[RiskStateChange, ...],
) -> tuple[RiskEpisodeState, ...]:
    """Advance only the hazard types actually included in a priority message."""

    accepted_types = {change.risk_type for change in changes}
    retained = [
        episode for episode in previous if episode.risk_type not in accepted_types
    ]
    retained.extend(current_high)
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
) -> str:
    signature = f"{_state_signature(previous)}->{_state_signature(current)}"
    digest = sha256(signature.encode("utf-8")).hexdigest()[:20]
    return f"transition:{digest}"


def _changes(
    previous: tuple[RiskEpisodeState, ...],
    current: tuple[RiskEpisodeState, ...],
) -> tuple[RiskStateChange, ...]:
    previous_by_type: dict[RiskType, list[RiskEpisodeState]] = {}
    current_by_type: dict[RiskType, list[RiskEpisodeState]] = {}
    for episode in previous:
        previous_by_type.setdefault(episode.risk_type, []).append(episode)
    for episode in current:
        current_by_type.setdefault(episode.risk_type, []).append(episode)

    changes: list[RiskStateChange] = []
    risk_types = sorted(
        set(previous_by_type) | set(current_by_type),
        key=_RISK_ORDER.__getitem__,
    )
    for risk_type in risk_types:
        old = tuple(previous_by_type.get(risk_type, ()))
        new = tuple(current_by_type.get(risk_type, ()))
        if old != new:
            changes.append(
                RiskStateChange(
                    risk_type=risk_type,
                    previous=old,
                    current=new,
                )
            )
    return tuple(changes)


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
    """Deliver only new or materially changed contiguous hazard periods.

    A forecast run is reduced to semantic episodes: hazard type, start date, end
    date and highest level. Changes in raw ensemble fraction and quantiles do not
    create another Telegram message. Elapsed dates are trimmed from both states,
    so the ordinary passage of a heat period does not look like a forecast change.

    ``previous_state`` is the last successfully accepted delivery baseline from
    PostgreSQL. It may be empty after a forecast explicitly cleared all signals.
    """

    if max_events <= 0:
        raise ValueError("max_events must be positive")

    resolved_mode = validate_risk_delivery_mode(mode)
    current_full_state = _episode_states(
        events,
        as_of_date=local_datetime.date(),
    )
    previous_full_state = _future_state(
        previous_state,
        as_of_date=local_datetime.date(),
    )
    current_state = _prioritized(
        _for_mode(current_full_state, mode=resolved_mode),
        limit=max_events,
    )
    old_state = _prioritized(
        _for_mode(previous_full_state, mode=resolved_mode),
        limit=max_events,
    )
    changes = _changes(old_state, current_state)
    if not changes:
        return RiskDeliveryDecision(
            events=(),
            changes=(),
            current_state=current_full_state,
            deferred=False,
            reason="существенных изменений периода нет",
            dedup_token=None,
        )

    quiet = is_quiet_time(
        local_datetime,
        quiet_hours_start,
        quiet_hours_end,
    )
    current_high_state = _prioritized(
        tuple(
            episode
            for episode in current_full_state
            if episode.highest_level == "high"
        ),
        limit=max_events,
    )
    previous_high_state = _prioritized(
        tuple(
            episode
            for episode in previous_full_state
            if episode.highest_level == "high"
        ),
        limit=max_events,
    )
    high_changes = _changes(previous_high_state, current_high_state)
    high_priority_change = bool(high_changes) and bool(current_high_state)
    priority_bypass = high_priority_change and (
        quiet or resolved_mode == "digest"
    )

    if quiet and not high_priority_change:
        return RiskDeliveryDecision(
            events=(),
            changes=(),
            current_state=previous_full_state,
            deferred=True,
            reason="доставка отложена до окончания тихих часов",
            dedup_token=None,
        )

    if priority_bypass:
        selected_state = current_high_state
        selected_previous_state = previous_high_state
        selected_changes = high_changes
        accepted_state = _accepted_priority_state(
            previous_full_state,
            current_high_state,
            high_changes,
        )
    else:
        selected_state = current_state
        selected_previous_state = old_state
        selected_changes = changes
        accepted_state = current_full_state

    selected_events = _events_for_episodes(events, selected_state)
    if resolved_mode == "digest" and not priority_bypass:
        dedup_token = f"daily:{local_datetime.date().isoformat()}"
    else:
        dedup_token = _transition_token(
            selected_previous_state,
            selected_state,
        )

    return RiskDeliveryDecision(
        events=selected_events,
        changes=selected_changes,
        current_state=accepted_state,
        deferred=False,
        reason=(
            "высокий риск существенно изменился и доставляется без ожидания"
            if priority_bypass
            else "существенное изменение прогноза готово к доставке"
        ),
        dedup_token=dedup_token,
        priority_bypass=priority_bypass,
    )
