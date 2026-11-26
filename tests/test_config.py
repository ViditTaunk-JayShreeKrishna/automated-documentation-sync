from dataclasses import asdict

import pytest

from docsync.config import ConfigurationError, load_settings


@pytest.fixture
def env() -> dict[str, str]:
    return {
        "DOCSYNC_JIRA_ACCESS_TOKEN": "jira-test-secret",
        "DOCSYNC_GITHUB_ACCESS_TOKEN": "github-test-secret",
        "DOCSYNC_CONFLUENCE_ACCESS_TOKEN": "confluence-test-secret",
    }


def test_defaults_and_redacted_representation(env: dict[str, str]) -> None:
    settings = load_settings(env)
    assert settings.reconciliation_seconds == 900
    assert settings.max_retries == 3
    assert settings.github_branch == "feature/automated-documentation-sync"
    assert all(value not in repr(settings) for value in env.values())
    assert all(value not in repr(asdict(settings)) for value in env.values())


def test_overrides_within_safe_limits(env: dict[str, str]) -> None:
    env.update(
        DOCSYNC_ENVIRONMENT="test",
        DOCSYNC_RECONCILIATION_SECONDS="60",
        DOCSYNC_MAX_RETRIES="0",
        DOCSYNC_RETRY_BACKOFF_SECONDS="0.5",
    )
    settings = load_settings(env)
    assert (settings.environment, settings.reconciliation_seconds, settings.max_retries) == (
        "test",
        60,
        0,
    )
    assert settings.retry_backoff_seconds == 0.5


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DOCSYNC_JIRA_PROJECT", "OTHER"),
        ("DOCSYNC_GITHUB_REPOSITORY", "other/repo"),
        ("DOCSYNC_GITHUB_BRANCH", "main"),
        ("DOCSYNC_CONFLUENCE_SPACE", "OTHER"),
        ("DOCSYNC_ENVIRONMENT", "invalid"),
        ("DOCSYNC_RECONCILIATION_SECONDS", "0"),
        ("DOCSYNC_RECONCILIATION_SECONDS", "not-an-integer"),
        ("DOCSYNC_MAX_RETRIES", "4"),
        ("DOCSYNC_MAX_RETRIES", "-1"),
        ("DOCSYNC_RETRY_BACKOFF_SECONDS", "nan"),
        ("DOCSYNC_RETRY_BACKOFF_SECONDS", "inf"),
        ("DOCSYNC_RETRY_BACKOFF_SECONDS", "0"),
    ],
)
def test_invalid_values_fail_without_echoing_input(
    env: dict[str, str], name: str, value: str
) -> None:
    env[name] = value
    with pytest.raises(ConfigurationError) as error:
        load_settings(env)
    assert name in str(error.value)
    assert value not in str(error.value)


@pytest.mark.parametrize(
    "name",
    [
        "DOCSYNC_JIRA_ACCESS_TOKEN",
        "DOCSYNC_GITHUB_ACCESS_TOKEN",
        "DOCSYNC_CONFLUENCE_ACCESS_TOKEN",
    ],
)
def test_missing_secrets_fail_closed(env: dict[str, str], name: str) -> None:
    del env[name]
    with pytest.raises(ConfigurationError, match=name):
        load_settings(env)


def test_blank_secret_fails_closed(env: dict[str, str]) -> None:
    env["DOCSYNC_JIRA_ACCESS_TOKEN"] = "   "
    with pytest.raises(ConfigurationError, match="DOCSYNC_JIRA_ACCESS_TOKEN"):
        load_settings(env)
