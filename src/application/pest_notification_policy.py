from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Literal

from src.domain.pests import PestNotification, PestOutlook

PestAdvanceChange = Literal[
    "initial",
    "earlier",
    "later",
    "withdrawn",
    "restored",
]
PestAdvanceStateKind = Literal["legacy", "expected", "withdrawn"]


@dataclass(frozen=True, slots=True)
class SemanticPestNotification(PestNotification):
    """Pest reminder carrying a semantic forecast-window transition."""

    state_key: str
    change: PestAdvanceChange | None = None
    previous_expected_date: date | None = None


@dataclass(frozen=True, slots=True)
class _AdvanceState:
    kind: PestAdvanceStateKind
    expected_date: date | None
    state_key: str


def _root(outlook: PestOutlook) -> str:
    return (
        f"{outlook.model.model_version}:"
        f"{outlook.biofix_date.isoformat()}"
    )


def _advance_prefix(outlook: PestOutlook) -> str | None:
    if outlook.next_stage is None:
        return None
    return f"{_root(outlook)}:approaching:{outlook.next_stage.key}"


def _expected_state_key(prefix: str, expected_date: date) -> str:
    return f"{prefix}:expected:{expected_date.isoformat()}"


def _withdrawn_state_key(prefix: str, previous_date: date) -> str:
    return f"{prefix}:withdrawn:{previous_date.isoformat()}"


def _parse_state(raw_value: str | None, prefix: str) -> _AdvanceState | None:
    if raw_value is None:
        return None
    if raw_value == prefix:
        return _AdvanceState("legacy", None, raw_value)

    expected_prefix = f"{prefix}:expected:"
    withdrawn_prefix = f"{prefix}:withdrawn:"
    if raw_value.startswith(expected_prefix):
        date_text = raw_value[len(expected_prefix) :]
        try:
            expected_date = date.fromisoformat(date_text)
        except ValueError:
            return None
        return _AdvanceState("expected", expected_date, raw_value)
    if raw_value.startswith(withdrawn_prefix):
        date_text = raw_value[len(withdrawn_prefix) :]
        try:
            previous_date = date.fromisoformat(date_text)
        except ValueError:
            return None
        return _AdvanceState("withdrawn", previous_date, raw_value)
    return None


def _transition_key(
    prefix: str,
    previous_state: str,
    current_state: str,
) -> str:
    signature = f"{previous_state}->{current_state}"
    digest = sha256(signature.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:transition:{digest}"


def pest_notification_state_key(notification: PestNotification) -> str:
    if isinstance(notification, SemanticPestNotification):
        return notification.state_key
    return notification.event_key


def choose_semantic_pest_notification(
    outlook: PestOutlook,
    *,
    last_notified_stage: str | None,
    last_notified_advance: str | None,
    today: date,
    advance_days: int = 3,
) -> PestNotification | None:
    """Choose one stage or forecast-window transition without daily repetition.

    The first approach reminder is emitted only inside ``advance_days``. Once an
    approach was announced, a material calendar-date change is reported even if
    the new date moves outside that initial window. A disappeared crossing is
    explicitly withdrawn once and can later be restored.
    """

    if not outlook.available or outlook.current_stage is None:
        return None
    if advance_days < 0:
        raise ValueError(
            "Срок предварительного напоминания не может быть отрицательным."
        )

    root = _root(outlook)
    current_key = f"{root}:current:{outlook.current_stage.key}"
    if last_notified_stage != current_key:
        return PestNotification(
            event_key=current_key,
            kind="current_window",
            stage=outlook.current_stage,
            expected_date=None,
        )

    if outlook.next_stage is None:
        return None
    prefix = _advance_prefix(outlook)
    if prefix is None:  # pragma: no cover - guarded by next_stage
        return None
    previous = _parse_state(last_notified_advance, prefix)
    projected = outlook.projected_crossing_date

    if projected is None or projected < today:
        if (
            previous is None
            or previous.kind != "expected"
            or previous.expected_date is None
        ):
            return None
        state_key = _withdrawn_state_key(prefix, previous.expected_date)
        return SemanticPestNotification(
            event_key=_transition_key(prefix, previous.state_key, state_key),
            kind="approaching_window",
            stage=outlook.next_stage,
            expected_date=None,
            state_key=state_key,
            change="withdrawn",
            previous_expected_date=previous.expected_date,
        )

    state_key = _expected_state_key(prefix, projected)
    if previous is not None and previous.state_key == state_key:
        return None

    lead_days = (projected - today).days
    if previous is None or previous.kind == "legacy":
        if not 0 <= lead_days <= advance_days:
            return None
        previous_key = "none" if previous is None else previous.state_key
        return SemanticPestNotification(
            event_key=_transition_key(prefix, previous_key, state_key),
            kind="approaching_window",
            stage=outlook.next_stage,
            expected_date=projected,
            state_key=state_key,
            change="initial",
        )

    if previous.kind == "withdrawn":
        return SemanticPestNotification(
            event_key=_transition_key(prefix, previous.state_key, state_key),
            kind="approaching_window",
            stage=outlook.next_stage,
            expected_date=projected,
            state_key=state_key,
            change="restored",
            previous_expected_date=previous.expected_date,
        )

    assert previous.expected_date is not None
    change: PestAdvanceChange = (
        "earlier" if projected < previous.expected_date else "later"
    )
    return SemanticPestNotification(
        event_key=_transition_key(prefix, previous.state_key, state_key),
        kind="approaching_window",
        stage=outlook.next_stage,
        expected_date=projected,
        state_key=state_key,
        change=change,
        previous_expected_date=previous.expected_date,
    )
