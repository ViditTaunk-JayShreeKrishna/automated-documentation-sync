"""Authorized dependency registry and cycle-safe traversal."""

from collections.abc import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from docsync.authorization import AuthenticatedIdentity, AuthorizationError, Role, require_role
from docsync.models import Artefact, AuditRecord, Dependency


class DependencyRegistryError(ValueError):
    pass


class DependencyRegistry:
    def __init__(self, session: Session) -> None:
        self.session = session

    def propose(
        self,
        identity: AuthenticatedIdentity,
        source: Artefact,
        dependent: Artefact,
        relationship_type: str,
        evidence: dict,
    ) -> Dependency:
        require_role(identity, Role.PROJECT_MEMBER)
        if source.id == dependent.id:
            raise DependencyRegistryError("A dependency cannot reference itself")
        candidate = Dependency(
            source_artefact_id=source.id,
            dependent_artefact_id=dependent.id,
            relationship_type=relationship_type,
            status="pending",
            evidence=evidence,
        )
        self.session.add(candidate)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            raise DependencyRegistryError("Duplicate dependency candidate") from None
        self.session.commit()
        return candidate

    def approve(
        self,
        identity: AuthenticatedIdentity,
        candidate: Dependency,
    ) -> Dependency:
        require_role(identity, Role.ADMINISTRATOR)
        if candidate.status != "pending":
            raise DependencyRegistryError("Only pending dependencies can be approved")
        if self.has_cycle(
            candidate.source_artefact_id,
            candidate.dependent_artefact_id,
        ):
            raise DependencyRegistryError("Dependency approval would create a cycle")
        candidate.status = "approved"
        self.session.add(AuditRecord(
            actor_account_id=identity.account_id,
            action="dependency_approve",
            target_artefact_id=candidate.dependent_artefact_id,
            outcome="recorded",
            details={
                "dependency_id": str(candidate.id),
                "relationship_type": candidate.relationship_type,
                "source_artefact_id": str(candidate.source_artefact_id),
            },
        ))
        self.session.commit()
        return candidate

    def reject(
        self,
        identity: AuthenticatedIdentity,
        candidate: Dependency,
        reason: str,
    ) -> Dependency:
        require_role(identity, Role.ADMINISTRATOR)
        if not reason.strip():
            raise DependencyRegistryError("A rejection reason is required")
        candidate.status = "rejected"
        candidate.evidence = {**candidate.evidence, "rejection_reason": reason}
        self.session.add(AuditRecord(
            actor_account_id=identity.account_id,
            action="dependency_reject",
            target_artefact_id=candidate.dependent_artefact_id,
            outcome="recorded",
            details={"dependency_id": str(candidate.id), "reason": reason},
        ))
        self.session.commit()
        return candidate

    def has_cycle(self, source_id, dependent_id) -> bool:
        adjacency = self._approved_adjacency()
        adjacency.setdefault(source_id, set()).add(dependent_id)
        visited: set[object] = set()
        stack = [dependent_id]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            if source_id in adjacency.get(current, set()):
                return True
            stack.extend(adjacency.get(current, set()))
        return False

    def approved_dependents(self, artefact_id) -> list[Artefact]:
        rows = self.session.query(Dependency).filter(
            Dependency.source_artefact_id == artefact_id,
            Dependency.status == "approved",
        ).all()
        return [
            artefact
            for row in rows
            if (artefact := self.session.get(Artefact, row.dependent_artefact_id)) is not None
        ]

    def _approved_adjacency(self) -> dict[object, set[object]]:
        adjacency: dict[object, set[object]] = {}
        for row in self.session.query(Dependency).filter(
            Dependency.status == "approved"
        ).all():
            adjacency.setdefault(row.source_artefact_id, set()).add(row.dependent_artefact_id)
        return adjacency
