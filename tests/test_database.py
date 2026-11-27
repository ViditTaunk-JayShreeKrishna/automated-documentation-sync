import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from docsync.db import create_database_engine
from docsync.models import Artefact, AuditRecord, Dependency


TEST_DATABASE_URL = os.environ.get(
    "DOCSYNC_DATABASE_URL",
    "postgresql+psycopg://docsync_test@127.0.0.1:55432/docsync_test",
)


@pytest.fixture(scope="session")
def migration_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


@pytest.fixture(scope="session", autouse=True)
def isolated_database(migration_config: Config):
    command.upgrade(migration_config, "head")
    yield
    command.downgrade(migration_config, "base")


def test_migration_creates_required_tables(migration_config: Config) -> None:
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    with engine.connect() as connection:
        names = set(inspect(connection).get_table_names())
    assert {
        "artefacts",
        "dependencies",
        "events",
        "jobs",
        "proposals",
        "approvals",
        "audit_records",
    } <= names
    engine.dispose()


def test_artefact_identity_is_unique_and_transactional() -> None:
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    with Session(engine) as session:
        session.query(Artefact).delete()
        session.commit()
        session.add(
            Artefact(
                name="Requirements",
                artefact_type="requirements",
                source_system="github",
                configured_scope="KAN",
                external_id="requirements.md",
            )
        )
        session.commit()
        session.add(
            Artefact(
                name="Duplicate",
                artefact_type="requirements",
                source_system="github",
                configured_scope="KAN",
                external_id="requirements.md",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.query(Artefact).count() == 1
    engine.dispose()


def test_dependency_rejects_self_reference() -> None:
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    with Session(engine) as session:
        session.query(Dependency).delete()
        session.query(Artefact).delete()
        artefact = Artefact(
            name="Architecture",
            artefact_type="architecture",
            source_system="github",
            configured_scope="KAN",
            external_id="architecture.md",
        )
        session.add(artefact)
        session.commit()
        session.add(
            Dependency(
                source_artefact_id=artefact.id,
                dependent_artefact_id=artefact.id,
                relationship_type="supports",
                evidence={"test": True},
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    engine.dispose()


def test_migration_downgrade_and_upgrade_is_reversible(migration_config: Config) -> None:
    command.downgrade(migration_config, "base")
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    with engine.connect() as connection:
        assert "artefacts" not in inspect(connection).get_table_names()
    engine.dispose()
    command.upgrade(migration_config, "head")
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    with engine.connect() as connection:
        assert "artefacts" in inspect(connection).get_table_names()
    engine.dispose()
