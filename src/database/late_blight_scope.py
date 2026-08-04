from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import CropSeason


async def open_field_late_blight_season_ids(
    session: AsyncSession,
    season_ids: tuple[int, ...],
) -> frozenset[int]:
    """Return active potato seasons explicitly marked as open field.

    The Hutton adapter uses outdoor model-grid weather. Unknown and greenhouse
    production systems are excluded instead of silently applying outdoor air
    to a protected-crop microclimate.
    """

    if not season_ids:
        return frozenset()
    result = await session.execute(
        select(CropSeason.id).where(
            CropSeason.id.in_(season_ids),
            CropSeason.is_active.is_(True),
            CropSeason.crop_key == "potato",
            CropSeason.production_system == "open_field",
        )
    )
    return frozenset(int(value) for value in result.scalars())
