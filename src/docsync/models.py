"""Durable application records for the approved modular monolith."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from docsync.db import Base


def uuid_value() -> uuid.UUID:
    return uuid.uuid4()


class Artefact(Base):
    __tablename__ = "artefacts"
    __table_args__ = (
        UniqueConstraint("source_system", "configured_scope", "external_id", name="uq_artefact_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_value)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    artefact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    configured_scope: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    owner_account_id: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str | None] = mapped_column(String(255))
    content_digest: Mapped[str | None] = mapped_column(String(128))
    last_detected_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(String(32))
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Dependency(Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint("source_artefact_id", "dependent_artefact_id", "relationship_type", name="uq_dependency"),
        CheckConstraint("source_artefact_id <> dependent_artefact_id", name="ck_dependency_no_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_value)
    source_artefact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artefacts.id", ondelete="RESTRICT"), nullable=False)
    dependent_artefact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artefacts.id", ondelete="RESTRICT"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("source_system", "source_event_id", name="uq_event_source"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_value)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("operation_type", "operation_id", name="uq_job_operation"),
        Index("ix_jobs_status_claim", "status", "lease_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_value)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_value)
    artefact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artefacts.id", ondelete="RESTRICT"), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    content_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    before_content: Mapped[str] = mapped_column(Text, nullable=False)
    after_content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("artefact_id", "revision", "content_digest", name="uq_proposal_revision"),)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_value)
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id", ondelete="RESTRICT"), nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    exact_content_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[str] = mapped_column(String(255), nullable=False)
    target_version: Mapped[str] = mapped_column(String(255), nullable=False)
    action_target: Mapped[str] = mapped_column(String(255), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditRecord(Base):
    __tablename__ = "audit_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_value)
    actor_account_id: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    source_artefact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artefacts.id", ondelete="SET NULL"))
    target_artefact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artefacts.id", ondelete="SET NULL"))
    source_version: Mapped[str | None] = mapped_column(String(255))
    target_version: Mapped[str | None] = mapped_column(String(255))
    content_digest: Mapped[str | None] = mapped_column(String(128))
    before_content: Mapped[str | None] = mapped_column(Text)
    after_content: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OwnerMapping(Base):
    __tablename__ = "owner_mappings"
    __table_args__ = (
        UniqueConstraint("artefact_id", "account_id", "role", name="uq_owner_mapping"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_value)
    artefact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artefacts.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    delegate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MirrorMapping(Base):
    __tablename__ = "mirror_mappings"
    __table_args__ = (
        UniqueConstraint("source_artefact_id", "target_artefact_id", name="uq_mirror_mapping"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_value)
    source_artefact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artefacts.id", ondelete="RESTRICT"), nullable=False)
    target_artefact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artefacts.id", ondelete="RESTRICT"), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(255))
    target_version: Mapped[str | None] = mapped_column(String(255))
    source_digest: Mapped[str | None] = mapped_column(String(128))
    target_digest: Mapped[str | None] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
