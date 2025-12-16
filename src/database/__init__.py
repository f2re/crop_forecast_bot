from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from .models import Base


class Database:
    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, poolclass=NullPool, echo=False)
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def create_tables(self):
        """Create all tables"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self):
        """Drop all tables"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    def get_session(self) -> AsyncSession:
        """Get database session"""
        return self.session_maker()


# Global database instance
db: Database = None


def get_db() -> Database:
    """Get global database instance"""
    return db


def init_db(db_url: str) -> Database:
    """Initialize database"""
    global db
    db = Database(db_url)
    return db
