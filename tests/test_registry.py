import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from docsync.authorization import AuthenticatedIdentity, AuthorizationError, Role
from docsync.db import create_database_engine
from docsync.models import Artefact, AuditRecord, MirrorMapping
from docsync.registry import ArtefactRegistry, RegistryError


TEST_DATABASE_URL = os.environ.get(
    "DOCSYNC_DATABASE_URL",
    "postgresql+psycopg://docsync_test@127.0.0.1:55432/docsync_test",
)


@pytest.fixture(scope="module", autouse=True)
def registry_schema() -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")
    yield


def test_register_preserves_stable_id_during_move() -> None:
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    admin = AuthenticatedIdentity("admin-1", True, frozenset({Role.ADMINISTRATOR}))
    with Session(engine) as session:
        session.query(MirrorMapping).delete()
        session.query(AuditRecord).delete()
        session.query(Artefact).delete()
        registry = ArtefactRegistry(session)
        artefact = registry.register(
            admin,
            name="Requirements",
            artefact_type="requirements",
            source_system="github",
            configured_scope="KAN",
            external_id="requirements.md",
            location="requirements.md",
            owner_account_id="owner-1",
            version="sha-1",
            content_digest="digest-1",
            related_document_ids=["architecture.md"],
        )
        original_id = artefact.id
        moved = registry.confirmed_move(
            admin, artefact, name="Approved Requirements", location="docs/requirements.md"
        )
        assert moved.id == original_id
        assert moved.external_id == "requirements.md"
        assert moved.location == "docs/requirements.md"
        assert registry.require_owner(moved) == "owner-1"
        assert session.query(AuditRecord).filter(
            AuditRecord.action.in_(["artefact_register", "artefact_move"])
        ).count() == 2
    engine.dispose()


def test_duplicate_identity_and_unknown_owner_fail_closed() -> None:
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    admin = AuthenticatedIdentity("admin-1", True, frozenset({Role.ADMINISTRATOR}))
    with Session(engine) as session:
        registry = ArtefactRegistry(session)
        first = registry.register(
            admin,
            name="Design Review",
            artefact_type="design_review",
            source_system="github",
            configured_scope="KAN",
            external_id="design-review.md",
        )
        with pytest.raises(RegistryError, match="already exists"):
            registry.register(
                admin,
                name="Duplicate",
                artefact_type="design_review",
                source_system="github",
                configured_scope="KAN",
                external_id="design-review.md",
            )
        with pytest.raises(AuthorizationError, match="Unknown document owner"):
            registry.require_owner(first)
    engine.dispose()
