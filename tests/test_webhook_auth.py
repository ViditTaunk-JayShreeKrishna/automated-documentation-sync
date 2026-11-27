import pytest

from docsync.webhook_auth import WebhookAuthenticationError, verify_hmac_sha256


@pytest.mark.parametrize(
    ("body", "signature"),
    [
        (
            b"Hello, World!",
            "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17",
        ),
        (
            b"Hello World!",
            "sha256=a4771c39fbe90f317c7824e83ddef3caae9cb3d976c214ace1f2937e133263c9",
        ),
    ],
)
def test_github_and_jira_published_signature_vectors(body, signature):
    verify_hmac_sha256(body, b"It's a Secret to Everybody", signature)


@pytest.mark.parametrize(
    "signature",
    [None, "", "sha1=" + "a" * 40, "sha256=" + "a" * 63, "sha256=" + "é" * 64],
)
def test_missing_or_malformed_signature_is_rejected(signature):
    with pytest.raises(WebhookAuthenticationError, match="missing or malformed"):
        verify_hmac_sha256(b"payload", b"fixture-secret", signature)


def test_tampered_body_and_missing_secret_are_rejected_without_exposing_secret():
    signature = "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17"
    with pytest.raises(WebhookAuthenticationError, match="invalid") as error:
        verify_hmac_sha256(b"tampered", b"It's a Secret to Everybody", signature)
    assert "It's a Secret to Everybody" not in str(error.value)
    with pytest.raises(WebhookAuthenticationError, match="not configured"):
        verify_hmac_sha256(b"payload", b"", signature)
