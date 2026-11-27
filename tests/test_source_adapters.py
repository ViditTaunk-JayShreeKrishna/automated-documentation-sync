import base64
from io import BytesIO
from urllib.error import HTTPError

import pytest

from docsync.config import load_settings
from docsync.source_adapters import (
    ConfluenceSourceAdapter,
    GitHubSourceAdapter,
    JiraSourceAdapter,
    SourcePage,
    SourcePermissionError,
    SourceReadError,
    SourceRecord,
    SourceUnsupportedError,
    _JsonClient,
)


def settings():
    return load_settings(
        {
            "DOCSYNC_JIRA_ACCESS_TOKEN": "jira-secret",
            "DOCSYNC_GITHUB_ACCESS_TOKEN": "github-secret",
            "DOCSYNC_CONFLUENCE_ACCESS_TOKEN": "confluence-secret",
            "DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL": "test@example.invalid",
            "DOCSYNC_ATLASSIAN_CLOUD_ID": "3aaf5522-6248-468c-88ca-9546e0d58a6d",
        }
    )


class StubClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, path, params=None):
        self.requests.append((path, params))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_jira_issue_search_preserves_identity_version_links_and_pagination():
    client = StubClient(
        [
            {
                "isLast": False,
                "nextPageToken": "jira-cursor-1",
                "issues": [
                    {
                        "id": "10001",
                        "key": "KAN-1",
                        "self": "https://jira.example/issue/10001",
                        "fields": {
                            "summary": "Story",
                            "updated": "2026-11-27T00:00:00.000+0000",
                            "issuelinks": [
                                {"outwardIssue": {"key": "KAN-2"}},
                                {"inwardIssue": {"key": "KAN-3"}},
                            ],
                            "status": {"name": "To Do"},
                        },
                    }
                ],
            }
        ]
    )
    adapter = JiraSourceAdapter(settings(), client)

    page = adapter.search_issues(page_size=1)

    assert isinstance(page, SourcePage)
    assert page.next_cursor == "jira-cursor-1"
    assert page.records == (
        SourceRecord(
            source="jira",
            id="10001",
            external_id="KAN-1",
            title="Story",
            version="2026-11-27T00:00:00.000+0000",
            url="https://jira.example/issue/10001",
            status="To Do",
            links=("KAN-2", "KAN-3"),
        ),
    )
    assert client.requests[0][1]["jql"].startswith("project = KAN")


def test_jira_issue_read_is_limited_to_approved_project():
    adapter = JiraSourceAdapter(settings(), StubClient([]))
    with pytest.raises(ValueError, match="approved Jira project"):
        adapter.read_issue("OTHER-1")
    with pytest.raises(ValueError, match="approved Jira project"):
        adapter.read_issue("KAN-not-a-number")


def test_jira_search_rejects_incomplete_pagination_metadata():
    adapter = JiraSourceAdapter(settings(), StubClient([{"isLast": False, "issues": []}]))
    with pytest.raises(SourceReadError, match="pagination cursor"):
        adapter.search_issues()


def test_github_file_listing_uses_commit_tree_identity():
    client = StubClient(
        [
            {"commit": {"sha": "commit-1"}},
            {
                "truncated": False,
                "tree": [
                    {
                        "type": "blob",
                        "path": "requirements.md",
                        "sha": "blob-1",
                        "url": "https://api.github.com/git/blobs/blob-1",
                    },
                    {"type": "tree", "path": "src", "sha": "tree-1"},
                ],
            },
        ]
    )
    page = GitHubSourceAdapter(settings(), client).list_files()

    assert page.next_cursor is None
    assert len(page.records) == 1
    assert page.records[0].external_id == "requirements.md"
    assert page.records[0].version == "blob-1"


def test_github_truncated_tree_fails_explicitly():
    client = StubClient([{"commit": {"sha": "commit-1"}}, {"truncated": True}])
    with pytest.raises(SourceUnsupportedError, match="truncated tree"):
        GitHubSourceAdapter(settings(), client).list_files()


def test_github_read_file_decodes_content_and_retains_blob_version():
    client = StubClient(
        [
            {
                "sha": "blob-2",
                "path": "docs/notes.txt",
                "html_url": "https://github.com/example/repo/blob/main/docs/notes.txt",
                "type": "file",
                "content": base64.b64encode(b"current content").decode("ascii"),
            }
        ]
    )
    record = GitHubSourceAdapter(settings(), client).read_file("docs/notes.txt")

    assert record.version == "blob-2"
    assert record.content == "current content"


def test_github_rejects_other_branch_and_environment_files():
    client = StubClient([])
    adapter = GitHubSourceAdapter(settings(), client)
    with pytest.raises(SourcePermissionError, match="tracked branch"):
        adapter.read_file("README.md", ref="main")
    for path in (".env", "nested/.env.production"):
        with pytest.raises(SourcePermissionError, match="environment file"):
            adapter.read_file(path)
    assert not client.requests


def test_github_listing_excludes_environment_files():
    client = StubClient(
        [
            {"commit": {"sha": "commit-1"}},
            {
                "truncated": False,
                "tree": [
                    {"type": "blob", "path": ".env", "sha": "a"},
                    {"type": "blob", "path": "nested/.env.production", "sha": "b"},
                    {"type": "blob", "path": "README.md", "sha": "c"},
                ],
            },
        ]
    )
    page = GitHubSourceAdapter(settings(), client).list_files()
    assert [record.external_id for record in page.records] == ["README.md"]


