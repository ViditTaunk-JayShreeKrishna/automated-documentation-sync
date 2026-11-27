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

## Configuration validation

`python -m docsync.config` validates environment settings without printing
their values. Supply `DOCSYNC_JIRA_ACCESS_TOKEN`, `DOCSYNC_GITHUB_ACCESS_TOKEN`
and `DOCSYNC_CONFLUENCE_ACCESS_TOKEN` through the process environment; do not
commit them or put them in documentation. Use least-privilege OAuth access
tokens provisioned for the intended environment. Validation checks presence,
not actual permissions or token validity.

`DOCSYNC_ENVIRONMENT` accepts `development` (default), `test` or `production`.
`DOCSYNC_RECONCILIATION_SECONDS` defaults to 900 and must be positive;
`DOCSYNC_MAX_RETRIES` defaults to 3 and must be between 0 and 3;
`DOCSYNC_RETRY_BACKOFF_SECONDS` defaults to 1 and must be positive and finite.
The initial Jira project, repository, branch and Confluence space are restricted
to the approved scope. Audited scope changes are not implemented yet.

The API and worker validate configuration before starting; invalid settings or
missing tokens stop startup. The API also validates when started through an
ASGI server directly. Neither process connects to external systems yet:
validating token presence does not enable integrations or verify permissions.

## Database setup

Install the development environment and set `DOCSYNC_DATABASE_URL` to a
PostgreSQL connection URL. The development default is an isolated local test
database. Production must explicitly configure the database URL and secrets.

Apply migrations:

```text
alembic upgrade head
alembic current
```

The migration creates tables for artefacts, dependencies, events, jobs,
proposals, approvals and audit records. Reversible migration and database
constraint tests run as part of `python -m pytest`.

## Authorization

Privileged operations require a native-provider-verifiable identity and an
explicit application role. Document approval and rollback require an active
owner or designated-reviewer mapping for the specific artefact. Unknown,
inactive or unverifiable identity and ownership mappings fail closed. Mapping
changes are durable records and must be accompanied by audit evidence. Native
Jira, GitHub or Confluence account verification is not claimed until the
corresponding live integration is configured and tested.

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
