import pytest

from docsync.ai import AIIntegrationError, ContextItem, SectionChange, generate_proposal
from docsync.security import SensitiveDataError


class Provider:
    provider_id = "test-provider"

    def __init__(self):
        self.calls = 0
        self.response = {
            "summary": "Update architecture",
            "reason": "Requirement changed",
            "document": "Architecture",
            "document_link": "https://example.invalid/architecture",
            "sections": [{"section": "Scope", "before": "old", "after": "new"}],
            "sources": ["KAN-1"],
            "assumptions": [],
        }

    def propose(self, context):
        self.calls += 1
        return self.response


class Allow:
    def permits(self, value):
        return True


class Deny:
    def permits(self, value):
        return False


@pytest.fixture
def context():
    return (ContextItem("jira", "KAN-1", "3", "A requirement changed"),)


def test_generation_requires_independent_verification_before_provider_call(context):
    provider = Provider()
    with pytest.raises(AIIntegrationError):
        generate_proposal(provider, context)
    for controls in (
        {"policy": Deny(), "authorizer": Allow(), "classifier": Allow()},
        {"policy": Allow(), "authorizer": Deny(), "classifier": Allow()},
        {"policy": Allow(), "authorizer": Allow(), "classifier": Deny()},
    ):
        with pytest.raises(AIIntegrationError):
            generate_proposal(provider, context, **controls)
    assert provider.calls == 0


def test_environment_files_and_sensitive_context_never_reach_provider(context):
    provider = Provider()
    controls = {"policy": Allow(), "authorizer": Allow(), "classifier": Allow()}
    with pytest.raises(AIIntegrationError):
        generate_proposal(provider, (ContextItem("github", "project\\.env.local", "3", "content"),), **controls)
    with pytest.raises(SensitiveDataError):
        generate_proposal(provider, (ContextItem("jira", "KAN-1", "3", "token=abc"),), **controls)
    assert provider.calls == 0


def test_validated_draft_is_unapproved_and_preserves_sections(context):
    provider = Provider()
    draft = generate_proposal(provider, context, policy=Allow(), authorizer=Allow(), classifier=Allow())
    assert provider.calls == 1
    assert draft.sections[0].before == "old"
    assert draft.sections[0].after == "new"
    assert not hasattr(draft, "approved")


@pytest.mark.parametrize(
    "change",
    [
        {"approved": True},
        {"sources": []},
        {"sections": [{"section": "Scope", "before": "same", "after": "same"}]},
        {"summary": " "},
    ],
)
def test_invalid_or_approval_shaped_output_is_rejected(context, change):
    provider = Provider()
    provider.response.update(change)
    with pytest.raises(AIIntegrationError, match="response is invalid"):
        generate_proposal(provider, context, policy=Allow(), authorizer=Allow(), classifier=Allow())


def test_sensitive_provider_output_is_rejected(context):
    provider = Provider()
    provider.response["summary"] = "token=do-not-expose"
    with pytest.raises(SensitiveDataError):
        generate_proposal(provider, context, policy=Allow(), authorizer=Allow(), classifier=Allow())


def test_constructed_unvalidated_section_is_revalidated(context):
    provider = Provider()
    provider.response["sections"] = [SectionChange.model_construct(section="Scope", before="same", after="same")]
    with pytest.raises(AIIntegrationError, match="response is invalid"):
        generate_proposal(provider, context, policy=Allow(), authorizer=Allow(), classifier=Allow())
