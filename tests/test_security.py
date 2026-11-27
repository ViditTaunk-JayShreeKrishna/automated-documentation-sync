import logging

import pytest

from docsync.security import (
    RedactingFilter,
    SensitiveDataError,
    redact_mapping,
    redact_text,
    screen_sensitive_text,
)


def test_redact_secret_and_personal_text() -> None:
    text = "Authorization: Bearer abc.def secret=password"
    redacted = redact_text(text)
    assert "abc.def" not in redacted
    assert "password" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_mapping_is_recursive() -> None:
    value = redact_mapping({
        "api_token": "top-secret",
        "nested": {"body": "owner@example.com"},
    })
    assert value["api_token"] == "[REDACTED]"
    assert value["nested"]["body"] == "[REDACTED]"


@pytest.mark.parametrize(
    "text",
    [
        "password=plain-secret",
        "Bearer eyJhbGciOiJIUzI1NiJ9.payload",
        "Contact owner@example.com",
        "Card 4111 1111 1111 1111",
    ],
)
def test_sensitive_screening_rejects_disallowed_text(text: str) -> None:
    with pytest.raises(SensitiveDataError):
        screen_sensitive_text(text)


def test_sensitive_screening_accepts_authorized_project_text() -> None:
    assert screen_sensitive_text("Requirements changed FR-001") == "Requirements changed FR-001"


def test_log_filter_redacts_record_and_extra_secrets() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "Using token=example-secret",
        (),
        None,
    )
    log_filter = RedactingFilter(["extra-value"])
    assert log_filter.filter(record)
    assert "example-secret" not in str(record.msg)
    assert "[REDACTED]" in str(record.msg)
