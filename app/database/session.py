from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings, get_settings

settings = get_settings()


def build_database_engine(configuration: Settings) -> Engine:
    return create_engine(
        configuration.database_url,
        connect_args={
            "connect_timeout": configuration.database_connect_timeout_seconds,
        },
        pool_pre_ping=True,
        pool_size=configuration.database_pool_size,
        max_overflow=configuration.database_max_overflow,
        pool_timeout=configuration.database_pool_timeout_seconds,
    )


engine = build_database_engine(settings)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_database_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
