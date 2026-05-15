"""FastAPI routes for the P9a demo control API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from backend.ui.snapshots import (
    ComponentId,
    ComponentInteractionRequest,
    ComponentInteractionResult,
    ComponentSnapshot,
    HealthSnapshot,
    ProbeRequest,
    ProbeResult,
    SessionCreateRequest,
    SessionSnapshot,
    SystemSnapshot,
    TimelineEventSnapshot,
)
from backend.ui.state import DemoControlService


def create_router(service: DemoControlService) -> APIRouter:
    """Build the P9a API router around one session service.

    The service is required so router construction never implicitly
    spins up state. ``create_app`` in ``server.py`` owns the fallback
    construction; tests inject their own service. Removing the
    optional default makes the dependency wiring obvious at every
    callsite.
    """
    router = APIRouter()
    control = service

    @router.get("/health", response_model=HealthSnapshot)
    def health() -> HealthSnapshot:
        return HealthSnapshot()

    @router.get("/system", response_model=SystemSnapshot)
    def system() -> SystemSnapshot:
        return control.system_snapshot()

    @router.post(
        "/sessions",
        response_model=SessionSnapshot,
        status_code=status.HTTP_201_CREATED,
    )
    def create_session(request: SessionCreateRequest) -> SessionSnapshot:
        return control.create_session(request)

    @router.get("/sessions/{session_id}", response_model=SessionSnapshot)
    def get_session(session_id: UUID) -> SessionSnapshot:
        try:
            return control.get_session(session_id)
        except KeyError as exc:
            raise _not_found(exc) from exc

    @router.post("/sessions/{session_id}/step", response_model=SessionSnapshot)
    def step_session(session_id: UUID) -> SessionSnapshot:
        try:
            return control.step_session(session_id)
        except KeyError as exc:
            raise _not_found(exc) from exc

    @router.post("/sessions/{session_id}/run-until-idle", response_model=SessionSnapshot)
    def run_until_idle(session_id: UUID) -> SessionSnapshot:
        try:
            return control.run_until_idle(session_id)
        except KeyError as exc:
            raise _not_found(exc) from exc

    @router.get(
        "/sessions/{session_id}/timeline",
        response_model=list[TimelineEventSnapshot],
    )
    def timeline(session_id: UUID) -> list[TimelineEventSnapshot]:
        try:
            return control.timeline(session_id)
        except KeyError as exc:
            raise _not_found(exc) from exc

    @router.get(
        "/sessions/{session_id}/events",
        response_model=list[TimelineEventSnapshot],
    )
    def events(session_id: UUID) -> list[TimelineEventSnapshot]:
        # `/events` and `/timeline` are deliberately distinct endpoints with
        # the same P9a-era implementation. `/timeline` is the stable
        # paged-history view; `/events` is the streaming surface that P15
        # will upgrade to SSE backed by the audit channel
        # (`audit.subscribe()`). Keeping the two paths separate now means
        # the P9b frontend can wire to `/events` for live updates and
        # `/timeline` for historical scrubbing without a route change
        # when P15 lands. TODO(P15): replace with StreamingResponse / SSE
        # once the audit channel exists.
        try:
            return control.timeline(session_id)
        except KeyError as exc:
            raise _not_found(exc) from exc

    @router.get(
        "/sessions/{session_id}/components/{component_id}",
        response_model=ComponentSnapshot,
    )
    def component(session_id: UUID, component_id: ComponentId) -> ComponentSnapshot:
        try:
            return control.component_snapshot(session_id, component_id)
        except KeyError as exc:
            raise _not_found(exc) from exc

    @router.post(
        "/sessions/{session_id}/probes",
        response_model=ProbeResult,
    )
    def probe(session_id: UUID, request: ProbeRequest) -> ProbeResult:
        try:
            return control.run_probe(session_id, request)
        except KeyError as exc:
            raise _not_found(exc) from exc

    @router.post(
        "/sessions/{session_id}/components/{component_id}/interactions",
        response_model=ComponentInteractionResult,
    )
    def component_interaction(
        session_id: UUID,
        component_id: ComponentId,
        request: ComponentInteractionRequest,
    ) -> ComponentInteractionResult:
        try:
            return control.run_component_interaction(session_id, component_id, request)
        except KeyError as exc:
            raise _not_found(exc) from exc

    return router


def _not_found(exc: KeyError) -> HTTPException:
    # str(KeyError("msg")) wraps the message in quotes; pull the first arg
    # when it is a string so the API "detail" reads cleanly. Fall back to
    # a generic message if the caller raised KeyError() with no args
    # (currently never the case, but the 404 contract is "always informative").
    detail = exc.args[0] if exc.args and isinstance(exc.args[0], str) else str(exc)
    if not detail:
        detail = "Resource not found"
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
