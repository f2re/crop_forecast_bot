from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import date, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import CropSeason, Field, User
from src.domain.risk_delivery import RiskDeliveryMode, validate_risk_delivery_mode

logger = logging.getLogger(__name__)


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
    date_basis: str = "season_start"
    production_system: str = "unknown"
    plant_type: str = "unknown"
    phase_confirmed_at: datetime | None = None
    field_ids: tuple[int, ...] = ()
    field_names: tuple[str, ...] = ()


def _weather_location_key(target: EnabledNotificationTarget) -> tuple[object, ...]:
    """Group accidental duplicate field cards without merging their database rows.

    Five decimal places are about one metre in latitude and sufficiently strict
    for duplicate coordinates copied from the same Telegram location. Delivery
    preferences remain part of the key: two deliberately different policies are
    not silently combined.
    """

    return (
        target.telegram_id,
        round(target.latitude, 5),
        round(target.longitude, 5),
        target.timezone,
        target.risk_delivery_mode,
        target.quiet_hours_start,
        target.quiet_hours_end,
    )


def collapse_weather_notification_targets(
    targets: list[EnabledNotificationTarget],
) -> list[EnabledNotificationTarget]:
    """Return one weather target for duplicate cards of the same point.

    A coordinate point can already contain multiple crop seasons. Creating a
    second field card with the same coordinates should therefore not duplicate a
    location-wide heat, rain or wind alert. The lowest field id owns the
    persistent delivery baseline; all field names and crops remain visible in
    the combined Telegram message.
    """

    groups: dict[tuple[object, ...], list[EnabledNotificationTarget]] = {}
    for target in targets:
        groups.setdefault(_weather_location_key(target), []).append(target)

    collapsed: list[EnabledNotificationTarget] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda item: item.field_id)
        primary = ordered[0]
        field_ids = tuple(item.field_id for item in ordered)
        field_names = tuple(dict.fromkeys(item.field_name for item in ordered))
        crop_keys = tuple(
            dict.fromkeys(
                crop
                for item in ordered
                for crop in (item.crop_keys or (item.selected_crop,))
                if crop
            )
        )
        phases = tuple(
            dict.fromkeys(
                item.phenological_phase
                for item in ordered
                if item.phenological_phase
            )
        )
        combined_name = " / ".join(field_names)
        if len(combined_name) > 120:
            combined_name = combined_name[:117].rstrip() + "…"

        if len(ordered) > 1:
            logger.warning(
                "Collapsed duplicate weather targets for Telegram user %s: "
                "field ids %s at %.5f, %.5f",
                primary.telegram_id,
                field_ids,
                primary.latitude,
                primary.longitude,
            )

        collapsed.append(
            replace(
                primary,
                field_name=combined_name,
                crop_keys=crop_keys or (primary.selected_crop,),
                phenological_phase=phases[0] if len(phases) == 1 else None,
                field_ids=field_ids,
                field_names=field_names,
            )
        )

    collapsed.sort(key=lambda item: (item.telegram_id, item.field_id))
    return collapsed


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

    Location-wide weather alerts collapse accidental duplicate field cards with
    identical coordinates and delivery settings. Crop-specific daily reports
    remain separate.
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
            CropSeason.date_basis,
            CropSeason.production_system,
            CropSeason.plant_type,
            CropSeason.phenological_phase,
            CropSeason.phase_confirmed_at,
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
                date_basis=row.date_basis or "season_start",
                production_system=row.production_system or "unknown",
                plant_type=row.plant_type or "unknown",
                phase_confirmed_at=row.phase_confirmed_at,
                field_ids=(row.field_id,),
                field_names=(row.field_name,),
            ),
        )

    resolved = list(targets.values())
    if frost_alerts_only and not daily_digest_only:
        return collapse_weather_notification_targets(resolved)
    return resolved
