"""FastAPI application entrypoint for the P9a control API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.ui.api import create_router
from backend.ui.state import DemoControlService


def create_app(service: DemoControlService | None = None) -> FastAPI:
    """Create the local demo-control API app.

    Owns the fallback service construction so ``create_router`` can
    require an explicit service. Tests pass their own service; the
    module-level ``app`` builds one on import.
    """
    app = FastAPI(
        title="Federated Silo Agent Demo Control API",
        version="0.1.0",
        description="Typed P9a control API for judge-console observability and probes.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5200",
            "http://127.0.0.1:5200",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_router(service if service is not None else DemoControlService()))
    return app


app = create_app()
