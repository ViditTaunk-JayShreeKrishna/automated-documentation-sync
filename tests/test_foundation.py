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

from docsync.worker import run


def entry_point(name: str) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    return str(Path(sys.executable).parent / f"{name}{suffix}")


def test_worker_stops_when_requested() -> None:
    stop = threading.Event()
    thread = threading.Thread(target=run, args=(stop,))
    thread.start()
    try:
        assert thread.is_alive()
    finally:
        stop.set()
        thread.join(timeout=3)
    assert not thread.is_alive()


def test_api_process_starts_and_serves_liveness(tmp_path) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    with (tmp_path / "api.log").open("w+") as log:
        process = subprocess.Popen(
            [entry_point("docsync-api"), "--port", str(port)],
            stdout=log,
            stderr=subprocess.STDOUT,
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


def test_worker_process_starts_and_stays_running(tmp_path) -> None:
    with (tmp_path / "worker.log").open("w+") as log:
        process = subprocess.Popen(
            [entry_point("docsync-worker")],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                log.seek(0)
                if "Worker started" in log.read():
                    assert process.poll() is None
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
