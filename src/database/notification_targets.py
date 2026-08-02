from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import CropSeason, Field, User
from src.domain.risk_delivery import RiskDeliveryMode, validate_risk_delivery_mode


@dataclass(frozen=True, slots=True)
class EnabledNotificationTarget:
    telegram_id: int
    field_id: int
    field_name: str
    latitude: float
    longitude: float
    timezone: str
    elevation_m: float | None
    elevation_source: str | None
    selected_crop: str
    season_start_date: date | None
    phenological_phase: str | None
    daily_digest_enabled: bool
    frost_alerts_enabled: bool
    risk_delivery_mode: RiskDeliveryMode
    quiet_hours_start: int | None
    quiet_hours_end: int | None
    crop_keys: tuple[str, ...] = ()


async def list_enabled_notification_targets(
    session: AsyncSession,
    *,
    daily_digest_only: bool = False,
    frost_alerts_only: bool = False,
) -> list[EnabledNotificationTarget]:
    """Return every field enabled for the requested background notification.

    ``Field.is_active`` is intentionally not used here. The active field is a
    Telegram navigation concept; background monitoring must continue for all
    explicitly enabled fields owned by the user.
    """
    statement = (
        select(
            User.telegram_id,
            User.selected_crop.label("legacy_crop"),
            Field.id.label("field_id"),
            Field.name.label("field_name"),
            Field.latitude,
            Field.longitude,
            Field.timezone,
            Field.elevation_m,
            Field.elevation_source,
            Field.daily_digest_enabled,
            Field.frost_alerts_enabled,
            Field.risk_delivery_mode,
            Field.quiet_hours_start,
            Field.quiet_hours_end,
            CropSeason.crop_key,
            CropSeason.season_start_date,
            CropSeason.phenological_phase,
        )
        .join(Field, Field.user_id == User.id)
        .outerjoin(
            CropSeason,
            and_(
                CropSeason.field_id == Field.id,
                CropSeason.is_active.is_(True),
            ),
        )
        .order_by(User.telegram_id.asc(), Field.id.asc())
    )
    if daily_digest_only:
        statement = statement.where(Field.daily_digest_enabled.is_(True))
    if frost_alerts_only:
        statement = statement.where(Field.frost_alerts_enabled.is_(True))

    result = await session.execute(statement)
    rows = result.all()
    field_ids = tuple(dict.fromkeys(row.field_id for row in rows))
    crop_map: dict[int, list[str]] = {field_id: [] for field_id in field_ids}
    if field_ids:
        crop_result = await session.execute(
            select(CropSeason.field_id, CropSeason.crop_key)
            .where(CropSeason.field_id.in_(field_ids))
            .order_by(
                CropSeason.field_id.asc(),
                CropSeason.is_active.desc(),
                CropSeason.created_at.asc(),
            )
        )
        for field_id, crop_key in crop_result.all():
            if crop_key not in crop_map[field_id]:
                crop_map[field_id].append(crop_key)

    targets: dict[int, EnabledNotificationTarget] = {}
    for row in rows:
        selected_crop = row.crop_key or row.legacy_crop or "wheat"
        crops = tuple(crop_map.get(row.field_id, ())) or (selected_crop,)
        targets.setdefault(
            row.field_id,
            EnabledNotificationTarget(
                telegram_id=row.telegram_id,
                field_id=row.field_id,
                field_name=row.field_name,
                latitude=float(row.latitude),
                longitude=float(row.longitude),
                timezone=row.timezone or "UTC",
                elevation_m=(
                    float(row.elevation_m) if row.elevation_m is not None else None
                ),
                elevation_source=row.elevation_source,
                selected_crop=selected_crop,
                season_start_date=row.season_start_date,
                phenological_phase=row.phenological_phase,
                daily_digest_enabled=bool(row.daily_digest_enabled),
                frost_alerts_enabled=bool(row.frost_alerts_enabled),
                risk_delivery_mode=validate_risk_delivery_mode(
                    row.risk_delivery_mode or "immediate"
                ),
                quiet_hours_start=row.quiet_hours_start,
                quiet_hours_end=row.quiet_hours_end,
                crop_keys=crops,
            ),
        )
    return list(targets.values())
