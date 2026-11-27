"""SQLAlchemy database setup."""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url(env: dict[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    return values.get(
        "DOCSYNC_DATABASE_URL",
        "postgresql+psycopg://docsync_test@127.0.0.1:55432/docsync_test",
    )


def create_database_engine(env: dict[str, str] | None = None) -> Engine:
    url = database_url(env)
    return create_engine(url, pool_pre_ping=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