def test_confluence_page_listing_returns_cursor_and_version():
    client = StubClient(
        [
            {"results": [{"id": "491547", "key": "ADS"}]},
            {
                "results": [
                    {
                        "id": "294927",
                        "title": "Implementation",
                        "status": "current",
                        "version": {"number": 10},
                        "_links": {"webui": "/spaces/ADS/pages/294927"},
                    }
                ],
                "_links": {"next": "/wiki/api/v2/pages?cursor=cursor-2"},
            },
            {"results": [{"id": "491547", "key": "ADS"}]},
            {
                "results": [
                    {
                        "id": "294928",
                        "title": "Other",
                        "version": {"number": 2},
                        "_links": {},
                    }
                ],
                "_links": {},
            },
        ]
    )
    adapter = ConfluenceSourceAdapter(settings(), client)

    first = adapter.list_pages(limit=1)
    second = adapter.list_pages(cursor=first.next_cursor, limit=1)

    assert first.next_cursor == "cursor-2"
    assert first.records[0].id == "294927"
    assert first.records[0].version == "10"
    assert second.next_cursor is None
    assert client.requests[3][1]["cursor"] == "cursor-2"


def test_confluence_page_read_returns_storage_content_and_revision():
    client = StubClient(
        [
            {"results": [{"id": "491547", "key": "ADS"}]},
            {"id": "294927", "spaceId": "491547"},
            {
                "id": "294927",
                "spaceId": "491547",
                "title": "Implementation",
                "status": "current",
                "version": {"number": 10},
                "_links": {"webui": "/spaces/ADS/pages/294927"},
                "body": {"storage": {"value": "<p>Body</p>"}},
            }
        ]
    )
    record = ConfluenceSourceAdapter(settings(), client).read_page("294927")

    assert record.id == "294927"
    assert record.version == "10"
    assert record.content == "<p>Body</p>"


def test_confluence_page_read_propagates_missing_scope_as_permission_error():
    client = StubClient([
        {"results": [{"id": "491547", "key": "ADS"}]},
        SourcePermissionError("confluence source access denied (HTTP 401)"),
    ])
    with pytest.raises(SourcePermissionError, match="access denied"):
        ConfluenceSourceAdapter(settings(), client).read_page("294927")


def test_confluence_page_rejects_other_space_before_requesting_body():
    client = StubClient([
        {"results": [{"id": "491547", "key": "ADS"}]},
        {"id": "294927", "spaceId": "999"},
    ])
    with pytest.raises(SourcePermissionError, match="configured Confluence space"):
        ConfluenceSourceAdapter(settings(), client).read_page("294927")
    assert len(client.requests) == 2
    assert client.requests[1][1] is None


def test_confluence_page_rejects_move_between_metadata_and_body_reads():
    client = StubClient([
        {"results": [{"id": "491547", "key": "ADS"}]},
        {"id": "294927", "spaceId": "491547"},
        {"id": "294927", "spaceId": "999", "body": {"storage": {"value": "private"}}},
    ])
    with pytest.raises(SourcePermissionError, match="configured Confluence space"):
        ConfluenceSourceAdapter(settings(), client).read_page("294927")


def test_atlassian_scoped_token_uses_basic_auth_and_redacts_auth_failures(
    monkeypatch,
):
    client = _JsonClient(
        "jira",
        "https://api.atlassian.com/ex/jira/cloud-id",
        "token-value",
        "user@example.invalid",
    )
    expected = "Basic " + base64.b64encode(
        b"user@example.invalid:token-value"
    ).decode("ascii")
    assert client.headers["Authorization"] == expected

    github = _JsonClient("github", "https://api.github.com", "fine-grained-token")
    assert github.headers["Authorization"] == "Bearer fine-grained-token"
    assert github.headers["X-GitHub-Api-Version"] == "2022-11-28"

    def deny(request, timeout):
        raise HTTPError(
            request.full_url, 401, "Unauthorized", {}, None
        )

    monkeypatch.setattr("docsync.source_adapters.urlopen", deny)
    with pytest.raises(SourcePermissionError) as error:
        client.get("/rest/api/3/project/KAN")
    assert "token-value" not in str(error.value)


def test_confluence_page_scope_401_is_classified_without_exposing_provider_body(
    monkeypatch,
):
    client = _JsonClient(
        "confluence",
        "https://api.atlassian.com/ex/confluence/cloud-id",
        "token-value",
        "user@example.invalid",
    )
    provider_error = b'{"message":"Unauthorized; scope does not match"}'

    def deny(request, timeout):
        raise HTTPError(
            request.full_url, 401, "Unauthorized", {}, BytesIO(provider_error)
        )

    monkeypatch.setattr("docsync.source_adapters.urlopen", deny)
    with pytest.raises(SourcePermissionError, match="HTTP 401") as error:
        client.get("/wiki/api/v2/pages/294927")

    assert "token-value" not in str(error.value)
    assert "scope does not match" not in str(error.value)
