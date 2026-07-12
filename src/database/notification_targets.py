from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.crud import NotificationTarget
from src.database.models import CropSeason, Field, User


async def list_enabled_notification_targets(
    session: AsyncSession,
    *,
    daily_digest_only: bool = False,
    frost_alerts_only: bool = False,
) -> list[NotificationTarget]:
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
    targets: dict[int, NotificationTarget] = {}
    for row in result.all():
        targets.setdefault(
            row.field_id,
            NotificationTarget(
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
                selected_crop=row.crop_key or row.legacy_crop or "wheat",
                season_start_date=row.season_start_date,
                phenological_phase=row.phenological_phase,
                daily_digest_enabled=bool(row.daily_digest_enabled),
                frost_alerts_enabled=bool(row.frost_alerts_enabled),
            ),
        )
    return list(targets.values())
