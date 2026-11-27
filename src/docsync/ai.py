"""Provider-independent proposal boundary; no runtime provider is configured."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from docsync.security import screen_sensitive_text


class AIIntegrationError(ValueError):
    """AI generation cannot safely proceed."""


@dataclass(frozen=True)
class ContextItem:
    source_system: str
    external_id: str
    version: str
    content: str


class AIProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def propose(self, context: tuple[ContextItem, ...]) -> object: ...


class ProviderPolicyVerifier(Protocol):
    def permits(self, provider_id: str) -> bool: ...


class ContextAuthorizer(Protocol):
    def permits(self, item: ContextItem) -> bool: ...


class SafetyClassifier(Protocol):
    def permits(self, text: str) -> bool: ...


class SectionChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")

    section: str = Field(min_length=1)
    before: str
    after: str

    @model_validator(mode="after")
    def check_change(self):
        if not self.section.strip() or self.before == self.after:
            raise ValueError("A section and actual change are required")
        return self


class ProposalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")

    summary: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    document: str = Field(min_length=1)
    document_link: str = Field(min_length=1)
    sections: list[SectionChange] = Field(min_length=1)
    sources: list[str] = Field(min_length=1)
    assumptions: list[str]

    @field_validator("summary", "reason", "document", "document_link")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A nonblank value is required")
        return value

    @field_validator("sources", "assumptions")
    @classmethod
    def require_nonblank_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Items must not be blank")
        return values


def _screen(text: str, classifier: SafetyClassifier) -> None:
    screen_sensitive_text(text)
    if classifier.permits(text) is not True:
        raise AIIntegrationError("Content safety could not be established")


def generate_proposal(
    provider: AIProvider,
    context: tuple[ContextItem, ...],
    *,
    policy: ProviderPolicyVerifier | None = None,
    authorizer: ContextAuthorizer | None = None,
    classifier: SafetyClassifier | None = None,
) -> ProposalDraft:
    """Generate an unapproved draft only after independent, trusted checks."""
    if policy is None or authorizer is None or classifier is None:
        raise AIIntegrationError("Provider policy, context authorization and safety checks are required")
    if not provider.provider_id.strip() or policy.permits(provider.provider_id) is not True:
        raise AIIntegrationError("Provider data-handling policy is not verified")
    if not context:
        raise AIIntegrationError("Authorized project context is required")
    for item in context:
        if not item.source_system.strip() or not item.external_id.strip() or not item.version.strip():
            raise AIIntegrationError("Context identity and version are required")
        parts = item.external_id.replace("\\", "/").lower().split("/")
        if any(part == ".env" or part.startswith(".env.") for part in parts):
            raise AIIntegrationError("Environment files are not allowed")
        if authorizer.permits(item) is not True:
            raise AIIntegrationError("Context is unauthorized or irrelevant")
        for value in (item.source_system, item.external_id, item.version, item.content):
            _screen(value, classifier)
    response = provider.propose(context)
    try:
        draft = ProposalDraft.model_validate(response)
    except ValidationError:
        raise AIIntegrationError("Provider response is invalid") from None
    for value in (
        draft.summary, draft.reason, draft.document, draft.document_link,
        *draft.sources, *draft.assumptions,
        *(text for section in draft.sections for text in (section.section, section.before, section.after)),
    ):
        _screen(value, classifier)
    return draft
