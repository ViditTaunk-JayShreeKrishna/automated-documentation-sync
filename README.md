# Automated Documentation Sync

This repository contains the approved project documents and the Python service
foundation. Read-only source adapters are available for controlled Jira,
GitHub and Confluence reads, but the API and worker do not invoke them
automatically. Change detection, event processing, scheduling and document
synchronization are not yet implemented.

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
their values and loads a local `.env` file when present (process environment
values take precedence). Supply `DOCSYNC_JIRA_ACCESS_TOKEN`,
`DOCSYNC_GITHUB_ACCESS_TOKEN`, `DOCSYNC_CONFLUENCE_ACCESS_TOKEN`,
`DOCSYNC_ATLASSIAN_ACCOUNT_EMAIL` and `DOCSYNC_ATLASSIAN_CLOUD_ID`. Never
commit `.env`, include credentials in documentation, or print their values.
Scoped Atlassian API tokens use HTTP Basic authentication with the account
email through the `api.atlassian.com` Jira and Confluence gateways. The gateway
URLs are derived from the Cloud ID; GitHub uses `https://api.github.com`.
Validation checks configuration presence and format, not actual permissions or
token validity. See `.env.example` for safe placeholders.

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

## Security controls

Structured log helpers redact secret-looking values, bearer credentials and
personal identifiers. AI, report and audit text are screened before use and
disallowed sensitive text fails closed. `DOCSYNC_REQUIRE_TLS` defaults to true
and must remain true in production. Secret and sensitive values must not be
stored in Markdown, logs or test fixtures. Live OAuth scopes and provider data
handling remain unverified until authorized credentials and terms are available.

## Read-only source adapters

`docsync.source_adapters` provides scoped Jira issue search/read, GitHub branch
tree/file reads and Confluence space/page reads. Jira and Confluence scoped
Atlassian API tokens use HTTP Basic with the configured account email; GitHub
uses a Bearer fine-grained token. Jira reads require project browse access and
the applicable Jira read scope. GitHub needs repository metadata and contents
read access. Confluence page bodies require the applicable content-read scope
(`read:confluence-content.all` or its granular equivalent) and space view
permission. These adapters perform GET requests only and classify permission,
not-found, transient and unsupported results explicitly. They do not publish
or update content.

## Artefact registry

Registered artefacts have an immutable application UUID and a unique
system/scope/external-ID identity. Registration and confirmed rename/move
operations require an authenticated administrator and are audited. Unknown
ownership blocks owner-dependent operations. Each record persists location,
owner, version, digest, related documents and synchronization status. Mirror
pairs record source and target versions and digests; unmapped artefact types
cannot be assigned authority implicitly.

## Dependency registry

Dependency candidates retain evidence and remain pending until an authorized
administrator approves or rejects them. Only approved edges participate in
impact traversal. Approval of a proposed edge detects direct or transitive
cycles and fails closed. Rejection requires a reason and is audit recorded.

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
