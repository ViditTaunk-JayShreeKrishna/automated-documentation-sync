"""HTTP process entry point and liveness endpoint."""

import argparse
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from docsync.config import load_settings, require_settings
from docsync.webhook_auth import WebhookAuthenticationError, verify_hmac_sha256
from docsync.webhooks import InvalidWebhook, accept_event, normalize_event

logger = logging.getLogger(__name__)
MAX_WEBHOOK_BYTES = 25 * 1024 * 1024


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.settings = load_settings()
    application.state.webhook_engine = create_engine(
        application.state.settings.database_url.get_secret_value(), pool_pre_ping=True
    )
    try:
        yield
    finally:
        application.state.webhook_engine.dispose()
        del application.state.webhook_engine
        del application.state.settings


app = FastAPI(
    docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
)


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.post("/webhooks/{source}")
async def receive_webhook(source: str, request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    if source == "github":
        secret = settings.github_webhook_secret
        signature = request.headers.get("X-Hub-Signature-256")
        event_type = request.headers.get("X-GitHub-Event", "")
    elif source == "jira":
        secret = settings.jira_webhook_secret
        signature = request.headers.get("X-Hub-Signature")
        event_type = ""
    else:
        raise HTTPException(status_code=404, detail="Webhook source is not supported")
    if secret is None:
        raise HTTPException(status_code=503, detail="Webhook source is not configured")
    if settings.environment == "production" and request.url.scheme != "https":
        raise HTTPException(status_code=403, detail="HTTPS is required")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="Webhook payload is too large")
    raw = bytes(body)
    try:
        verify_hmac_sha256(raw, secret.get_secret_value().encode("utf-8"), signature)
    except WebhookAuthenticationError:
        raise HTTPException(status_code=401, detail="Webhook authentication failed") from None
    try:
        normalized = normalize_event(source, event_type, raw, settings)
    except InvalidWebhook:
        raise HTTPException(status_code=422, detail="Webhook event is invalid or unsupported") from None
    try:
        created = await run_in_threadpool(
            accept_event, request.app.state.webhook_engine, source, raw, normalized
        )
    except SQLAlchemyError:
        logger.error("Webhook event persistence failed for %s", source)
        raise HTTPException(status_code=503, detail="Webhook persistence unavailable") from None
    return {"status": "accepted" if created else "duplicate"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the documentation sync API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    require_settings()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
