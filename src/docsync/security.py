"""Security screening and structured-log redaction helpers."""

import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any


SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:password|passwd|token|secret|api[_-]?key)\b\s*[:=]\s*[^\s,]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]+"),
)

PERSONAL_PATTERNS = (
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
)


class SensitiveDataError(ValueError):
    pass


def redact_text(value: str, replacement: str = "[REDACTED]") -> str:
    redacted = value
    for pattern in SECRET_PATTERNS + PERSONAL_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values.items():
        if re.search(r"(?i)(password|passwd|token|secret|api[_-]?key|credential)", key):
            result[key] = "[REDACTED]"
        elif isinstance(value, Mapping):
            result[key] = redact_mapping(value)
        elif isinstance(value, str):
            result[key] = redact_text(value)
        else:
            result[key] = value
    return result


def screen_sensitive_text(text: str) -> str:
    if not text or not text.strip():
        return text
    for pattern in SECRET_PATTERNS + PERSONAL_PATTERNS:
        if pattern.search(text):
            raise SensitiveDataError("Sensitive or secret data is not allowed in AI or audit text")
    return text


class RedactingFilter(logging.Filter):
    def __init__(self, additional_secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self.additional_secrets = tuple(secret for secret in additional_secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(str(record.msg))
        for secret in self.additional_secrets:
            record.msg = str(record.msg).replace(secret, "[REDACTED]")
        if isinstance(record.args, dict):
            record.args = redact_mapping(record.args)
        return True
