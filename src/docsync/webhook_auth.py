"""Authentication primitives for source webhooks; no receiver is enabled."""

import hashlib
import hmac
import re


class WebhookAuthenticationError(ValueError):
    """A webhook could not be authenticated."""


def verify_hmac_sha256(body: bytes, secret: bytes, signature: str | None) -> None:
    """Verify a Jira or GitHub HMAC header against the original request bytes."""
    if not secret:
        raise WebhookAuthenticationError("Webhook secret is not configured")
    if signature is None or re.fullmatch(r"sha256=[0-9a-f]{64}", signature) is None:
        raise WebhookAuthenticationError("Webhook signature is missing or malformed")
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise WebhookAuthenticationError("Webhook signature is invalid")
