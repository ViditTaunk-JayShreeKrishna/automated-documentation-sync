"""Validated configuration for the initial project scope."""

import math
import os
import sys
from dataclasses import dataclass, field
from typing import Mapping

from pydantic import SecretStr


class ConfigurationError(ValueError):
    """A configuration value is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    environment: str
    jira_project: str
    github_repository: str
    github_branch: str
    confluence_space: str
    reconciliation_seconds: int
    max_retries: int
    retry_backoff_seconds: float
    jira_access_token: SecretStr = field(repr=False)
    github_access_token: SecretStr = field(repr=False)
    confluence_access_token: SecretStr = field(repr=False)


def _integer(env: Mapping[str, str], name: str, default: str) -> int:
    try:
        return int(env.get(name, default))
    except ValueError:
        raise ConfigurationError(f"{name} must be an integer") from None


def _positive_number(env: Mapping[str, str], name: str, default: str) -> float:
    try:
        value = float(env.get(name, default))
    except ValueError:
        raise ConfigurationError(f"{name} must be a positive finite number") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f"{name} must be a positive finite number")
    return value


def _secret(env: Mapping[str, str], name: str) -> SecretStr:
    value = env.get(name)
    if value is None or not value.strip():
        raise ConfigurationError(f"{name} is required")
    return SecretStr(value)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Load environment-only settings without including values in errors."""
    if env is None:
        env = os.environ

    environment = env.get("DOCSYNC_ENVIRONMENT", "development")
    if environment not in {"development", "test", "production"}:
        raise ConfigurationError("DOCSYNC_ENVIRONMENT must be development, test or production")

    scope = {
        "DOCSYNC_JIRA_PROJECT": "KAN",
        "DOCSYNC_GITHUB_REPOSITORY": "ViditTaunk-JayShreeKrishna/automated-documentation-sync",
        "DOCSYNC_GITHUB_BRANCH": "feature/automated-documentation-sync",
        "DOCSYNC_CONFLUENCE_SPACE": "ADS",
    }
    for name, approved_value in scope.items():
        if env.get(name, approved_value) != approved_value:
            raise ConfigurationError(
                f"{name} is outside the initial approved scope; audited scope changes are not implemented"
            )

    interval = _integer(env, "DOCSYNC_RECONCILIATION_SECONDS", "900")
    if interval <= 0:
        raise ConfigurationError("DOCSYNC_RECONCILIATION_SECONDS must be greater than zero")
    retries = _integer(env, "DOCSYNC_MAX_RETRIES", "3")
    if not 0 <= retries <= 3:
        raise ConfigurationError("DOCSYNC_MAX_RETRIES must be between zero and three")
    backoff = _positive_number(env, "DOCSYNC_RETRY_BACKOFF_SECONDS", "1")

    return Settings(
        environment=environment,
        jira_project=scope["DOCSYNC_JIRA_PROJECT"],
        github_repository=scope["DOCSYNC_GITHUB_REPOSITORY"],
        github_branch=scope["DOCSYNC_GITHUB_BRANCH"],
        confluence_space=scope["DOCSYNC_CONFLUENCE_SPACE"],
        reconciliation_seconds=interval,
        max_retries=retries,
        retry_backoff_seconds=backoff,
        jira_access_token=_secret(env, "DOCSYNC_JIRA_ACCESS_TOKEN"),
        github_access_token=_secret(env, "DOCSYNC_GITHUB_ACCESS_TOKEN"),
        confluence_access_token=_secret(env, "DOCSYNC_CONFLUENCE_ACCESS_TOKEN"),
    )


def require_settings() -> Settings:
    try:
        return load_settings()
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(1) from None


def main() -> None:
    require_settings()
    print("Configuration is valid; integration permissions have not been verified.")


if __name__ == "__main__":
    main()
