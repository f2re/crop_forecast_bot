from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, cast

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Base
from src.domain.risk import RiskLevel, RiskType
from src.domain.risk_delivery import (
    RiskDeliveryMode,
    RiskEpisodeState,
    validate_risk_delivery_mode,
)

_STATE_VERSION = 1
_RISK_TYPES = frozenset(
    {"frost", "heat", "heavy_rain", "strong_wind", "convection"}
)
_RISK_LEVELS = frozenset({"watch", "elevated", "high"})


def _register_table(metadata: MetaData) -> Table:
    existing = metadata.tables.get("risk_delivery_states")
    if existing is not None:
        return existing
    return Table(
        "risk_delivery_states",
        metadata,
        Column(
            "field_id",
            Integer,
            ForeignKey("fields.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        Column("model", String(80), nullable=False),
        Column("delivery_mode", String(16), nullable=False),
        Column(
            "state_version",
            Integer,
            nullable=False,
            default=_STATE_VERSION,
            server_default="1",
        ),
        Column("state_json", Text, nullable=False),
        Column("last_observed_at", DateTime, nullable=False),
        Column("last_notified_at", DateTime, nullable=True),
        CheckConstraint(
            "delivery_mode IN ('immediate', 'digest', 'high_only')",
            name="ck_risk_delivery_states_mode",
        ),
        Index(
            "ix_risk_delivery_states_observed_at",
            "last_observed_at",
        ),
    )


risk_delivery_states = _register_table(Base.metadata)


@dataclass(frozen=True, slots=True)
class StoredRiskDeliveryState:
    field_id: int
    model: str
    delivery_mode: RiskDeliveryMode
    episodes: tuple[RiskEpisodeState, ...]
    last_observed_at: datetime
    last_notified_at: datetime | None


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _serialize(episodes: tuple[RiskEpisodeState, ...]) -> str:
    payload = [
        {
            "risk_type": episode.risk_type,
            "start_date": episode.start_date.isoformat(),
            "end_date": episode.end_date.isoformat(),
            "highest_level": episode.highest_level,
        }
        for episode in episodes
    ]
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_episode(item: Any) -> RiskEpisodeState:
    if not isinstance(item, dict):
        raise ValueError("risk delivery state item is not an object")
    risk_type = item.get("risk_type")
    highest_level = item.get("highest_level")
    if risk_type not in _RISK_TYPES:
        raise ValueError(f"unsupported risk type in delivery state: {risk_type!r}")
    if highest_level not in _RISK_LEVELS:
        raise ValueError(
            f"unsupported risk level in delivery state: {highest_level!r}"
        )
    try:
        start_date = date.fromisoformat(str(item["start_date"]))
        end_date = date.fromisoformat(str(item["end_date"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid date in risk delivery state") from exc
    if end_date < start_date:
        raise ValueError("risk delivery state ends before it starts")
    return RiskEpisodeState(
        risk_type=cast(RiskType, risk_type),
        start_date=start_date,
        end_date=end_date,
        highest_level=cast(RiskLevel, highest_level),
    )


def _deserialize(raw_value: str) -> tuple[RiskEpisodeState, ...]:
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError("risk delivery state is not valid JSON") from exc
    if not isinstance(payload, list):
        raise ValueError("risk delivery state root is not a list")
    return tuple(_decode_episode(item) for item in payload)


async def load_risk_delivery_state(
    session: AsyncSession,
    *,
    field_id: int,
    model: str,
    delivery_mode: str,
) -> StoredRiskDeliveryState | None:
    resolved_mode = validate_risk_delivery_mode(delivery_mode)
    result = await session.execute(
        select(risk_delivery_states).where(
            risk_delivery_states.c.field_id == field_id
        )
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    if (
        row["model"] != model
        or row["delivery_mode"] != resolved_mode
        or row["state_version"] != _STATE_VERSION
    ):
        return None
    try:
        episodes = _deserialize(row["state_json"])
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid persisted risk delivery state for field {field_id}"
        ) from exc
    return StoredRiskDeliveryState(
        field_id=field_id,
        model=row["model"],
        delivery_mode=resolved_mode,
        episodes=episodes,
        last_observed_at=row["last_observed_at"],
        last_notified_at=row["last_notified_at"],
    )


async def save_risk_delivery_state(
    session: AsyncSession,
    *,
    field_id: int,
    model: str,
    delivery_mode: str,
    episodes: tuple[RiskEpisodeState, ...],
    observed_at: datetime,
    notified_at: datetime | None = None,
) -> StoredRiskDeliveryState:
    resolved_mode = validate_risk_delivery_mode(delivery_mode)
    observed_value = _utc_naive(observed_at)
    notified_value = None if notified_at is None else _utc_naive(notified_at)
    result = await session.execute(
        select(
            risk_delivery_states.c.field_id,
            risk_delivery_states.c.model,
            risk_delivery_states.c.delivery_mode,
            risk_delivery_states.c.last_notified_at,
        ).where(risk_delivery_states.c.field_id == field_id)
    )
    existing = result.mappings().one_or_none()
    compatible_existing = (
        existing is not None
        and existing["model"] == model
        and existing["delivery_mode"] == resolved_mode
    )
    values = {
        "model": model,
        "delivery_mode": resolved_mode,
        "state_version": _STATE_VERSION,
        "state_json": _serialize(episodes),
        "last_observed_at": observed_value,
        "last_notified_at": (
            notified_value
            if notified_value is not None
            else (
                existing["last_notified_at"]
                if compatible_existing
                else None
            )
        ),
    }
    if existing is None:
        await session.execute(
            insert(risk_delivery_states).values(
                field_id=field_id,
                **values,
            )
        )
    else:
        await session.execute(
            update(risk_delivery_states)
            .where(risk_delivery_states.c.field_id == field_id)
            .values(**values)
        )
    await session.commit()
    return StoredRiskDeliveryState(
        field_id=field_id,
        model=model,
        delivery_mode=resolved_mode,
        episodes=episodes,
        last_observed_at=observed_value,
        last_notified_at=values["last_notified_at"],
    )
