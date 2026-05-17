"""FastAPI application entrypoint for the P9a control API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.ui.api import create_router
from backend.ui.state import (
    DemoControlService,
    _DEFAULT_UI_RUN_TURN_DELAY_SECONDS,
    close_model_route_client,
)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await close_model_route_client()


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
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        # 5173 is Vite's default and what ``scripts/start_frontend.ps1``
        # binds. The CORS allowlist intentionally stays minimal here:
        # extra-origin padding for sibling worktrees (e.g. the parallel
        # design-reference variant) is opt-in and should be added back
        # explicitly when those frontends are actively used, rather than
        # carried as defaults.
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            # P18 worktree dev port: the main 5173 slot is taken by the
            # sibling `federated_silo_agent` worktree's frontend, so P18
            # polish work runs on 5180 (paired with the 8060 backend in
            # this worktree). Per the comment above, sibling-worktree
            # origins are opt-in; this addition is opt-in for the
            # duration of P18 development.
            "http://localhost:5180",
            "http://127.0.0.1:5180",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(
        create_router(
            service
            if service is not None
            else DemoControlService(
                run_turn_delay_seconds=_DEFAULT_UI_RUN_TURN_DELAY_SECONDS
            )
        )
    )
    return app


app = create_app()
