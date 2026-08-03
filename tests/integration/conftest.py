from __future__ import annotations

import os

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture(autouse=True)
async def clean_orphan_extension_tables() -> None:
    """Repair the intentionally destructive legacy reset used by integration tests.

    Several older integration modules drop the original core tables and the
    Alembic marker directly. PostgreSQL keeps a referencing table when its
    foreign-key target is dropped with CASCADE; only the constraint disappears.
    Until those modules are consolidated on one reset helper, remove the new
    extension table whenever the Alembic marker is absent so the next fresh
    migration remains reproducible.
    """

    database_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if database_url:
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                version_table = await connection.scalar(
                    text("SELECT to_regclass('public.alembic_version')")
                )
                pest_table = await connection.scalar(
                    text("SELECT to_regclass('public.pest_monitors')")
                )
                if version_table is None and pest_table is not None:
                    await connection.execute(
                        text("DROP TABLE IF EXISTS pest_monitors CASCADE")
                    )
        finally:
            await engine.dispose()
    yield
