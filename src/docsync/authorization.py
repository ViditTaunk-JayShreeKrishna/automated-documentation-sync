"""Role and ownership authorization; native identity verification is required externally."""

from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session

from docsync.models import AuditRecord, OwnerMapping


class Role(str, Enum):
    ADMINISTRATOR = "administrator"
    PROJECT_MEMBER = "project_member"
    DOCUMENT_OWNER = "document_owner"
    DESIGNATED_REVIEWER = "designated_reviewer"
    SERVICE_ACCOUNT = "service_account"


class AuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class AuthenticatedIdentity:
    account_id: str
    native_verified: bool
    roles: frozenset[Role] = field(default_factory=frozenset)

    def can_act_as(self, role: Role) -> bool:
        return self.native_verified and role in self.roles


def require_role(identity: AuthenticatedIdentity, role: Role) -> None:
    if not identity.native_verified:
        raise AuthorizationError("Identity is not native-provider verified")
    if role not in identity.roles:
        raise AuthorizationError(f"Identity lacks required role: {role.value}")


def require_document_authority(
    session: Session,
    identity: AuthenticatedIdentity,
    artefact_id,
    action: str,
) -> None:
    if not identity.native_verified:
        raise AuthorizationError("Identity is not native-provider verified")
    mapping = session.query(OwnerMapping).filter(
        OwnerMapping.artefact_id == artefact_id,
        OwnerMapping.account_id == identity.account_id,
        OwnerMapping.active.is_(True),
        OwnerMapping.role.in_([Role.DOCUMENT_OWNER.value, Role.DESIGNATED_REVIEWER.value]),
    ).first()
    if mapping is None:
        raise AuthorizationError(
            f"Unknown or unauthorized document mapping for action: {action}"
        )


def change_owner_mapping(
    session: Session,
    administrator: AuthenticatedIdentity,
    artefact_id,
    account_id: str,
    role: Role,
    delegate: bool,
    active: bool,
) -> OwnerMapping:
    require_role(administrator, Role.ADMINISTRATOR)
    mapping = session.query(OwnerMapping).filter(
        OwnerMapping.artefact_id == artefact_id,
        OwnerMapping.account_id == account_id,
        OwnerMapping.role == role.value,
    ).first()
    if mapping is None:
        mapping = OwnerMapping(
            artefact_id=artefact_id,
            account_id=account_id,
            role=role.value,
            delegate=delegate,
            active=active,
            created_by=administrator.account_id,
        )
        session.add(mapping)
    else:
        mapping.delegate = delegate
        mapping.active = active
    session.flush()
    session.add(AuditRecord(
        actor_account_id=administrator.account_id,
        action="owner_mapping_change",
        target_artefact_id=artefact_id,
        outcome="recorded",
        details={
            "account_id": account_id,
            "role": role.value,
            "delegate": delegate,
            "active": active,
        },
    ))
    session.commit()
    return mapping
