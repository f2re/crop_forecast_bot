from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"


class SchemaRevisionError(RuntimeError):
    """Database schema revision does not match the application release."""


def expected_schema_revision(config_path: Path = DEFAULT_ALEMBIC_CONFIG) -> str:
    config = Config(str(config_path))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise SchemaRevisionError(
            f"Expected exactly one Alembic head, found {len(heads)}: {heads}"
        )
    return heads[0]


async def current_schema_revision(engine: AsyncEngine) -> str | None:
    async with engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_connection: MigrationContext.configure(
                sync_connection
            ).get_current_revision()
        )


async def require_current_schema(engine: AsyncEngine) -> str:
    expected = expected_schema_revision()
    current = await current_schema_revision(engine)
    if current != expected:
        current_label = current or "not initialized"
        raise SchemaRevisionError(
            "Database schema is not current: "
            f"current={current_label}, expected={expected}. "
            "Run `alembic upgrade head` before starting the bot."
        )
    return current
