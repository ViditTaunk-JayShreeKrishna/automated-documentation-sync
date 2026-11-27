import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from docsync.authorization import AuthenticatedIdentity, AuthorizationError, Role
from docsync.db import create_database_engine
from docsync.dependencies import DependencyRegistry, DependencyRegistryError
from docsync.models import Artefact, AuditRecord, Dependency


TEST_DATABASE_URL = os.environ.get(
    "DOCSYNC_DATABASE_URL",
    "postgresql+psycopg://docsync_test@127.0.0.1:55432/docsync_test",
)


@pytest.fixture(scope="module", autouse=True)
def dependency_schema() -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")
    yield


def test_only_approved_edges_are_traversable() -> None:
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    admin = AuthenticatedIdentity("admin-1", True, frozenset({Role.ADMINISTRATOR}))
    member = AuthenticatedIdentity("member-1", True, frozenset({Role.PROJECT_MEMBER}))
    with Session(engine) as session:
        session.query(Dependency).delete()
        session.query(Artefact).delete()
        source = Artefact(name="Requirements", artefact_type="requirements", source_system="jira", configured_scope="KAN", external_id="KAN-1")
        target = Artefact(name="Architecture", artefact_type="architecture", source_system="github", configured_scope="KAN", external_id="architecture.md")
        session.add_all([source, target])
        session.commit()
        registry = DependencyRegistry(session)
        pending = registry.propose(member, source, target, "supports", {"evidence": "KAN-1"})
        assert registry.approved_dependents(source.id) == []
        approved = registry.approve(admin, pending)
        assert approved.status == "approved"
        assert [item.id for item in registry.approved_dependents(source.id)] == [target.id]
    engine.dispose()


def test_cycle_is_rejected_and_rejection_requires_reason() -> None:
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    admin = AuthenticatedIdentity("admin-1", True, frozenset({Role.ADMINISTRATOR}))
    member = AuthenticatedIdentity("member-1", True, frozenset({Role.PROJECT_MEMBER}))
    with Session(engine) as session:
        session.query(Dependency).delete()
        session.query(Artefact).delete()
        source = Artefact(name="A", artefact_type="architecture", source_system="github", configured_scope="KAN", external_id="a")
        target = Artefact(name="B", artefact_type="architecture", source_system="github", configured_scope="KAN", external_id="b")
        session.add_all([source, target])
        session.commit()
        registry = DependencyRegistry(session)
        forward = registry.propose(member, source, target, "depends-on", {"evidence": "test"})
        registry.approve(admin, forward)
        reverse = registry.propose(member, target, source, "depends-on", {"evidence": "test"})
        with pytest.raises(DependencyRegistryError, match="cycle"):
            registry.approve(admin, reverse)
        with pytest.raises(DependencyRegistryError, match="rejection reason"):
            registry.reject(admin, reverse, "")
        rejected = registry.reject(admin, reverse, "Contradictory evidence")
        assert rejected.status == "rejected"
    engine.dispose()


def test_project_member_cannot_approve_or_reject() -> None:
    engine = create_database_engine({"DOCSYNC_DATABASE_URL": TEST_DATABASE_URL})
    member = AuthenticatedIdentity("member-1", True, frozenset({Role.PROJECT_MEMBER}))
    with Session(engine) as session:
        candidate = Dependency(
            source_artefact_id="00000000-0000-0000-0000-000000000001",
            dependent_artefact_id="00000000-0000-0000-0000-000000000002",
            relationship_type="supports",
            status="pending",
            evidence={},
        )
        registry = DependencyRegistry(session)
        with pytest.raises(AuthorizationError):
            registry.approve(member, candidate)
    engine.dispose()
