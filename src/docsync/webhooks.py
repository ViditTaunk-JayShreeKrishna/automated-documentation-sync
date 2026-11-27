"""Authenticated, durable intake for a restricted subset of source events."""

import hashlib
import json
import re
import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from docsync.config import Settings
from docsync.models import Event, Job


class InvalidWebhook(ValueError):
    """A signed webhook is malformed or not supported by this receiver."""


def _revision(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is not None


def normalize_event(source: str, event_type: str, body: bytes, settings: Settings) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidWebhook("Invalid JSON payload") from None
    if not isinstance(payload, dict):
        raise InvalidWebhook("Invalid event payload")
    if source == "github" and event_type == "push":
        repository = payload.get("repository")
        if not isinstance(repository, dict) or repository.get("full_name") != settings.github_repository:
            raise InvalidWebhook("Event is outside configured repository")
        ref = payload.get("ref")
        if ref != "refs/heads/" + settings.github_branch:
            raise InvalidWebhook("Event is outside configured branch")
        before, after = payload.get("before"), payload.get("after")
        if not all(_revision(value) for value in (before, after)):
            raise InvalidWebhook("Push event omitted valid revisions")
        return {"type": "push", "repository": settings.github_repository, "ref": ref, "before": before, "after": after}
    if source == "github" and event_type == "pull_request":
        repository, pull_request = payload.get("repository"), payload.get("pull_request")
        if not isinstance(repository, dict) or repository.get("full_name") != settings.github_repository:
            raise InvalidWebhook("Event is outside configured repository")
        if not isinstance(pull_request, dict):
            raise InvalidWebhook("Pull request event omitted its details")
        base, head = pull_request.get("base"), pull_request.get("head")
        if not isinstance(base, dict) or not isinstance(head, dict):
            raise InvalidWebhook("Pull request event omitted revisions")
        base_repository = base.get("repo")
        if (
            not isinstance(base_repository, dict)
            or base_repository.get("full_name") != settings.github_repository
            or base.get("ref") != settings.github_branch
        ):
            raise InvalidWebhook("Event is outside configured branch")
        action, number, merged = payload.get("action"), payload.get("number"), pull_request.get("merged")
        if not isinstance(action, str) or action not in {"opened", "reopened", "synchronize", "edited", "closed"}:
            raise InvalidWebhook("Unsupported pull request action")
        if type(number) is not int or number <= 0 or pull_request.get("number") != number:
            raise InvalidWebhook("Pull request identity is invalid")
        if type(merged) is not bool or (merged and action != "closed"):
            raise InvalidWebhook("Pull request merge state is invalid")
        if not _revision(base.get("sha")) or not _revision(head.get("sha")):
            raise InvalidWebhook("Pull request event omitted valid revisions")
        return {
            "type": "pull_request", "repository": settings.github_repository,
            "number": number, "action": action, "base_ref": settings.github_branch,
            "base_sha": base["sha"], "head_sha": head["sha"], "merged": merged,
        }
    if source == "jira":
        kind = payload.get("webhookEvent")
        if kind not in {"jira:issue_created", "jira:issue_updated", "jira:issue_deleted"}:
            raise InvalidWebhook("Unsupported Jira event")
        issue = payload.get("issue")
        if not isinstance(issue, dict):
            raise InvalidWebhook("Jira event omitted issue identity")
        key, issue_id = issue.get("key"), issue.get("id")
        if not isinstance(key, str) or re.fullmatch(re.escape(settings.jira_project) + r"-[0-9]+", key) is None:
            raise InvalidWebhook("Event is outside configured Jira project")
        if not isinstance(issue_id, str) or not issue_id.isdecimal():
            raise InvalidWebhook("Jira event omitted issue identity")
        return {"type": kind, "issue_key": key, "issue_id": issue_id}
    raise InvalidWebhook("Unsupported webhook event")


def accept_event(engine: Engine, source: str, body: bytes, normalized: dict[str, Any]) -> bool:
    """Atomically persist an event and its job, returning False for exact replays."""
    digest = hashlib.sha256(body).hexdigest()
    event_id = uuid.uuid4()
    with Session(engine) as session, session.begin():
        inserted = session.execute(
            insert(Event)
            .values(id=event_id, source_system=source, source_event_id=digest, normalized_payload=normalized)
            .on_conflict_do_nothing(constraint="uq_event_source")
            .returning(Event.id)
        ).scalar_one_or_none()
        if inserted is None:
            return False
        session.add(
            Job(
                operation_type="source_event",
                operation_id=f"{source}:{digest}",
                payload={"event_id": str(event_id)},
            )
        )
    return True
