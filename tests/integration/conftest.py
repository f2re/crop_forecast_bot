from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def _drop_test_tables(database_url: str) -> None:
    """Remove every application table, including tables added by new migrations."""

    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = current_schema()"
                )
            )
            preparer = connection.dialect.identifier_preparer
            for table_name in result.scalars().all():
                quoted_name = preparer.quote_identifier(table_name)
                await connection.exec_driver_sql(
                    f"DROP TABLE IF EXISTS {quoted_name} CASCADE"
                )
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def isolate_postgres_integration_schema() -> AsyncIterator[None]:
    """Prevent one integration scenario or startup smoke from leaking schema."""

    database_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not database_url:
        yield
        return
    if not database_url.startswith("postgresql+asyncpg://"):
        yield
        return

    await _drop_test_tables(database_url)
    try:
        yield
    finally:
        await _drop_test_tables(database_url)
