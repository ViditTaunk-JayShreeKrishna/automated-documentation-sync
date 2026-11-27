from dataclasses import asdict

import pytest

from docsync.config import ConfigurationError, load_settings


ATLASSIAN_CLOUD_ID = "3aaf5522-6248-468c-88ca-9546e0d58a6d"


@pytest.fixture
def env() -> dict[str, str]:
    return {
        "DOCSYNC_JIRA_ACCESS_TOKEN": "jira-test-secret",
        "DOCSYNC_GITHUB_ACCESS_TOKEN": "github-test-secret",
        "DOCSYNC_CONFLUENCE_ACCESS_TOKEN": "confluence-test-secret",
        "DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL": "test@example.invalid",
        "DOCSYNC_ATLASSIAN_CLOUD_ID": ATLASSIAN_CLOUD_ID,
    }


def test_defaults_and_redacted_representation(env: dict[str, str]) -> None:
    settings = load_settings(env)
    assert settings.reconciliation_seconds == 900
    assert settings.max_retries == 3
    assert settings.github_branch == "feature/automated-documentation-sync"
    assert settings.jira_base_url == f"https://api.atlassian.com/ex/jira/{ATLASSIAN_CLOUD_ID}"
    assert settings.github_api_base_url == "https://api.github.com"
    assert settings.confluence_base_url == (
        f"https://api.atlassian.com/ex/confluence/{ATLASSIAN_CLOUD_ID}"
    )
    sensitive_values = [
        env["DOCSYNC_JIRA_ACCESS_TOKEN"],
        env["DOCSYNC_GITHUB_ACCESS_TOKEN"],
        env["DOCSYNC_CONFLUENCE_ACCESS_TOKEN"],
        env["DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL"],
    ]
    assert all(value not in repr(settings) for value in sensitive_values)
    assert all(value not in repr(asdict(settings)) for value in sensitive_values)


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


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_environment_selection(env: dict[str, str], environment: str) -> None:
    env["DOCSYNC_ENVIRONMENT"] = environment
    if environment == "production":
        env["DOCSYNC_DATABASE_URL"] = "postgresql+psycopg://user:password@localhost/docsync"
    assert load_settings(env).environment == environment


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DOCSYNC_JIRA_PROJECT", "OTHER"),
        ("DOCSYNC_GITHUB_REPOSITORY", "other/repo"),
        ("DOCSYNC_GITHUB_BRANCH", "main"),
        ("DOCSYNC_CONFLUENCE_SPACE", "OTHER"),
        ("DOCSYNC_ENVIRONMENT", "invalid"),
        ("DOCSYNC_ATLASSIAN_CLOUD_ID", "not-a-cloud-id"),
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


@pytest.mark.parametrize(
    "name",
    ["DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL", "DOCSYNC_ATLASSIAN_CLOUD_ID"],
)
def test_missing_atlassian_configuration_fails_closed(
    env: dict[str, str], name: str
) -> None:
    del env[name]
    with pytest.raises(ConfigurationError, match=name):
        load_settings(env)


def test_loads_local_dotenv_without_overriding_process_environment(
    tmp_path, monkeypatch
) -> None:
    keys = {
        "DOCSYNC_JIRA_ACCESS_TOKEN",
        "DOCSYNC_GITHUB_ACCESS_TOKEN",
        "DOCSYNC_CONFLUENCE_ACCESS_TOKEN",
        "DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL",
        "DOCSYNC_ATLASSIAN_CLOUD_ID",
    }
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DOCSYNC_JIRA_ACCESS_TOKEN=dotenv-jira-secret",
                "DOCSYNC_GITHUB_ACCESS_TOKEN=dotenv-github-secret",
                "DOCSYNC_CONFLUENCE_ACCESS_TOKEN=dotenv-confluence-secret",
                "DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL=dotenv@example.invalid",
                f"DOCSYNC_ATLASSIAN_CLOUD_ID={ATLASSIAN_CLOUD_ID}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DOCSYNC_JIRA_PROJECT", "KAN")

    settings = load_settings()

    assert settings.atlassian_cloud_id == ATLASSIAN_CLOUD_ID
    assert settings.jira_access_token.get_secret_value() == "dotenv-jira-secret"
    assert settings.atlassian_account_email.get_secret_value() == "dotenv@example.invalid"
    monkeypatch.setenv("DOCSYNC_JIRA_ACCESS_TOKEN", "process-jira-secret")
    assert load_settings().jira_access_token.get_secret_value() == "process-jira-secret"


def test_database_url_is_redacted(env: dict[str, str]) -> None:
    env["DOCSYNC_DATABASE_URL"] = "postgresql+psycopg://user:password@localhost/db"
    settings = load_settings(env)
    assert "password" not in repr(settings)
    assert "password" not in repr(asdict(settings))


def test_production_requires_explicit_database_url(env: dict[str, str]) -> None:
    env["DOCSYNC_ENVIRONMENT"] = "production"
    env.pop("DOCSYNC_DATABASE_URL", None)
    with pytest.raises(ConfigurationError, match="DOCSYNC_DATABASE_URL"):
        load_settings(env)


def test_production_requires_tls(env: dict[str, str]) -> None:
    env.update(
        DOCSYNC_ENVIRONMENT="production",
        DOCSYNC_DATABASE_URL="postgresql+psycopg://user:password@db.example/docsync",
        DOCSYNC_REQUIRE_TLS="false",
    )
    with pytest.raises(ConfigurationError, match="DOCSYNC_REQUIRE_TLS"):
        load_settings(env)


def test_invalid_tls_setting_fails_closed(env: dict[str, str]) -> None:
    env["DOCSYNC_REQUIRE_TLS"] = "sometimes"
    with pytest.raises(ConfigurationError, match="DOCSYNC_REQUIRE_TLS"):
        load_settings(env)
