import os

from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config

import pytest

from docsync.authorization import (
    AuthenticatedIdentity,
    AuthorizationError,
    Role,
    require_document_authority,
    require_role,
    change_owner_mapping,
)
from docsync.db import create_database_engine
from docsync.models import Artefact, OwnerMapping
from docsync.models import AuditRecord


@pytest.fixture(scope="module", autouse=True)
def authorization_schema() -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")
    yield


TEST_DATABASE_URL = os.environ.get(
    "DOCSYNC_DATABASE_URL",
    "postgresql+psycopg://docsync_test@127.0.0.1:55432/docsync_test",
)


def test_role_requires_native_verification() -> None:
    identity = AuthenticatedIdentity("account-1", False, frozenset({Role.ADMINISTRATOR}))
    with pytest.raises(AuthorizationError, match="native-provider"):
        require_role(identity, Role.ADMINISTRATOR)

    identity = AuthenticatedIdentity("account-1", True, frozenset({Role.ADMINISTRATOR}))
    require_role(identity, Role.ADMINISTRATOR)


def test_role_denies_missing_role() -> None:
    identity = AuthenticatedIdentity("account-1", True, frozenset({Role.PROJECT_MEMBER}))
    with pytest.raises(AuthorizationError, match="lacks required role"):
        require_role(identity, Role.ADMINISTRATOR)


def test_document_owner_mapping_is_required_and_auditable() -> None:
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    with Session(engine) as session:
        session.query(OwnerMapping).delete()
        session.query(Artefact).delete()
        artefact = Artefact(
            name="Architecture",
            artefact_type="architecture",
            source_system="github",
            configured_scope="KAN",
            external_id="architecture.md",
            owner_account_id="owner-1",
        )
        session.add(artefact)
        session.commit()

        unauthorized = AuthenticatedIdentity("unknown", True, frozenset({Role.PROJECT_MEMBER}))
        with pytest.raises(AuthorizationError, match="Unknown or unauthorized"):
            require_document_authority(session, unauthorized, artefact.id, "approve")

        session.add(OwnerMapping(
            artefact_id=artefact.id,
            account_id="owner-1",
            role=Role.DOCUMENT_OWNER.value,
            delegate=False,
            active=True,
            created_by="administrator-1",
        ))
        session.commit()

        owner = AuthenticatedIdentity("owner-1", True, frozenset({Role.DOCUMENT_OWNER}))
        require_document_authority(session, owner, artefact.id, "approve")

        owner_inactive = AuthenticatedIdentity("owner-1", False, frozenset({Role.DOCUMENT_OWNER}))
        with pytest.raises(AuthorizationError, match="native-provider"):
            require_document_authority(session, owner_inactive, artefact.id, "approve")
    engine.dispose()


def test_mapping_change_requires_administrator_and_is_audited() -> None:
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    with Session(engine) as session:
        session.query(AuditRecord).delete()
        session.query(OwnerMapping).delete()
        session.query(Artefact).delete()
        artefact = Artefact(
            name="Proposal",
            artefact_type="proposal",
            source_system="application",
            configured_scope="KAN",
            external_id="proposal-1",
        )
        session.add(artefact)
        session.commit()

        project_member = AuthenticatedIdentity(
            "member-1", True, frozenset({Role.PROJECT_MEMBER})
        )
        with pytest.raises(AuthorizationError, match="lacks required role"):
            change_owner_mapping(
                session, project_member, artefact.id, "owner-1",
                Role.DOCUMENT_OWNER, False, True,
            )

        administrator = AuthenticatedIdentity(
            "admin-1", True, frozenset({Role.ADMINISTRATOR})
        )
        mapping = change_owner_mapping(
            session, administrator, artefact.id, "owner-1",
            Role.DOCUMENT_OWNER, False, True,
        )
        assert mapping.account_id == "owner-1"
        assert session.query(AuditRecord).filter(
            AuditRecord.action == "owner_mapping_change"
        ).count() == 1
    engine.dispose()
