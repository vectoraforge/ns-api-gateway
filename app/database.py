from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

engine = None
session_factory = None


def init_engine(url: str, pool_size: int):
    global engine, session_factory
    engine = create_async_engine(url, pool_size=pool_size, max_overflow=0)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
