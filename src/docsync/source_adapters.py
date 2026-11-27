"""Read-only, scoped adapters for the approved Jira, GitHub and Confluence sources."""

import base64
import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

from docsync.config import Settings


class SourceReadError(RuntimeError):
    """A source read failed without exposing request credentials or response bodies."""


class SourcePermissionError(SourceReadError):
    """The configured identity or token scope cannot read the requested source data."""


class SourceNotFoundError(SourceReadError):
    """The requested source resource does not exist or is not visible."""


class SourceTransientError(SourceReadError):
    """The source returned a retryable or transport-level failure."""


class SourceUnsupportedError(SourceReadError):
    """The source API cannot provide a complete result for the requested operation."""


@dataclass(frozen=True)
class SourceRecord:
    source: str
    id: str
    external_id: str
    title: str
    version: str
    url: str
    status: str | None = None
    links: tuple[str, ...] = ()
    content: Any = None


@dataclass(frozen=True)
class SourcePage:
    records: tuple[SourceRecord, ...]
    next_cursor: str | None


class JsonReader(Protocol):
    def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        ...


class _JsonClient:
    def __init__(
        self,
        source: str,
        base_url: str,
        token: str,
        account_email: str | None = None,
    ) -> None:
        self.source = source
        self.base_url = base_url.rstrip("/")
        if account_email is None:
            authorization = "Bearer " + token
        else:
            pair = f"{account_email}:{token}".encode("utf-8")
            authorization = "Basic " + base64.b64encode(pair).decode("ascii")
        self.headers = {"Accept": "application/json", "Authorization": authorization}
        if source == "github":
            self.headers["X-GitHub-Api-Version"] = "2022-11-28"

    def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        url = self.base_url + path
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers=self.headers)
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read()
        except HTTPError as error:
            if error.code in {401, 403}:
                raise SourcePermissionError(
                    f"{self.source} source access denied (HTTP {error.code})"
                ) from None
            if error.code == 404:
                raise SourceNotFoundError(
                    f"{self.source} source resource unavailable (HTTP 404)"
                ) from None
            if error.code in {408, 425, 429} or error.code >= 500:
                raise SourceTransientError(
                    f"{self.source} source temporarily unavailable (HTTP {error.code})"
                ) from None
            raise SourceReadError(
                f"{self.source} source request failed (HTTP {error.code})"
            ) from None
        except (URLError, TimeoutError):
            raise SourceTransientError(f"{self.source} source connection failed") from None
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise SourceReadError(f"{self.source} source returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise SourceReadError(f"{self.source} source returned an invalid response")
        return payload


def _client(settings: Settings, source: str) -> JsonReader:
    if source == "jira":
        return _JsonClient(
            source,
            settings.jira_base_url,
            settings.jira_access_token.get_secret_value(),
            settings.atlassian_account_email.get_secret_value(),
        )
    if source == "confluence":
        return _JsonClient(
            source,
            settings.confluence_base_url,
            settings.confluence_access_token.get_secret_value(),
            settings.atlassian_account_email.get_secret_value(),
        )
    return _JsonClient(
        source,
        settings.github_api_base_url,
        settings.github_access_token.get_secret_value(),
    )


class JiraSourceAdapter:
    def __init__(self, settings: Settings, client: JsonReader | None = None) -> None:
        self.settings = settings
        self.client = client or _client(settings, "jira")

    def read_project(self) -> dict[str, Any]:
        return self.client.get(f"/rest/api/3/project/{quote(self.settings.jira_project)}")

    def read_issue(self, issue_key: str) -> SourceRecord:
        project, separator, number = issue_key.partition("-")
        if project != self.settings.jira_project or not separator or not number.isdecimal():
            raise ValueError("Issue key is outside the approved Jira project")
        issue = self.client.get(
            f"/rest/api/3/issue/{quote(issue_key)}",
            {"fields": "summary,description,updated,issuelinks,status"},
        )
        return self._issue_record(issue)

    def search_issues(
        self, cursor: str | None = None, page_size: int = 50
    ) -> SourcePage:
        if not 1 <= page_size <= 100:
            raise ValueError("Jira pagination values are out of range")
        params = {
            "jql": f"project = {self.settings.jira_project} ORDER BY key ASC",
            "fields": "summary,description,updated,issuelinks,status",
            "maxResults": str(page_size),
        }
        if cursor:
            params["nextPageToken"] = cursor
        response = self.client.get("/rest/api/3/search/jql", params)
        issues = response.get("issues") or []
        is_last = response.get("isLast")
        next_cursor = response.get("nextPageToken")
        if not isinstance(is_last, bool):
            raise SourceReadError("Jira search response omitted pagination state")
        if not is_last and (not isinstance(next_cursor, str) or not next_cursor):
            raise SourceReadError("Jira search response omitted its pagination cursor")
        if is_last:
            next_cursor = None
        records = tuple(
            self._issue_record(issue)
            for issue in issues
        )
        return SourcePage(records, next_cursor)

    @staticmethod
    def _issue_record(issue: dict[str, Any]) -> SourceRecord:
        fields = issue.get("fields") or {}
        linked_keys = tuple(
            target["key"]
            for link in fields.get("issuelinks") or []
            for target in (link.get("inwardIssue"), link.get("outwardIssue"))
            if target and target.get("key")
        )
        status = fields.get("status") or {}
        return SourceRecord(
            source="jira",
            id=str(issue.get("id", "")),
            external_id=str(issue.get("key", "")),
            title=str(fields.get("summary", "")),
            version=str(fields.get("updated", "")),
            url=str(issue.get("self", "")),
            status=status.get("name"),
            links=linked_keys,
            content=fields.get("description"),
        )


class GitHubSourceAdapter:
    def __init__(self, settings: Settings, client: JsonReader | None = None) -> None:
        self.settings = settings
        self.client = client or _client(settings, "github")
        self.owner, self.repository = settings.github_repository.split("/", 1)

    def read_repository(self) -> dict[str, Any]:
        return self.client.get(f"/repos/{self.owner}/{self.repository}")

    def list_files(self) -> SourcePage:
        branch_path = quote(self.settings.github_branch, safe="")
        branch = self.client.get(
            f"/repos/{self.owner}/{self.repository}/branches/{branch_path}"
        )
        commit_sha = (branch.get("commit") or {}).get("sha")
        if not commit_sha:
            raise SourceReadError("GitHub branch response has no commit identity")
        tree = self.client.get(
            f"/repos/{self.owner}/{self.repository}/git/trees/{commit_sha}",
            {"recursive": "1"},
        )
        if tree.get("truncated"):
            raise SourceUnsupportedError(
                "GitHub returned a truncated tree; a complete paginated tree is unavailable"
            )
        entries = tree.get("tree")
        if not isinstance(entries, list):
            raise SourceReadError("GitHub tree response omitted its entries")
        records = tuple(
            SourceRecord(
                source="github",
                id=str(item.get("sha", "")),
                external_id=str(item.get("path", "")),
                title=str(item.get("path", "")),
                version=str(item.get("sha", "")),
                url=str(item.get("url", "")),
                status=str(item.get("type", "")),
            )
            for item in entries
            if item.get("type") == "blob" and not self._is_environment_file(
                str(item.get("path", ""))
            )
        )
        return SourcePage(records, None)

    @staticmethod
    def _is_environment_file(path: str) -> bool:
        return any(part.lower() == ".env" or part.lower().startswith(".env.") for part in path.split("/"))

    def read_file(self, path: str, ref: str | None = None) -> SourceRecord:
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("GitHub path must be a repository-relative path")
        if self._is_environment_file(path):
            raise SourcePermissionError("GitHub environment file access is prohibited")
        if ref is not None and ref != self.settings.github_branch:
            raise SourcePermissionError("GitHub ref is outside the configured tracked branch")
        endpoint = quote(path, safe="/")
        response = self.client.get(
            f"/repos/{self.owner}/{self.repository}/contents/{endpoint}",
            {"ref": ref or self.settings.github_branch},
        )
        try:
            encoded = "".join(str(response.get("content", "")).split())
            content = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise SourceReadError("GitHub file content is not valid base64 UTF-8") from None
        return SourceRecord(
            source="github",
            id=str(response.get("sha", "")),
            external_id=str(response.get("path", path)),
            title=str(response.get("path", path)),
            version=str(response.get("sha", "")),
            url=str(response.get("html_url", "")),
            status=str(response.get("type", "")),
            content=content,
        )


class ConfluenceSourceAdapter:
    def __init__(self, settings: Settings, client: JsonReader | None = None) -> None:
        self.settings = settings
        self.client = client or _client(settings, "confluence")

    def read_space(self) -> dict[str, Any]:
        response = self.client.get(
            "/wiki/api/v2/spaces", {"keys": self.settings.confluence_space, "limit": "1"}
        )
        spaces = response.get("results") or []
        if not spaces:
            raise SourceNotFoundError("Configured Confluence space is not visible")
        space = spaces[0]
        if not space.get("id"):
            raise SourceReadError("Confluence space response omitted its identity")
        return space

    def list_pages(self, cursor: str | None = None, limit: int = 50) -> SourcePage:
        if not 1 <= limit <= 250:
            raise ValueError("Confluence page limit is out of range")
        space = self.read_space()
        params = {"space-id": str(space["id"]), "limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        response = self.client.get("/wiki/api/v2/pages", params)
        next_url = (response.get("_links") or {}).get("next")
        next_cursor = None
        if next_url:
            parsed = urlparse(next_url)
            if parsed.scheme and parsed.netloc and (
                parsed.scheme != "https" or parsed.netloc != "api.atlassian.com"
            ):
                raise SourceReadError("Confluence returned an untrusted pagination URL")
            next_cursor = (parse_qs(parsed.query).get("cursor") or [None])[0]
            if not next_cursor:
                raise SourceReadError("Confluence pagination link has no cursor")
        records = tuple(self._page_record(page) for page in response.get("results", []))
        return SourcePage(records, next_cursor)

    def read_page(self, page_id: str) -> SourceRecord:
        if not page_id.isdecimal():
            raise ValueError("Confluence page ID must be numeric")
        space_id = str(self.read_space()["id"])
        metadata = self.client.get(f"/wiki/api/v2/pages/{page_id}")
        self._check_page_space(metadata, space_id)
        page = self.client.get(
            f"/wiki/api/v2/pages/{page_id}", {"body-format": "storage"}
        )
        self._check_page_space(page, space_id)
        return self._page_record(page, include_content=True)

    @staticmethod
    def _check_page_space(page: dict[str, Any], space_id: str) -> None:
        if not page.get("spaceId"):
            raise SourceReadError("Confluence page response omitted its space identity")
        if str(page["spaceId"]) != space_id:
            raise SourcePermissionError("Page is outside the configured Confluence space")

    @staticmethod
    def _page_record(
        page: dict[str, Any], include_content: bool = False
    ) -> SourceRecord:
        version = page.get("version") or {}
        links = page.get("_links") or {}
        body = page.get("body") or {}
        storage = body.get("storage") or {}
        return SourceRecord(
            source="confluence",
            id=str(page.get("id", "")),
            external_id=str(page.get("id", "")),
            title=str(page.get("title", "")),
            version=str(version.get("number", "")),
            url=str(links.get("webui", "")),
            status=page.get("status"),
            content=storage.get("value") if include_content else None,
        )
