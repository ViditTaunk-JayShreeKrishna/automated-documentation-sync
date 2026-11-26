"""HTTP process entry point and liveness endpoint."""

import argparse
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI

from docsync.config import load_settings, require_settings


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.settings = load_settings()
    try:
        yield
    finally:
        del application.state.settings


app = FastAPI(
    docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
)


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the documentation sync API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    require_settings()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
