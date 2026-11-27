import asyncio
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import replace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from docsync.api import app
from docsync.config import ConfigurationError, load_settings
from docsync.models import Event, Job

DATABASE_URL = os.environ.get(
    "DOCSYNC_DATABASE_URL",
    "postgresql+psycopg://docsync_test@127.0.0.1:55432/docsync_test",
)
GITHUB_SECRET = "g" * 32
JIRA_SECRET = "j" * 32


@pytest.fixture(scope="module")
def engine():
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    engine = create_engine(DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def settings():
    return load_settings({
        "DOCSYNC_ENVIRONMENT": "test",
        "DOCSYNC_JIRA_ACCESS_TOKEN": "jira-test-token",
        "DOCSYNC_GITHUB_ACCESS_TOKEN": "github-test-token",
        "DOCSYNC_CONFLUENCE_ACCESS_TOKEN": "confluence-test-token",
        "DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL": "test@example.invalid",
        "DOCSYNC_ATLASSIAN_CLOUD_ID": "3aaf5522-6248-468c-88ca-9546e0d58a6d",
        "DOCSYNC_JIRA_WEBHOOK_SECRET": JIRA_SECRET,
        "DOCSYNC_GITHUB_WEBHOOK_SECRET": GITHUB_SECRET,
    })


def signed_body(payload, secret):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, signature


async def send(source, body, signature=None, event_type="push", scheme="http", delivery="first"):
    messages = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send_message(message):
        messages.append(message)

    headers = [(b"x-github-event", event_type.encode()), (b"x-github-delivery", delivery.encode())]
    if signature:
        header = b"x-hub-signature-256" if source == "github" else b"x-hub-signature"
        headers.append((header, signature.encode()))
    path = "/webhooks/" + source
    await app(
        {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "scheme": scheme, "path": path, "raw_path": path.encode(),
            "query_string": b"", "headers": headers, "server": ("test", 80),
            "client": ("127.0.0.1", 1), "root_path": "",
        },
        receive,
        send_message,
    )
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    data = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(data)


def github_payload(settings):
    return {
        "repository": {"full_name": settings.github_repository},
        "ref": "refs/heads/" + settings.github_branch,
        "before": "0" * 40,
        "after": uuid.uuid4().hex + "0" * 8,
        "untrusted_private_data": "must-not-be-persisted",
    }


def pull_request_payload(settings):
    return {
        "action": "closed",
        "number": 123,
        "repository": {"full_name": settings.github_repository},
        "pull_request": {
            "number": 123,
            "merged": True,
            "base": {
                "repo": {"full_name": settings.github_repository},
                "ref": settings.github_branch,
                "sha": uuid.uuid4().hex + "0" * 8,
            },
            "head": {"sha": uuid.uuid4().hex + "0" * 8},
            "body": "must-not-be-persisted",
        },
    }


@pytest.fixture
def receiver(monkeypatch, settings, engine):
    monkeypatch.setattr(app.state, "settings", settings, raising=False)
    monkeypatch.setattr(app.state, "webhook_engine", engine, raising=False)
    digests = []
    yield digests
    with Session(engine) as session, session.begin():
        for source, digest in digests:
            session.query(Job).filter_by(operation_type="source_event", operation_id=f"{source}:{digest}").delete()
            session.query(Event).filter_by(source_system=source, source_event_id=digest).delete()


def test_github_receiver_persists_atomically_and_deduplicates_signed_body(receiver, settings, engine):
    body, signature = signed_body(github_payload(settings), GITHUB_SECRET)
    digest = hashlib.sha256(body).hexdigest()
    receiver.append(("github", digest))

    async def deliver():
        return await asyncio.gather(
            send("github", body, signature, delivery="one"),
            send("github", body, signature, delivery="changed-unsigned-header"),
        )

    responses = asyncio.run(deliver())
    assert sorted(result[1]["status"] for result in responses) == ["accepted", "duplicate"]
    assert all(result[0] == 200 for result in responses)
    with Session(engine) as session:
        event = session.execute(select(Event).filter_by(source_system="github", source_event_id=digest)).scalar_one()
        job = session.execute(select(Job).filter_by(operation_type="source_event", operation_id="github:" + digest)).scalar_one()
        assert job.payload == {"event_id": str(event.id)}
        assert job.status == "pending"
        assert "must-not-be-persisted" not in repr(event.normalized_payload)


def test_jira_receiver_accepts_scoped_issue_event(receiver, engine):
    payload = {"webhookEvent": "jira:issue_updated", "issue": {"key": "KAN-9", "id": str(uuid.uuid4().int)}}
    body, signature = signed_body(payload, JIRA_SECRET)
    digest = hashlib.sha256(body).hexdigest()
    receiver.append(("jira", digest))
    assert asyncio.run(send("jira", body, signature)) == (200, {"status": "accepted"})
    assert asyncio.run(send("jira", body, signature)) == (200, {"status": "duplicate"})
    with Session(engine) as session:
        event = session.execute(select(Event).filter_by(source_system="jira", source_event_id=digest)).scalar_one()
        assert event.normalized_payload["issue_key"] == "KAN-9"


def test_github_pull_request_delivery_records_signed_state_and_deduplicates(receiver, settings, engine):
    payload = pull_request_payload(settings)
    body, signature = signed_body(payload, GITHUB_SECRET)
    digest = hashlib.sha256(body).hexdigest()
    receiver.append(("github", digest))
    assert asyncio.run(send("github", body, signature, event_type="pull_request")) == (200, {"status": "accepted"})
    assert asyncio.run(send("github", body, signature, event_type="pull_request", delivery="different")) == (
        200, {"status": "duplicate"}
    )
    with Session(engine) as session:
        event = session.execute(select(Event).filter_by(source_system="github", source_event_id=digest)).scalar_one()
        assert event.normalized_payload["merged"] is True
        assert event.normalized_payload["number"] == 123
        assert event.normalized_payload["base_sha"] == payload["pull_request"]["base"]["sha"]
        assert event.normalized_payload["head_sha"] == payload["pull_request"]["head"]["sha"]
        assert "must-not-be-persisted" not in repr(event.normalized_payload)
        assert session.execute(select(Job).filter_by(operation_id="github:" + digest)).scalar_one().payload == {
            "event_id": str(event.id)
        }


@pytest.mark.parametrize("case", ["wrong_branch", "wrong_repository", "wrong_base_repository", "invalid_number", "invalid_sha", "unsupported_action", "malformed_action", "invalid_merge_state"])
def test_github_pull_request_rejects_invalid_or_unscoped_events(receiver, settings, case):
    payload = pull_request_payload(settings)
    if case == "wrong_branch":
        payload["pull_request"]["base"]["ref"] = "main"
    elif case == "wrong_repository":
        payload["repository"]["full_name"] = "other/repository"
    elif case == "wrong_base_repository":
        payload["pull_request"]["base"]["repo"]["full_name"] = "other/repository"
    elif case == "invalid_number":
        payload["number"] = True
    elif case == "invalid_sha":
        payload["pull_request"]["head"]["sha"] = "not-a-sha"
    elif case == "unsupported_action":
        payload["action"] = "labeled"
    elif case == "malformed_action":
        payload["action"] = []
    else:
        payload["action"] = "opened"
    body, signature = signed_body(payload, GITHUB_SECRET)
    assert asyncio.run(send("github", body, signature, event_type="pull_request"))[0] == 422


@pytest.mark.parametrize("action", ["opened", "reopened", "synchronize", "edited", "closed"])
def test_github_pull_request_unmerged_state_is_preserved(receiver, settings, engine, action):
    payload = pull_request_payload(settings)
    payload["action"] = action
    payload["pull_request"]["merged"] = False
    body, signature = signed_body(payload, GITHUB_SECRET)
    digest = hashlib.sha256(body).hexdigest()
    receiver.append(("github", digest))
    assert asyncio.run(send("github", body, signature, event_type="pull_request"))[0] == 200
    with Session(engine) as session:
        event = session.execute(select(Event).filter_by(source_system="github", source_event_id=digest)).scalar_one()
        assert event.normalized_payload["merged"] is False


def test_github_pull_request_tampering_and_unsigned_header_cannot_reclassify(receiver, settings):
    body, signature = signed_body(pull_request_payload(settings), GITHUB_SECRET)
    assert asyncio.run(send("github", body + b" ", signature, event_type="pull_request"))[0] == 401
    assert asyncio.run(send("github", body, signature, event_type="push"))[0] == 422


def test_rejects_invalid_signatures_and_out_of_scope_events(receiver, settings):
    payload = github_payload(settings)
    body, signature = signed_body(payload, GITHUB_SECRET)
    assert asyncio.run(send("github", body, None))[0] == 401
    assert asyncio.run(send("github", body + b" ", signature))[0] == 401
    assert asyncio.run(send("github", body, signature, event_type="issues"))[0] == 422
    payload["ref"] = "refs/heads/main"
    body, signature = signed_body(payload, GITHUB_SECRET)
    assert asyncio.run(send("github", body, signature))[0] == 422
    body, signature = signed_body({"webhookEvent": "jira:issue_updated", "issue": {"key": "OTHER-1", "id": "1"}}, JIRA_SECRET)
    assert asyncio.run(send("jira", body, signature))[0] == 422
    assert asyncio.run(send("confluence", body, signature))[0] == 404


def test_rejects_bad_json_oversized_and_production_http(receiver, settings, monkeypatch):
    body = b"{bad json"
    signature = "sha256=" + hmac.new(GITHUB_SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert asyncio.run(send("github", body, signature))[0] == 422
    monkeypatch.setattr("docsync.api.MAX_WEBHOOK_BYTES", 4)
    assert asyncio.run(send("github", body, signature))[0] == 413
    app.state.settings = replace(settings, environment="production")
    try:
        assert asyncio.run(send("github", body, signature))[0] == 403
    finally:
        app.state.settings = settings


def test_database_failure_never_acknowledges(receiver, settings, monkeypatch):
    body, signature = signed_body(github_payload(settings), GITHUB_SECRET)
    def fail(*args):
        raise SQLAlchemyError("secret data should not be exposed")
    monkeypatch.setattr("docsync.api.accept_event", fail)
    status, response = asyncio.run(send("github", body, signature))
    assert status == 503
    assert "secret data" not in repr(response)


def test_job_insert_failure_rolls_back_event(receiver, settings, engine):
    body, signature = signed_body(github_payload(settings), GITHUB_SECRET)
    digest = hashlib.sha256(body).hexdigest()
    receiver.append(("github", digest))
    with Session(engine) as session, session.begin():
        session.add(Job(operation_type="source_event", operation_id="github:" + digest, payload={}))
    assert asyncio.run(send("github", body, signature))[0] == 503
    with Session(engine) as session:
        assert session.execute(select(Event).filter_by(source_system="github", source_event_id=digest)).scalar_one_or_none() is None


def test_real_local_http_delivery_is_durably_accepted(receiver, settings, engine, tmp_path):
    body, signature = signed_body(github_payload(settings), GITHUB_SECRET)
    digest = hashlib.sha256(body).hexdigest()
    receiver.append(("github", digest))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith("DOCSYNC_")}
    env.update(
        DOCSYNC_ENVIRONMENT="test", DOCSYNC_DATABASE_URL=DATABASE_URL,
        DOCSYNC_JIRA_ACCESS_TOKEN="jira-test-token", DOCSYNC_GITHUB_ACCESS_TOKEN="github-test-token",
        DOCSYNC_CONFLUENCE_ACCESS_TOKEN="confluence-test-token",
        DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL="test@example.invalid",
        DOCSYNC_ATLASSIAN_CLOUD_ID="3aaf5522-6248-468c-88ca-9546e0d58a6d",
        DOCSYNC_GITHUB_WEBHOOK_SECRET=GITHUB_SECRET, PYTHON_DOTENV_DISABLED="1",
    )
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "docsync.api:app", "--host", "127.0.0.1", "--port", str(port)],
            stdout=log, stderr=subprocess.STDOUT, env=env,
        )
        try:
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail("Local API exited before becoming ready")
                try:
                    with urllib.request.urlopen(url + "/health/live", timeout=1):
                        break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.1)
            else:
                pytest.fail("Local API did not become ready")
            request = urllib.request.Request(
                url + "/webhooks/github", data=body, method="POST",
                headers={"X-Hub-Signature-256": signature, "X-GitHub-Event": "push"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                assert response.status == 200
                assert json.load(response)["status"] == "accepted"
            with Session(engine) as session:
                event = session.execute(select(Event).filter_by(source_system="github", source_event_id=digest)).scalar_one()
                job = session.execute(select(Job).filter_by(operation_type="source_event", operation_id="github:" + digest)).scalar_one()
                assert job.payload["event_id"] == str(event.id)
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


def test_secrets_are_optional_redacted_and_distinct(settings):
    assert GITHUB_SECRET not in repr(settings)
    assert JIRA_SECRET not in repr(settings)
    base = {
        "DOCSYNC_JIRA_ACCESS_TOKEN": "x", "DOCSYNC_GITHUB_ACCESS_TOKEN": "x",
        "DOCSYNC_CONFLUENCE_ACCESS_TOKEN": "x", "DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL": "x",
        "DOCSYNC_ATLASSIAN_CLOUD_ID": "3aaf5522-6248-468c-88ca-9546e0d58a6d",
    }
    assert load_settings(base).github_webhook_secret is None
    with pytest.raises(ConfigurationError):
        load_settings({**base, "DOCSYNC_GITHUB_WEBHOOK_SECRET": "short"})
    with pytest.raises(ConfigurationError):
        load_settings({**base, "DOCSYNC_GITHUB_WEBHOOK_SECRET": GITHUB_SECRET, "DOCSYNC_JIRA_WEBHOOK_SECRET": GITHUB_SECRET})
    app.state.settings = replace(settings, github_webhook_secret=None)
    try:
        assert asyncio.run(send("github", b""))[0] == 503
    finally:
        del app.state.settings
