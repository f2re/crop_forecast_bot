from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class Database:
    def __init__(self, db_url: str):
        self.engine = create_async_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=1800,
            echo=False,
        )
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()

    def get_session(self) -> AsyncSession:
        return self.session_maker()


_db: Database | None = None


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database is not initialized")
    return _db


def init_db(db_url: str) -> Database:
    global _db
    if _db is not None:
        return _db
    _db = Database(db_url)
    return _db
