# Automated Documentation Sync

This repository contains the approved project documents and the IP-01 Python
service foundation. It does not yet detect changes, run a scheduler, process
durable jobs, connect to external systems or synchronize documents.

## Requirements

Python 3.12 or 3.13 and pip are required. No Node.js runtime is needed.
FastAPI and Uvicorn provide the API; pytest is the test dependency. The
worker and API run as separate Python processes.

## Setup

From the repository root, create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

On systems without the `py` launcher, use `python3.12 -m venv .venv`, or the
path to a compatible Python interpreter. On macOS or Linux, activate with
`source .venv/bin/activate`.

## Run

In separate activated terminals:

```text
docsync-api
docsync-worker
```

The API listens on `127.0.0.1:8000` by default; `docsync-api --host` and
`--port` select a different interface and port. `GET /health/live` returns
`{"status":"alive"}` when the API process responds. This is a liveness
check only: it does not assert database, scheduler, worker or integration
readiness. API documentation endpoints are disabled in this foundation.

Stop either process with Ctrl+C. The worker remains idle until stopped; the
scheduler and durable PostgreSQL-backed job processing belong to later tasks.
Module entry points `python -m docsync.api` and `python -m docsync.worker`
are also available.

## Test

```text
python -m pytest
```

The tests exercise the liveness response, worker stop signal and actual API
and worker process startup. GitHub Actions installs the development
dependencies and runs the same test command. An Actions result is not assumed
until the workflow has actually run.

## Approved baseline

- [Requirements](requirements.md)
- [Architecture](architecture.md)
- [Design review](design-review.md)
- [Implementation plan](impl-plan.md), especially IP-01
