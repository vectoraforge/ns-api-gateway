from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = None
session_factory = None


def init_engine(url: str, pool_size: int):
    global engine, session_factory
    engine = create_async_engine(url, pool_size=pool_size, max_overflow=0)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if session_factory is None:
        raise Exception("session_factory is not initialized")
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
