import asyncio
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from docsync.config import load_settings
from docsync.api import app
from docsync.worker import run


@pytest.fixture
def configured_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("DOCSYNC_")}
    env.update(
        DOCSYNC_ENVIRONMENT="test",
        DOCSYNC_JIRA_ACCESS_TOKEN="jira-test-secret",
        DOCSYNC_GITHUB_ACCESS_TOKEN="github-test-secret",
        DOCSYNC_CONFLUENCE_ACCESS_TOKEN="confluence-test-secret",
        DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL="test@example.invalid",
        DOCSYNC_ATLASSIAN_CLOUD_ID="3aaf5522-6248-468c-88ca-9546e0d58a6d",
        PYTHON_DOTENV_DISABLED="1",
    )
    return env


def entry_point(name: str) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    return str(Path(sys.executable).parent / f"{name}{suffix}")


def test_worker_stops_when_requested(configured_env: dict[str, str]) -> None:
    stop = threading.Event()
    thread = threading.Thread(target=run, args=(stop, load_settings(configured_env)))
    thread.start()
    try:
        assert thread.is_alive()
    finally:
        stop.set()
        thread.join(timeout=3)
    assert not thread.is_alive()


def test_api_process_starts_and_serves_liveness(tmp_path, configured_env) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    with (tmp_path / "api.log").open("w+") as log:
        process = subprocess.Popen(
            [entry_point("docsync-api"), "--port", str(port)],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=configured_env,
        )
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                log.seek(0)
                if "Uvicorn running on" not in log.read():
                    time.sleep(0.1)
                    continue
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/health/live", timeout=1
                    ) as response:
                        assert response.status == 200
                        assert response.read() == b'{"status":"alive"}'
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.1)
                    continue
                with pytest.raises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/openapi.json", timeout=1
                    )
                assert error.value.code == 404
                return
            log.seek(0)
            raise AssertionError(f"API process did not become ready: {log.read()}")
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


def test_worker_process_starts_and_stays_running(tmp_path, configured_env) -> None:
    with (tmp_path / "worker.log").open("w+") as log:
        process = subprocess.Popen(
            [entry_point("docsync-worker")],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=configured_env,
        )
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                log.seek(0)
                output = log.read()
                if "Worker started in test" in output:
                    assert process.poll() is None
                    assert all(
                        configured_env[key] not in output
                        for key in (
                            "DOCSYNC_JIRA_ACCESS_TOKEN",
                            "DOCSYNC_GITHUB_ACCESS_TOKEN",
                            "DOCSYNC_CONFLUENCE_ACCESS_TOKEN",
                        )
                    )
                    return
                if process.poll() is not None:
                    break
                time.sleep(0.1)
            log.seek(0)
            raise AssertionError(f"Worker did not start: {log.read()}")
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


def test_api_rejects_invalid_port() -> None:
    process = subprocess.run(
        [entry_point("docsync-api"), "--port", "not-a-port"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert process.returncode != 0
    assert "invalid int value" in process.stderr


@pytest.mark.parametrize("process_name", ["docsync-api", "docsync-worker"])
@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DOCSYNC_JIRA_ACCESS_TOKEN", ""),
        ("DOCSYNC_MAX_RETRIES", "4"),
        ("DOCSYNC_GITHUB_BRANCH", "main"),
        ("DOCSYNC_ENVIRONMENT", "invalid"),
    ],
)
def test_process_rejects_invalid_configuration(
    configured_env: dict[str, str], process_name: str, name: str, value: str
) -> None:
    secrets = [configured_env[key] for key in (
        "DOCSYNC_JIRA_ACCESS_TOKEN",
        "DOCSYNC_GITHUB_ACCESS_TOKEN",
        "DOCSYNC_CONFLUENCE_ACCESS_TOKEN",
    )]
    configured_env[name] = value
    process = subprocess.run(
        [entry_point(process_name)],
        env=configured_env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    output = process.stdout + process.stderr
    assert process.returncode != 0
    assert name in output
    assert all(secret not in output for secret in secrets)


def test_direct_asgi_startup_rejects_missing_configuration(configured_env) -> None:
    del configured_env["DOCSYNC_JIRA_ACCESS_TOKEN"]
    process = subprocess.run(
        [sys.executable, "-m", "uvicorn", "docsync.api:app", "--port", "0"],
        env=configured_env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert process.returncode != 0
    assert "DOCSYNC_JIRA_ACCESS_TOKEN" in process.stderr
    assert configured_env["DOCSYNC_GITHUB_ACCESS_TOKEN"] not in process.stderr


def test_asgi_lifespan_exposes_validated_settings(configured_env, monkeypatch) -> None:
    for key in list(os.environ):
        if key.startswith("DOCSYNC_"):
            monkeypatch.delenv(key)
    for key, value in configured_env.items():
        if key.startswith("DOCSYNC_"):
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("DOCSYNC_RECONCILIATION_SECONDS", "120")

    async def check() -> None:
        async with app.router.lifespan_context(app):
            assert app.state.settings.environment == "test"
            assert app.state.settings.reconciliation_seconds == 120
        assert not hasattr(app.state, "settings")

    asyncio.run(check())
