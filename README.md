# Automated Documentation Sync

This repository contains the approved project documents and the Python service
foundation. Read-only source adapters are available for controlled Jira,
GitHub and Confluence reads, but the API and worker do not invoke them
automatically. A limited webhook receiver is available but disabled by default;
event processing, scheduling and document synchronization are not yet implemented.

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
read access. Confluence page reads through the REST v2 pages endpoints require
the `read:page:confluence` scope and permission to view both the page and its
space. A general content-read scope such as `read:content:confluence` does not
satisfy that endpoint's documented page scope. These adapters perform GET
requests only and classify permission, not-found, transient and unsupported
results explicitly. GitHub reads are restricted to the configured branch and
exclude environment files from discovery and content reads. Confluence page
reads check the configured space before requesting content and again after the
content read. They do not publish or update content.

## Webhook intake progress

The `POST /webhooks/github` and `POST /webhooks/jira` endpoints are disabled
unless their respective `DOCSYNC_GITHUB_WEBHOOK_SECRET` or
`DOCSYNC_JIRA_WEBHOOK_SECRET` is configured. Use independently generated random
secrets of at least 32 bytes, not API tokens. Production requests must reach the
application with an HTTPS scheme; configure any trusted TLS-terminating proxy
appropriately. The receiver verifies the provider's raw-body HMAC before
validating scope and atomically persisting an event and a pending job.
GitHub push events on the configured repository and branch and Jira issue
created, updated and deleted events in KAN are the currently supported subset;
other events are rejected. Confluence intake is not implemented.

The SHA-256 digest of the signed body is the persistent replay/deduplication
identity, rather than an unsigned delivery header. This intentionally collapses
identical signed bodies, including any distinct legitimate events with identical
bodies, and only prevents replay while the event record is retained. The
worker does not yet process accepted jobs; reconciliation and lifecycle coverage
are not implemented. Live webhook delivery has not been verified. IP-09
remains in progress pending end-to-end coverage and verification.

### Live webhook prerequisites (not yet configured)

- Run the API with a durable PostgreSQL database behind a publicly reachable
  HTTPS endpoint with a trusted certificate. Configure the reverse proxy and
  ASGI server to trust forwarded headers only from the actual proxy. Restrict
  other public endpoints and supply production settings through a secret
  manager or environment variables. Do not disable certificate validation.
- The GitHub fine-grained token needs repository **Webhooks: read** to list
  hooks and **Webhooks: read and write** to register one through the API, or a
  repository administrator may configure it. The current token returned HTTP
  403 for listing with `repository_hooks=read` in the accepted-permissions
  response header. Configure JSON delivery for push events to
  `/webhooks/github`, using the corresponding secret. The receiver currently
  rejects GitHub's initial `ping` event; a controlled push, not the ping, is
  needed to test the currently supported path.
- Jira administrative webhook configuration requires the **Administer Jira**
  global permission. Configure issue-created, issue-updated and issue-deleted
  events, restricted to project KAN, to `/webhooks/jira` with its distinct
  secret. Verify sender signature and controlled delivery on the actual site.
- Confluence Automation authentication and lifecycle trigger coverage remain
  unverified. Do not enable a Confluence path until these controls are proven.

Do not register live senders yet: the receiver covers only a subset of events,
the worker is idle, and the HTTPS endpoint and permissions are not established.
These steps describe prerequisites, not evidence that a hook exists or works.

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
