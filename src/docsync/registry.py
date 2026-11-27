"""Authorized artefact registration and discovery primitives."""

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from docsync.authorization import AuthenticatedIdentity, AuthorizationError, Role, require_role
from docsync.models import Artefact, AuditRecord, MirrorMapping


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ArtefactRecord:
    id: object
    name: str
    artefact_type: str
    source_system: str
    configured_scope: str
    external_id: str
    location: str | None
    owner_account_id: str | None
    version: str | None
    content_digest: str | None
    related_document_ids: tuple[str, ...]
    last_sync_status: str | None


class ArtefactRegistry:
    def __init__(self, session: Session) -> None:
        self.session = session

    def register(
        self,
        identity: AuthenticatedIdentity,
        *,
        name: str,
        artefact_type: str,
        source_system: str,
        configured_scope: str,
        external_id: str,
        location: str | None = None,
        owner_account_id: str | None = None,
        version: str | None = None,
        content_digest: str | None = None,
        related_document_ids: Iterable[str] = (),
        discovery_evidence: dict | None = None,
    ) -> Artefact:
        require_role(identity, Role.ADMINISTRATOR)
        if not name.strip() or not artefact_type.strip() or not external_id.strip():
            raise RegistryError("Name, artefact type and external identity are required")
        artefact = Artefact(
            name=name,
            artefact_type=artefact_type,
            source_system=source_system,
            configured_scope=configured_scope,
            external_id=external_id,
            location=location,
            owner_account_id=owner_account_id,
            version=version,
            content_digest=content_digest,
            metadata_={
                "related_document_ids": list(related_document_ids),
                "discovery_evidence": discovery_evidence or {},
            },
        )
        self.session.add(artefact)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            raise RegistryError("A registered artefact with this scoped identity already exists") from None
        self.session.add(AuditRecord(
            actor_account_id=identity.account_id,
            action="artefact_register",
            target_artefact_id=artefact.id,
            source_version=version,
            target_version=version,
            content_digest=content_digest,
            outcome="recorded",
            details={"source_system": source_system, "external_id": external_id},
        ))
        self.session.commit()
        return artefact

    def confirmed_move(
        self,
        identity: AuthenticatedIdentity,
        artefact: Artefact,
        *,
        name: str | None = None,
        location: str | None = None,
    ) -> Artefact:
        require_role(identity, Role.ADMINISTRATOR)
        if name is not None:
            artefact.name = name
        if location is not None:
            artefact.location = location
        self.session.add(AuditRecord(
            actor_account_id=identity.account_id,
            action="artefact_move",
            target_artefact_id=artefact.id,
            source_version=artefact.version,
            target_version=artefact.version,
            outcome="recorded",
            details={"name": artefact.name, "location": artefact.location},
        ))
        self.session.commit()
        return artefact

    def require_owner(
        self,
        artefact: Artefact,
    ) -> str:
        if not artefact.owner_account_id:
            raise AuthorizationError("Unknown document owner blocks owner-dependent actions")
        return artefact.owner_account_id

    def add_mirror(
        self,
        identity: AuthenticatedIdentity,
        source: Artefact,
        target: Artefact,
    ) -> MirrorMapping:
        require_role(identity, Role.ADMINISTRATOR)
        mapping = MirrorMapping(
            source_artefact_id=source.id,
            target_artefact_id=target.id,
            source_version=source.version,
            target_version=target.version,
            source_digest=source.content_digest,
            target_digest=target.content_digest,
            active=True,
        )
        self.session.add(mapping)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            raise RegistryError("This mirror mapping is already registered") from None
        self.session.commit()
        return mapping
