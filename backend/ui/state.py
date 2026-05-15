"""In-memory P9a demo-control service.

This module deliberately exposes only a demo control plane. It can inspect
state and inject probes through normal security boundaries, but it does not
own privileged mutators such as "approve route" or "mark signature valid".
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from datetime import timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.a3_silo_responder import A3SiloResponderAgent
from backend.agents.a3_states import A3TurnInput
from backend.agents.f3_sanctions import load_watchlist
from backend.runtime.context import AgentRuntimeContext, TrustDomain
from backend.security import (
    PrincipalNotAllowed,
    PrincipalAllowlist,
    PrincipalAllowlistEntry,
    ReplayCache,
    ReplayCacheSnapshot,
    ReplayDetected,
    SecurityEnvelopeError,
    SignatureInvalid,
)
from backend.security.signing import (
    approved_body_hash,
    generate_key_pair,
    sign_message,
    sign_model_signature,
)
from backend.silos.budget import PrivacyBudgetLedger, RequesterKey
from backend.silos.local_reader import bank_db_path
from shared.enums import AgentRole, BankId, MessageType, QueryShape, RouteKind, TypologyCode
from shared.messages import (
    EntityPresencePayload,
    PurposeDeclaration,
    RouteApproval,
    Sec314bQuery,
)

from backend.ui.snapshots import (
    AuditChainSnapshot,
    ComponentId,
    ComponentInteractionKind,
    ComponentInteractionRequest,
    ComponentInteractionResult,
    ComponentReadinessSnapshot,
    ComponentSnapshot,
    DpLedgerEntrySnapshot,
    DpLedgerSnapshot,
    EnvelopeVerificationSnapshot,
    ProbeKind,
    ProbeRequest,
    ProbeResult,
    ProviderHealthSnapshot,
    RouteApprovalSnapshot,
    SecurityLayer,
    SessionCreateRequest,
    SessionSnapshot,
    SigningStateSnapshot,
    SnapshotField,
    SnapshotStatus,
    SystemSnapshot,
    TimelineEventSnapshot,
    utc_now,
)


class UiStateModel(BaseModel):
    """Strict base for internal P9a state models."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class DemoPrincipal(UiStateModel):
    """One demo principal with private key retained server-side only."""

    agent_id: str
    role: AgentRole
    bank_id: BankId
    signing_key_id: str
    private_key: str = Field(repr=False)
    public_key: str


class DemoSessionRuntime:
    """Mutable in-memory session state for local demo control.

    Thread-safe: FastAPI runs synchronous endpoints in a threadpool, so
    concurrent requests targeting the same session_id can interleave
    writes (a probe handler mutating ``latest_envelope`` + ``latest_route``
    + ``timeline`` + ``updated_at``) with reads (``component_snapshot``
    pulling those fields, or ``to_snapshot`` reading ``timeline[-10:]``
    and ``updated_at`` together). The public ``lock`` is an ``RLock``
    so internal locked methods can be called from inside an outer
    ``with session.lock:`` block without deadlocking.
    """

    def __init__(self, request: SessionCreateRequest) -> None:
        now = utc_now()
        self.session_id = uuid4()
        self.scenario_id = request.scenario_id
        self.mode = request.mode
        self.phase = "initialized"
        self.created_at = now
        self.updated_at = now
        self.timeline: list[TimelineEventSnapshot] = [
            TimelineEventSnapshot(
                component_id=ComponentId.F1,
                title="Session initialized",
                detail="P9a control API created a typed demo session.",
                status=SnapshotStatus.LIVE,
            )
        ]
        self.replay_cache = ReplayCache()
        self.latest_envelope = EnvelopeVerificationSnapshot(
            status=SnapshotStatus.PENDING,
            detail="No envelope has been checked in this session yet.",
        )
        self.latest_route = RouteApprovalSnapshot(
            status=SnapshotStatus.PENDING,
            detail="No route approval has been checked in this session yet.",
        )
        self.dp_ledger = DpLedgerSnapshot(
            status=SnapshotStatus.LIVE,
            entries=[],
            detail="No DP budget has been spent in this session yet.",
        )
        self.lock = threading.RLock()

    def append_event(self, event: TimelineEventSnapshot) -> TimelineEventSnapshot:
        with self.lock:
            self.timeline.append(event)
            self.updated_at = utc_now()
        return event

    def to_snapshot(self, components: list[ComponentReadinessSnapshot]) -> SessionSnapshot:
        with self.lock:
            return SessionSnapshot(
                session_id=self.session_id,
                scenario_id=self.scenario_id,
                mode=self.mode,
                phase=self.phase,
                created_at=self.created_at,
                updated_at=self.updated_at,
                components=components,
                latest_events=self.timeline[-10:],
            )


MAX_ACTIVE_SESSIONS = 50

# Module-level logger for server-side diagnostics that should not be exposed
# to the UI. Uses ``logging.getLogger(__name__)`` so deployments can route or
# silence ``backend.ui.state`` messages via the standard logging config
# without changing call sites.
_logger = logging.getLogger(__name__)

# backend/ui/state.py → backend/ui/ → backend/ → repo root.
# The demo runs from the repo root via `uv run uvicorn`, but a container
# image or any future installable-package layout can override the infra
# location at startup via the env var below. This keeps the local-dev
# default zero-config while preventing a hard dependency on the source
# tree's relative shape.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_INFRA_ROOT_ENV = "FEDERATED_SILO_INFRA_ROOT"


def _infra_root() -> Path:
    override = os.getenv(_INFRA_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT / "infra"

# `ShortText` allows up to 2048 chars, but a downstream library may
# produce a longer error string in unusual cases. Truncate at the
# assignment site to defense-in-depth against a Pydantic ValidationError
# surfacing as a 500 on what should be a refusal path.
_DETAIL_MAX_LEN = 2048
_DETAIL_ELLIPSIS = " …[truncated]"


def _truncate_detail(text: str, *, limit: int = _DETAIL_MAX_LEN) -> str:
    """Clamp a dynamic detail string to ShortText's max length."""
    if len(text) <= limit:
        return text
    head_len = max(limit - len(_DETAIL_ELLIPSIS), 1)
    return text[:head_len] + _DETAIL_ELLIPSIS


class DemoControlService:
    """Session registry plus controlled probe harness for the P9a API.

    Sessions are held in an in-memory FIFO bounded at ``MAX_ACTIVE_SESSIONS``.
    When the cap is reached, ``create_session`` evicts the oldest session
    so a long-running demo or automated probe sweep cannot grow the dict
    without bound. P15 will replace this with the real orchestrator
    session store, which owns persistence and TTLs.

    Thread-safe: FastAPI runs synchronous endpoints in a threadpool, so
    concurrent ``POST /sessions`` calls could race the FIFO eviction
    (two callers passing the size check, then either colliding on
    ``del self._sessions[oldest_id]`` with a ``KeyError`` or mutating
    the dict mid-iteration). ``_sessions_lock`` serializes the
    read-modify-write in ``create_session`` and the dict lookup in
    ``_session``. Same pattern as ``PrivacyBudgetLedger``.
    """

    def __init__(self) -> None:
        if MAX_ACTIVE_SESSIONS < 1:
            # Defensive: MAX_ACTIVE_SESSIONS is a module constant today,
            # but if a future config path lowers it to 0 or below, the
            # FIFO eviction loop in `create_session` would either spin
            # forever or hit `StopIteration` on `next(iter({}))`. Fail
            # loud at service construction instead.
            raise ValueError(
                f"MAX_ACTIVE_SESSIONS must be >= 1, got {MAX_ACTIVE_SESSIONS}"
            )
        self._principals = _build_demo_principals()
        self._allowlist = PrincipalAllowlist(_allowlist_entries(self._principals))
        # Python dicts preserve insertion order since 3.7, which gives us
        # FIFO eviction for free without pulling in collections.OrderedDict.
        self._sessions: dict[UUID, DemoSessionRuntime] = {}
        self._sessions_lock = threading.Lock()
        # NOTE on readiness caching: earlier rounds of review pushed
        # toward a cached readiness list (round 9 perf concern) and
        # then eager pre-population (round 11 race concern). Round 12
        # correctly observed that caching plus eager population creates
        # staleness — if the demo DB files are created after the
        # server starts, /system reports them missing forever. The
        # readiness build is ~3 filesystem stat calls; the demo call
        # volume (judges hit /system a handful of times per session)
        # does not justify the staleness risk. So we recompute readiness
        # on each call and accept the cheap I/O.

    def create_session(self, request: SessionCreateRequest) -> SessionSnapshot:
        session = DemoSessionRuntime(request)
        with self._sessions_lock:
            # Belt-and-braces with the __init__ validation: even if the
            # cap were somehow zeroed, `and self._sessions` keeps the
            # loop from `StopIteration`-ing on an empty dict.
            while len(self._sessions) >= MAX_ACTIVE_SESSIONS and self._sessions:
                oldest_id = next(iter(self._sessions))
                del self._sessions[oldest_id]
            self._sessions[session.session_id] = session
        return session.to_snapshot(self.component_readiness())

    def get_session(self, session_id: UUID) -> SessionSnapshot:
        return self._session(session_id).to_snapshot(self.component_readiness())

    def step_session(self, session_id: UUID) -> SessionSnapshot:
        session = self._session(session_id)
        with session.lock:
            session.phase = "p9a_placeholder_step"
            session.append_event(
                TimelineEventSnapshot(
                    component_id=ComponentId.F1,
                    title="Control-plane step recorded",
                    detail=(
                        "P9a does not run the full message bus; P15 will replace this "
                        "placeholder with orchestrator-driven transitions."
                    ),
                    status=SnapshotStatus.PENDING,
                )
            )
        return session.to_snapshot(self.component_readiness())

    def run_until_idle(self, session_id: UUID) -> SessionSnapshot:
        session = self._session(session_id)
        with session.lock:
            session.phase = "p9a_idle"
            session.append_event(
                TimelineEventSnapshot(
                    component_id=ComponentId.AUDIT_CHAIN,
                    title="No live orchestrator yet",
                    detail="P15 owns run-until-idle semantics; P9a reports typed placeholders.",
                    status=SnapshotStatus.NOT_BUILT,
                    blocked_by=SecurityLayer.NOT_BUILT,
                )
            )
        return session.to_snapshot(self.component_readiness())

    def timeline(self, session_id: UUID) -> list[TimelineEventSnapshot]:
        session = self._session(session_id)
        # `list(...)` iterates `session.timeline`; a concurrent
        # `append_event` from another threadpool worker can mutate
        # the list mid-iteration and surface
        # "RuntimeError: list changed size during iteration".
        with session.lock:
            return list(session.timeline)

    def component_snapshot(
        self,
        session_id: UUID,
        component_id: ComponentId,
        *,
        readiness_map: dict[ComponentId, ComponentReadinessSnapshot] | None = None,
        session: DemoSessionRuntime | None = None,
    ) -> ComponentSnapshot:
        # `readiness_map` is an internal optimisation for callers (e.g.
        # ``run_component_interaction``) that already built the readiness
        # map and want to avoid a second filesystem-stat pass. Public
        # callers can ignore the kwarg.
        #
        # `session` lets callers that already resolved the session and hold
        # `session.lock` pass it in. Without this, a re-entrant lookup here
        # would acquire `self._sessions_lock` while the caller holds
        # `session.lock`, inverting the lock order against
        # ``create_session`` / ``get_session`` (which hold
        # `_sessions_lock` first and then take `session.lock` via
        # ``to_snapshot``). AB-BA deadlock. Caught by Gemini PR-6 round 3.
        session = session or self._session(session_id)
        readiness = readiness_map or {
            item.component_id: item for item in self.component_readiness()
        }
        item = readiness[component_id]
        fields = [
            SnapshotField(name="available_after", value=item.available_after or "now"),
            SnapshotField(name="detail", value=item.detail),
        ]
        if component_id == ComponentId.SIGNING:
            return ComponentSnapshot(
                component_id=component_id,
                status=item.status,
                title=item.label,
                fields=fields,
                signing=self.signing_snapshot(),
            )
        # Reads below hold session.lock so the .status field stays consistent
        # with the snapshot object the caller receives (a concurrent probe
        # writer could otherwise swap the snapshot between the two reads).
        if component_id == ComponentId.ENVELOPE:
            with session.lock:
                envelope = session.latest_envelope
            return ComponentSnapshot(
                component_id=component_id,
                status=envelope.status,
                title=item.label,
                fields=fields,
                envelope=envelope,
            )
        if component_id == ComponentId.REPLAY:
            # `ReplayCache.to_snapshot` is internally locked (own
            # `threading.Lock`), so the session.lock here is for
            # pattern consistency with the other component branches
            # rather than strict necessity. Cheap, defensive, and
            # matches the audit invariant that one snapshot read
            # corresponds to one observable state.
            with session.lock:
                replay_snapshot = session.replay_cache.to_snapshot()
            return ComponentSnapshot(
                component_id=component_id,
                status=item.status,
                title=item.label,
                fields=fields,
                replay=replay_snapshot,
            )
        if component_id == ComponentId.ROUTE_APPROVAL:
            with session.lock:
                route = session.latest_route
            return ComponentSnapshot(
                component_id=component_id,
                status=route.status,
                title=item.label,
                fields=fields,
                route_approval=route,
            )
        if component_id == ComponentId.DP_LEDGER:
            with session.lock:
                ledger = session.dp_ledger
            return ComponentSnapshot(
                component_id=component_id,
                status=ledger.status,
                title=item.label,
                fields=fields,
                dp_ledger=ledger,
            )
        if component_id == ComponentId.F2:
            return ComponentSnapshot(
                component_id=component_id,
                status=item.status,
                title=item.label,
                fields=[
                    *fields,
                    SnapshotField(name="analysis_mode", value="hybrid"),
                    SnapshotField(name="clear_positive_rules", value="F2-B1,F2-B2"),
                    SnapshotField(name="input_boundary", value="dp_noised_aggregates"),
                ],
            )
        if component_id == ComponentId.F3:
            # Surface F3-specific operational state in the inspector: the
            # number of unique-hash entries loaded into the screener and
            # the screening mode (deterministic vs LLM-adjudicated; we are
            # always deterministic until P14/P15). Per the F3
            # non-disclosure contract, this intentionally does NOT break
            # the count down by source (SDN vs PEP); the per-source counts
            # would leak the shape of each list. The total-size signal is
            # public information about the watchlist file existing and
            # parsing, which the demo treats as acceptable to display.
            try:
                # Shares the ``load_watchlist`` lru_cache with
                # ``F3SanctionsAgent.__init__`` so the size reported in
                # the inspector is guaranteed to match what live agents
                # observe -- no separate snapshot cache that could drift
                # away from agent state if an agent is constructed with
                # a non-default path.
                watchlist = load_watchlist()
                watchlist_field = SnapshotField(
                    name="watchlist_size", value=str(watchlist.size)
                )
            except (ValueError, OSError):
                # File missing or invalid (e.g. test environment without
                # the data fixture). Surface as a field rather than 500
                # so the inspector renders something rather than crashing.
                # ``SanctionsWatchlist.from_path`` currently re-wraps
                # ``OSError`` into ``ValueError``, but catching both keeps
                # the snapshot resilient if that translation is ever
                # removed upstream -- the caller should not be coupled
                # to the loader's exception-translation policy.
                # Do NOT echo the underlying ``ValueError`` message into
                # the snapshot: it can include the resolved filesystem
                # path of the watchlist file or JSON parse details,
                # which is server-internal information the UI shouldn't
                # carry. The full exception (including the path /
                # parse-error context) IS logged server-side at WARNING
                # so a developer can diagnose; ``exc_info=True`` attaches
                # the traceback.
                _logger.warning(
                    "F3 sanctions watchlist failed to load for UI snapshot",
                    exc_info=True,
                )
                watchlist_field = SnapshotField(
                    name="watchlist_size",
                    value="unavailable: watchlist failed to load",
                )
            return ComponentSnapshot(
                component_id=component_id,
                status=item.status,
                title=item.label,
                fields=[
                    *fields,
                    watchlist_field,
                    SnapshotField(name="screening_mode", value="deterministic"),
                ],
            )
        elif component_id == ComponentId.F4:
            return ComponentSnapshot(
                component_id=component_id,
                status=item.status,
                title=item.label,
                fields=[
                    *fields,
                    SnapshotField(name="drafting_mode", value="llm_narrative"),
                    SnapshotField(name="structured_fields", value="deterministic"),
                    SnapshotField(
                        name="missing_input_behavior",
                        value="typed SARContributionRequest",
                    ),
                ],
            )
        if component_id in {ComponentId.LOBSTER_TRAP, ComponentId.LITELLM}:
            return ComponentSnapshot(
                component_id=component_id,
                status=item.status,
                title=item.label,
                fields=fields,
                provider_health=self.provider_health(),
            )
        if component_id == ComponentId.AUDIT_CHAIN:
            return ComponentSnapshot(
                component_id=component_id,
                status=item.status,
                title=item.label,
                fields=fields,
                audit_chain=AuditChainSnapshot(
                    status=item.status,
                    event_count=0,
                    detail=(
                        "Hash-chain persistence lands with P13/P15; P9a timeline "
                        "events are not counted as audit-chain events."
                    ),
                ),
            )
        return ComponentSnapshot(
            component_id=component_id,
            status=item.status,
            title=item.label,
            fields=fields,
        )

    def run_component_interaction(
        self,
        session_id: UUID,
        component_id: ComponentId,
        request: ComponentInteractionRequest,
    ) -> ComponentInteractionResult:
        # ``target_instance_id`` is typed as ``TrustDomainId`` (a
        # ``StrEnum``) on the request models, so FastAPI / Pydantic
        # automatically returns 422 for any value outside the canonical
        # five trust domains. This handler can assume any non-None value
        # is a valid ``TrustDomainId`` member.
        # Resolve session *outside* ``session.lock``. ``self._session(...)``
        # acquires ``self._sessions_lock``; doing so while holding
        # ``session.lock`` would invert the lock order against
        # ``create_session`` / ``get_session`` (which hold the sessions
        # lock first and then take a session lock via ``to_snapshot``).
        # AB-BA. The ``_session`` call releases ``_sessions_lock`` before
        # returning, so taking ``session.lock`` below is safe.
        session = self._session(session_id)
        readiness = {item.component_id: item for item in self.component_readiness()}
        readiness_item = readiness[component_id]

        # Atomic read-modify-write: hold ``session.lock`` across the
        # snapshot read and the timeline append so a concurrent probe
        # cannot tear the result (return a snapshot that no longer
        # matches the state recorded in the timeline event).
        #
        # ``session.lock`` is an ``RLock``, so ``append_event``'s own
        # ``with self.lock`` reacquires cheaply. We pass ``session=``
        # into ``component_snapshot`` so it skips the
        # ``self._session(...)`` lookup (which would otherwise take
        # ``self._sessions_lock`` while we hold ``session.lock`` and
        # reintroduce the AB-BA cycle).
        with session.lock:
            # Reuse the readiness map so we don't rebuild it
            # (3 filesystem stats) per request.
            snapshot = self.component_snapshot(
                session_id,
                component_id,
                readiness_map=readiness,
                session=session,
            )

            component_built = readiness_item.status != SnapshotStatus.NOT_BUILT
            is_read_only = request.interaction_kind in {
                ComponentInteractionKind.INSPECT,
                ComponentInteractionKind.EXPLAIN_STATE,
            }

            if not component_built:
                # Cannot process: the component itself does not exist yet.
                accepted = False
                executed = False
                status = SnapshotStatus.NOT_BUILT
                blocked_by: SecurityLayer | None = SecurityLayer.NOT_BUILT
                event_status = SnapshotStatus.BLOCKED
                reason = _truncate_detail(
                    f"{readiness_item.label} is available after "
                    f"{readiness_item.available_after or 'a later milestone'}."
                )
            elif is_read_only:
                # Live read-only interaction; a real handler ran and the
                # full snapshot is returned to the caller.
                accepted = True
                executed = True
                status = snapshot.status
                blocked_by = None
                event_status = status
                if request.interaction_kind == ComponentInteractionKind.INSPECT:
                    reason = _truncate_detail(
                        f"{readiness_item.label} snapshot returned."
                    )
                else:
                    # ``readiness_item.detail`` is also ShortText (up to 2048
                    # chars); concatenating with the label + status can exceed
                    # the cap and raise a Pydantic ValidationError -> 500. The
                    # truncate helper trims with an ellipsis suffix.
                    reason = _truncate_detail(
                        f"{readiness_item.label} is {snapshot.status.value}: "
                        f"{readiness_item.detail}"
                    )
            else:
                # PROMPT or SAFE_INPUT on a live component: the request is
                # accepted and recorded, but no live handler exists yet
                # (lands with P14/P15). Protected state stays untouched.
                accepted = True
                executed = False
                status = SnapshotStatus.PENDING
                blocked_by = None
                event_status = SnapshotStatus.PENDING
                reason = _interaction_placeholder_reason(
                    component_id,
                    interaction_kind=request.interaction_kind,
                    label=readiness_item.label,
                )

            event = TimelineEventSnapshot(
                component_id=component_id,
                title=f"Interaction: {request.interaction_kind.value}",
                detail=reason,
                status=event_status,
                blocked_by=blocked_by,
            )
            result = ComponentInteractionResult(
                interaction_kind=request.interaction_kind,
                target_component=component_id,
                target_instance_id=request.target_instance_id,
                attacker_profile=request.attacker_profile,
                accepted=accepted,
                executed=executed,
                status=status,
                blocked_by=blocked_by,
                reason=reason,
                timeline_event=event,
                component_snapshot=snapshot,
                available_after=readiness_item.available_after,
            )
            # ``append_event`` reacquires ``session.lock`` (RLock), keeping
            # the snapshot read and the timeline append in one atomic
            # critical section.
            session.append_event(event)
        return result

    def run_probe(self, session_id: UUID, request: ProbeRequest) -> ProbeResult:
        session = self._session(session_id)
        # Probe handlers run *outside* the session lock so a slow probe
        # (future LLM-driven LT injection, A3 with policy adapter, etc.)
        # cannot block other reads on the same session. The handlers
        # produce a `ProbeResult` whose `envelope` / `route_approval` /
        # `dp_ledger` fields carry the full state bundle to commit;
        # `_commit_probe_outcome` takes the lock briefly to apply the
        # bundle and append the timeline event in one critical section.
        try:
            result = self._dispatch_probe(session, request)
        except Exception as exc:  # noqa: BLE001
            # Probe handlers call into real agent code
            # (A3SiloResponderAgent, PrivacyBudgetLedger, etc.).
            # An unexpected internal failure should surface as a
            # structured timeline entry, not a 500. The judge
            # console can then render the breakdown distinctly
            # from a "security layer blocked the probe" outcome.
            # `accepted=False` because the attack did not
            # demonstrably succeed; `blocked_by=INTERNAL_ERROR`
            # marks the entry as a code failure rather than a
            # policy enforcement.
            result = _probe_result(
                request,
                accepted=False,
                blocked_by=SecurityLayer.INTERNAL_ERROR,
                reason=_truncate_detail(
                    f"Probe handler raised {type(exc).__name__}: {exc}"
                ),
            )

        self._commit_probe_outcome(session, result)
        return result

    def _dispatch_probe(
        self,
        session: DemoSessionRuntime,
        request: ProbeRequest,
    ) -> ProbeResult:
        if request.probe_kind == ProbeKind.UNSIGNED_MESSAGE:
            return self._unsigned_message_probe(session, request)
        if request.probe_kind == ProbeKind.BODY_TAMPER:
            return self._body_tamper_probe(session, request)
        if request.probe_kind == ProbeKind.WRONG_ROLE:
            return self._wrong_role_probe(session, request)
        if request.probe_kind == ProbeKind.REPLAY_NONCE:
            return self._replay_probe(session, request)
        if request.probe_kind == ProbeKind.ROUTE_MISMATCH:
            return self._route_mismatch_probe(session, request)
        if request.probe_kind == ProbeKind.BUDGET_EXHAUSTION:
            return self._budget_exhaustion_probe(session, request)
        return self._placeholder_probe(session, request)

    def _commit_probe_outcome(
        self,
        session: DemoSessionRuntime,
        result: ProbeResult,
    ) -> None:
        # Short critical section: copy the probe's state bundle onto
        # the session and append the timeline event so a concurrent
        # reader sees either the full prior state or the full new
        # state, never a half-applied probe outcome.
        with session.lock:
            if result.envelope is not None:
                session.latest_envelope = result.envelope
            if result.route_approval is not None:
                session.latest_route = result.route_approval
            if result.dp_ledger is not None:
                session.dp_ledger = result.dp_ledger
            session.append_event(result.timeline_event)

    def system_snapshot(self) -> SystemSnapshot:
        return SystemSnapshot(
            status=SnapshotStatus.LIVE,
            components=self.component_readiness(),
            provider_health=self.provider_health(),
            detail="P9a control API is running with local in-memory session state.",
        )

    def signing_snapshot(self) -> SigningStateSnapshot:
        return SigningStateSnapshot(
            status=SnapshotStatus.LIVE,
            known_signing_key_ids=sorted(
                principal.signing_key_id for principal in self._principals.values()
            ),
            detail="Demo private keys are retained server-side only.",
        )

    def provider_health(self) -> ProviderHealthSnapshot:
        # Anchor the infra path on this file rather than the current
        # working directory so the same code reports correctly whether
        # the server is started from the repo root, a container WORKDIR,
        # or a Cloud Run / unit-test temp dir. A deploy can override the
        # location with the `FEDERATED_SILO_INFRA_ROOT` env var if the
        # source tree layout does not match the installed layout.
        infra_root = _infra_root()
        return ProviderHealthSnapshot(
            status=SnapshotStatus.PENDING,
            lobster_trap_configured=(infra_root / "lobstertrap").exists(),
            litellm_configured=(infra_root / "litellm_config.yaml").exists(),
            gemini_api_key_present=bool(os.getenv("GEMINI_API_KEY")),
            openrouter_api_key_present=bool(os.getenv("OPENROUTER_API_KEY")),
            detail=(
                "P9a reports configuration presence only; live LT/LiteLLM verdict "
                "adapters land with P14/P15."
            ),
        )

    def component_readiness(self) -> list[ComponentReadinessSnapshot]:
        db_status = _database_detail()
        return [
            _component(ComponentId.A1, "A1 local monitor", SnapshotStatus.LIVE, "P6 complete."),
            _component(ComponentId.A2, "A2 investigator", SnapshotStatus.LIVE, "P8 complete."),
            _component(ComponentId.F1, "F1 coordinator", SnapshotStatus.LIVE, "P9 complete."),
            _component(ComponentId.BANK_ALPHA_A3, "Bank Alpha A3", SnapshotStatus.LIVE, "P8a complete."),
            _component(ComponentId.BANK_BETA_A3, "Bank Beta A3", SnapshotStatus.LIVE, "P8a complete."),
            _component(ComponentId.BANK_GAMMA_A3, "Bank Gamma A3", SnapshotStatus.LIVE, "P8a complete."),
            _component(ComponentId.P7, "P7 stats primitives", SnapshotStatus.LIVE, db_status),
            _component(ComponentId.F3, "F3 sanctions", SnapshotStatus.LIVE, "P10 complete."),
            _component(ComponentId.F2, "F2 graph analysis", SnapshotStatus.LIVE, "P11 complete."),
            _component(ComponentId.F4, "F4 SAR drafter", SnapshotStatus.LIVE, "P12 complete."),
            _component(ComponentId.F5, "F5 auditor", SnapshotStatus.NOT_BUILT, "Available after P13.", "P13"),
            _component(ComponentId.LOBSTER_TRAP, "Lobster Trap", SnapshotStatus.PENDING, "P0 scaffolded; API verdict adapter lands P14."),
            _component(ComponentId.LITELLM, "LiteLLM", SnapshotStatus.PENDING, "P0 scaffolded; provider health adapter lands P14/P15."),
            _component(ComponentId.SIGNING, "Signing", SnapshotStatus.LIVE, "Ed25519 envelope helpers are live."),
            _component(ComponentId.ENVELOPE, "Envelope verification", SnapshotStatus.LIVE, "Security envelope checks are live."),
            _component(ComponentId.REPLAY, "Replay cache", SnapshotStatus.LIVE, "In-memory replay cache is live."),
            _component(ComponentId.ROUTE_APPROVAL, "Route approvals", SnapshotStatus.LIVE, "F1/A3 route-approval binding is live."),
            _component(ComponentId.DP_LEDGER, "DP ledger", SnapshotStatus.LIVE, "P7 rho ledger is live."),
            _component(ComponentId.AUDIT_CHAIN, "Audit chain", SnapshotStatus.NOT_BUILT, "Hash-chain persistence lands P13/P15.", "P13/P15"),
        ]

    def _unsigned_message_probe(
        self,
        session: DemoSessionRuntime,
        request: ProbeRequest,
    ) -> ProbeResult:
        message = _base_a2_query(nonce=f"unsigned-{uuid4()}")
        try:
            self._allowlist.verify_message(message, replay_cache=session.replay_cache)
        except SecurityEnvelopeError as exc:
            # Catch the envelope base class rather than only
            # PrincipalNotAllowed: an unsigned message currently
            # surfaces as PrincipalNotAllowed("missing signing_key_id"),
            # but a future signing-helper variant could raise
            # SignatureInvalid for an absent signature. Either is a
            # valid "signature gate refused" outcome from the UI
            # perspective.
            envelope = _envelope_snapshot(
                message,
                status=SnapshotStatus.LIVE,
                signature_status="missing",
                blocked_by=SecurityLayer.SIGNATURE,
                detail=str(exc),
            )
            return _probe_result(
                request,
                accepted=False,
                blocked_by=SecurityLayer.SIGNATURE,
                reason="Unsigned message was rejected before F1 route planning.",
                envelope=envelope,
            )
        return _unexpected_acceptance(
            request,
            reason="Unsigned message was unexpectedly accepted; signature gate did not refuse.",
        )

    def _body_tamper_probe(
        self,
        session: DemoSessionRuntime,
        request: ProbeRequest,
    ) -> ProbeResult:
        message = self._signed_a2_query(nonce=f"tamper-{uuid4()}")
        tampered = message.model_copy(
            update={"requesting_investigator_id": "investigator-alpha-tampered"}
        )
        try:
            self._allowlist.verify_message(tampered, replay_cache=session.replay_cache)
        except SignatureInvalid as exc:
            envelope = _envelope_snapshot(
                tampered,
                status=SnapshotStatus.LIVE,
                signature_status="invalid",
                blocked_by=SecurityLayer.SIGNATURE,
                detail=str(exc),
            )
            return _probe_result(
                request,
                accepted=False,
                blocked_by=SecurityLayer.SIGNATURE,
                reason="Body was modified after signing; canonical body hash failed.",
                envelope=envelope,
            )
        return _unexpected_acceptance(
            request,
            reason="Tampered body was unexpectedly accepted; body-hash gate did not refuse.",
        )

    def _wrong_role_probe(
        self,
        session: DemoSessionRuntime,
        request: ProbeRequest,
    ) -> ProbeResult:
        principal = self._principals["bank_beta.A3"]
        message = _base_a2_query(
            sender_agent_id=principal.agent_id,
            sender_role=AgentRole.F1,
            sender_bank_id=principal.bank_id,
            nonce=f"wrong-role-{uuid4()}",
        )
        signed = sign_message(
            message,
            private_key=principal.private_key,
            signing_key_id=principal.signing_key_id,
        )
        try:
            self._allowlist.verify_message(signed, replay_cache=session.replay_cache)
        except PrincipalNotAllowed as exc:
            envelope = _envelope_snapshot(
                signed,
                status=SnapshotStatus.LIVE,
                signature_status="valid",
                blocked_by=SecurityLayer.ALLOWLIST,
                detail=str(exc),
            )
            return _probe_result(
                request,
                accepted=False,
                blocked_by=SecurityLayer.ALLOWLIST,
                reason="A3 signing key claimed an F1 sender role and was denied.",
                envelope=envelope,
            )
        return _unexpected_acceptance(
            request,
            reason="Wrong-role sender was unexpectedly accepted; allowlist gate did not refuse.",
        )

    def _replay_probe(
        self,
        session: DemoSessionRuntime,
        request: ProbeRequest,
    ) -> ProbeResult:
        message = self._signed_a2_query(nonce=f"replay-{uuid4()}")
        self._allowlist.verify_message(message, replay_cache=session.replay_cache)
        try:
            self._allowlist.verify_message(message, replay_cache=session.replay_cache)
        except ReplayDetected as exc:
            envelope = _envelope_snapshot(
                message,
                status=SnapshotStatus.LIVE,
                signature_status="valid",
                freshness_status="fresh",
                blocked_by=SecurityLayer.REPLAY,
                detail=str(exc),
            )
            return _probe_result(
                request,
                accepted=False,
                blocked_by=SecurityLayer.REPLAY,
                reason="Second use of the same nonce was rejected.",
                envelope=envelope,
                replay=session.replay_cache.to_snapshot(),
            )
        return _unexpected_acceptance(
            request,
            reason="Replayed nonce was unexpectedly accepted; replay-cache gate did not refuse.",
            replay=session.replay_cache.to_snapshot(),
        )

    def _route_mismatch_probe(
        self,
        session: DemoSessionRuntime,
        request: ProbeRequest,
    ) -> ProbeResult:
        message = self._signed_f1_routed_query(nonce=f"route-{uuid4()}")
        principal = self._principals["federation.F1"]
        tampered_unsigned = message.model_copy(
            update={"requested_rho_per_primitive": 0.02}
        )
        tampered = sign_message(
            tampered_unsigned,
            private_key=principal.private_key,
            signing_key_id=principal.signing_key_id,
        )
        approved_hash = message.route_approval.approved_query_body_hash if message.route_approval else None
        computed_hash = approved_body_hash(tampered)
        if approved_hash == computed_hash:
            # Internal-setup invariant: the probe's tampered body
            # somehow hashed to the original approved hash, so the
            # tampering never happened. Using `RuntimeError` rather
            # than `AssertionError` because the latter is loosely
            # associated with `assert` statements (which are stripped
            # by `python -O`); the explicit raise form isn't stripped,
            # but RuntimeError is the cleaner semantic for a
            # service-layer code-invariant violation.
            raise RuntimeError("route mismatch probe did not change approved body hash")
        response = self._beta_a3(session).run(A3TurnInput(request=tampered))
        if response.refusal_reason != "route_violation":
            # A3 accepted a body that no longer matches the signed route
            # approval — surface as a structured probe-accepted result so
            # the judge console sees the breach instead of a 500.
            return _unexpected_acceptance(
                request,
                reason=(
                    "Tampered routed query was unexpectedly accepted; "
                    f"A3 returned refusal_reason={response.refusal_reason!r} "
                    "instead of route_violation."
                ),
            )
        envelope = _envelope_snapshot(
            tampered,
            status=SnapshotStatus.LIVE,
            signature_status="valid",
            freshness_status="fresh",
            detail="F1-signed routed query passed envelope checks before A3 route binding.",
        )
        route = RouteApprovalSnapshot(
            status=SnapshotStatus.BLOCKED,
            query_id=message.query_id,
            route_kind=RouteKind.PEER_314B,
            approved_query_body_hash=approved_hash,
            computed_query_body_hash=computed_hash,
            requester_bank_id=BankId.BANK_ALPHA,
            responder_bank_id=BankId.BANK_BETA,
            binding_status="mismatched",
            detail="Routed query body no longer matches the signed route approval.",
        )
        return _probe_result(
            request,
            accepted=False,
            blocked_by=SecurityLayer.ROUTE_APPROVAL,
            reason="A3 rejected the F1-signed query because route approval binding failed.",
            envelope=envelope,
            route_approval=route,
        )

    def _budget_exhaustion_probe(
        self,
        session: DemoSessionRuntime,
        request: ProbeRequest,
    ) -> ProbeResult:
        ledger = PrivacyBudgetLedger(rho_max=0.01)
        requester = RequesterKey(
            requesting_investigator_id="investigator-alpha",
            requesting_bank_id=BankId.BANK_ALPHA,
            responding_bank_id=BankId.BANK_BETA,
        )
        debit = ledger.debit(requester, 0.02)
        dp_ledger = DpLedgerSnapshot(
            status=SnapshotStatus.LIVE,
            entries=[
                DpLedgerEntrySnapshot(
                    requester_key=_redacted_requester_key(requester),
                    responding_bank_id=BankId.BANK_BETA,
                    rho_spent=debit.rho_spent,
                    rho_remaining=debit.rho_remaining,
                    rho_max=ledger.rho_max,
                )
            ],
            detail="Budget-exhaustion probe used the real P7 ledger refusal path.",
        )
        return _probe_result(
            request,
            accepted=False,
            blocked_by=SecurityLayer.P7_BUDGET,
            reason="Requested rho would exceed the requester-bank budget.",
            dp_ledger=dp_ledger,
        )

    def _placeholder_probe(
        self,
        session: DemoSessionRuntime,
        request: ProbeRequest,
    ) -> ProbeResult:
        _ = session
        layer = (
            SecurityLayer.LOBSTER_TRAP
            if request.probe_kind == ProbeKind.PROMPT_INJECTION
            else SecurityLayer.A3_POLICY
        )
        return _probe_result(
            request,
            accepted=False,
            blocked_by=SecurityLayer.NOT_BUILT,
            reason=f"{layer.value} live probe adapter is scheduled for a later milestone.",
        )

    def _signed_a2_query(self, *, nonce: str) -> Sec314bQuery:
        principal = self._principals["bank_alpha.A2"]
        return sign_message(
            _base_a2_query(nonce=nonce),
            private_key=principal.private_key,
            signing_key_id=principal.signing_key_id,
        )

    def _signed_f1_routed_query(self, *, nonce: str) -> Sec314bQuery:
        principal = self._principals["federation.F1"]
        unsigned = _base_a2_query(
            sender_agent_id=principal.agent_id,
            sender_role=principal.role,
            sender_bank_id=principal.bank_id,
            recipient_agent_id="bank_beta.A3",
            nonce=nonce,
        )
        approval = RouteApproval(
            query_id=unsigned.query_id,
            route_kind=RouteKind.PEER_314B,
            approved_query_body_hash=approved_body_hash(unsigned),
            requesting_bank_id=BankId.BANK_ALPHA,
            responding_bank_id=BankId.BANK_BETA,
            approved_by_agent_id=principal.agent_id,
            expires_at=utc_now() + timedelta(minutes=5),
        )
        signed_approval = sign_model_signature(
            approval,
            private_key=principal.private_key,
            signing_key_id=principal.signing_key_id,
        )
        # `StrictModel` (Sec314bQuery's base) has `validate_assignment=True`,
        # so `model_copy(update=...)` re-runs validators on the changed
        # `route_approval` field. No need for the
        # `model_validate(model_dump())` round-trip.
        routed = unsigned.model_copy(update={"route_approval": signed_approval})
        return sign_message(
            routed,
            private_key=principal.private_key,
            signing_key_id=principal.signing_key_id,
        )

    def _beta_a3(self, session: DemoSessionRuntime) -> A3SiloResponderAgent:
        return A3SiloResponderAgent(
            bank_id=BankId.BANK_BETA,
            runtime=AgentRuntimeContext(
                node_id="ui-probe-bank-beta",
                trust_domain=TrustDomain.BANK_SILO,
            ),
            principal_allowlist=self._allowlist,
            replay_cache=session.replay_cache,
        )

    def _session(self, session_id: UUID) -> DemoSessionRuntime:
        # Lock the lookup so a concurrent eviction can never surface
        # a transient KeyError for a still-valid session_id.
        with self._sessions_lock:
            try:
                return self._sessions[session_id]
            except KeyError as exc:
                raise KeyError(f"unknown session_id: {session_id}") from exc


def _build_demo_principals() -> dict[str, DemoPrincipal]:
    specs = [
        ("bank_alpha.A2", AgentRole.A2, BankId.BANK_ALPHA),
        ("bank_beta.A3", AgentRole.A3, BankId.BANK_BETA),
        ("federation.F1", AgentRole.F1, BankId.FEDERATION),
        ("bank_alpha.F6", AgentRole.F6, BankId.BANK_ALPHA),
        ("bank_beta.F6", AgentRole.F6, BankId.BANK_BETA),
        ("bank_gamma.F6", AgentRole.F6, BankId.BANK_GAMMA),
        ("federation.F6", AgentRole.F6, BankId.FEDERATION),
    ]
    principals: dict[str, DemoPrincipal] = {}
    for agent_id, role, bank_id in specs:
        pair = generate_key_pair(f"{agent_id}.demo-key")
        principals[agent_id] = DemoPrincipal(
            agent_id=agent_id,
            role=role,
            bank_id=bank_id,
            signing_key_id=pair.signing_key_id,
            private_key=pair.private_key,
            public_key=pair.public_key,
        )
    return principals


def _allowlist_entries(principals: dict[str, DemoPrincipal]) -> list[PrincipalAllowlistEntry]:
    alpha_a2 = principals["bank_alpha.A2"]
    beta_a3 = principals["bank_beta.A3"]
    f1 = principals["federation.F1"]
    entries = [
        PrincipalAllowlistEntry(
            agent_id=alpha_a2.agent_id,
            role=alpha_a2.role,
            bank_id=alpha_a2.bank_id,
            signing_key_id=alpha_a2.signing_key_id,
            public_key=alpha_a2.public_key,
            allowed_message_types=[MessageType.SEC314B_QUERY.value],
            allowed_recipients=["federation.F1"],
        ),
        PrincipalAllowlistEntry(
            agent_id=beta_a3.agent_id,
            role=beta_a3.role,
            bank_id=beta_a3.bank_id,
            signing_key_id=beta_a3.signing_key_id,
            public_key=beta_a3.public_key,
            allowed_message_types=[MessageType.SEC314B_RESPONSE.value],
            allowed_recipients=["federation.F1"],
        ),
        PrincipalAllowlistEntry(
            agent_id=f1.agent_id,
            role=f1.role,
            bank_id=f1.bank_id,
            signing_key_id=f1.signing_key_id,
            public_key=f1.public_key,
            allowed_message_types=[
                MessageType.SEC314B_QUERY.value,
                MessageType.LOCAL_SILO_CONTRIBUTION_REQUEST.value,
                # F1 emits the aggregate Sec314bResponse back to the requester A2.
                MessageType.SEC314B_RESPONSE.value,
            ],
            allowed_recipients=["*"],
            allowed_routes=[RouteKind.PEER_314B, RouteKind.LOCAL_CONTRIBUTION],
        ),
    ]
    entries.extend(
        PrincipalAllowlistEntry(
            agent_id=principal.agent_id,
            role=principal.role,
            bank_id=principal.bank_id,
            signing_key_id=principal.signing_key_id,
            public_key=principal.public_key,
            allowed_message_types=[
                MessageType.POLICY_EVALUATION_RESULT.value,
                MessageType.AUDIT_EVENT.value,
            ],
            allowed_recipients=["*"],
        )
        for principal in principals.values()
        if principal.role == AgentRole.F6
    )
    return entries


def _base_a2_query(
    *,
    sender_agent_id: str = "bank_alpha.A2",
    sender_role: AgentRole = AgentRole.A2,
    sender_bank_id: BankId = BankId.BANK_ALPHA,
    recipient_agent_id: str = "federation.F1",
    nonce: str,
) -> Sec314bQuery:
    return Sec314bQuery(
        sender_agent_id=sender_agent_id,
        sender_role=sender_role,
        sender_bank_id=sender_bank_id,
        recipient_agent_id=recipient_agent_id,
        expires_at=utc_now() + timedelta(minutes=5),
        nonce=nonce,
        requesting_investigator_id="investigator-alpha",
        requesting_bank_id=BankId.BANK_ALPHA,
        target_bank_ids=[BankId.BANK_BETA],
        query_shape=QueryShape.ENTITY_PRESENCE,
        query_payload=EntityPresencePayload(name_hashes=["aaaaaaaaaaaaaaaa"]),
        purpose_declaration=PurposeDeclaration(
            typology_code=TypologyCode.STRUCTURING,
            suspicion_rationale="Structuring signals require peer-bank corroboration.",
            supporting_alert_ids=[uuid4()],
        ),
    )


def _component(
    component_id: ComponentId,
    label: str,
    status: SnapshotStatus,
    detail: str,
    available_after: str | None = None,
) -> ComponentReadinessSnapshot:
    return ComponentReadinessSnapshot(
        component_id=component_id,
        label=label,
        status=status,
        available_after=available_after,
        detail=detail,
    )


def _database_detail() -> str:
    missing = [
        bank_id.value
        for bank_id in (BankId.BANK_ALPHA, BankId.BANK_BETA, BankId.BANK_GAMMA)
        if not bank_db_path(bank_id).exists()
    ]
    if missing:
        return f"P7 is live, but demo DBs are missing for: {', '.join(missing)}."
    return "P7 is live and all three demo bank DBs are present."


def _redacted_requester_key(requester: RequesterKey) -> str:
    digest = hashlib.sha256(requester.stable_key.encode("utf-8")).hexdigest()[:16]
    return f"requester:{digest}"


def _interaction_placeholder_reason(
    component_id: ComponentId,
    *,
    interaction_kind: ComponentInteractionKind,
    label: str,
) -> str:
    """Describe accepted-but-not-executed prompt paths for the UI.

    P9b can route demo input to either the LT policy gate or the direct
    LiteLLM/model-route harness. The live LT verdict and provider call
    still land in P14/P15, so the wording must make clear which boundary
    was reached and what is not yet executing.
    """
    if component_id == ComponentId.LITELLM:
        return _truncate_detail(
            f"{interaction_kind.value} reached the LiteLLM/model route directly. "
            "Live provider execution lands with P14/P15, so no model call was made yet. "
            "No protected state was mutated."
        )
    if component_id == ComponentId.LOBSTER_TRAP:
        return _truncate_detail(
            f"{interaction_kind.value} reached the Lobster Trap policy gate. "
            "Live LT verdicts and model forwarding land with P14/P15. "
            "No protected state was mutated."
        )
    return _truncate_detail(
        f"{interaction_kind.value} was recorded for {label}; the live handler lands "
        "with P14/P15. No protected state was mutated."
    )


def _envelope_snapshot(
    message: Sec314bQuery,
    *,
    status: SnapshotStatus,
    signature_status: Literal["valid", "invalid", "missing", "not_checked"],
    detail: str,
    blocked_by: SecurityLayer | None = None,
    freshness_status: Literal["fresh", "expired", "not_checked"] = "not_checked",
) -> EnvelopeVerificationSnapshot:
    return EnvelopeVerificationSnapshot(
        status=status,
        message_type=message.message_type,
        sender_agent_id=message.sender_agent_id,
        recipient_agent_id=message.recipient_agent_id,
        body_hash=message.body_hash,
        signature_status=signature_status,
        freshness_status=freshness_status,
        blocked_by=blocked_by,
        detail=_truncate_detail(detail),
    )


def _unexpected_acceptance(
    request: ProbeRequest,
    *,
    reason: str,
    envelope: EnvelopeVerificationSnapshot | None = None,
    replay: ReplayCacheSnapshot | None = None,
    route_approval: RouteApprovalSnapshot | None = None,
    dp_ledger: DpLedgerSnapshot | None = None,
) -> ProbeResult:
    """Build the structured "probe attack succeeded" outcome.

    If a security layer that should have refused a probe instead let
    it through, that is a real security event in the demo context,
    not an API error. The judge console renders this as
    ``accepted=True``/``status=ERROR`` so the breach is a first-class
    timeline entry. Test assertions on `accepted is False` still
    catch the regression loudly without depending on a 500.
    """
    return _probe_result(
        request,
        accepted=True,
        blocked_by=SecurityLayer.ACCEPTED,
        reason=reason,
        envelope=envelope,
        replay=replay,
        route_approval=route_approval,
        dp_ledger=dp_ledger,
    )


def _probe_result(
    request: ProbeRequest,
    *,
    accepted: bool,
    blocked_by: SecurityLayer,
    reason: str,
    envelope: EnvelopeVerificationSnapshot | None = None,
    replay: ReplayCacheSnapshot | None = None,
    route_approval: RouteApprovalSnapshot | None = None,
    dp_ledger: DpLedgerSnapshot | None = None,
) -> ProbeResult:
    event = TimelineEventSnapshot(
        component_id=request.target_component,
        title=f"Probe: {request.probe_kind.value}",
        detail=reason,
        status=SnapshotStatus.ERROR if accepted else SnapshotStatus.BLOCKED,
        blocked_by=blocked_by,
    )
    return ProbeResult(
        probe_kind=request.probe_kind,
        target_component=request.target_component,
        attacker_profile=request.attacker_profile,
        accepted=accepted,
        blocked_by=blocked_by,
        reason=reason,
        envelope=envelope,
        replay=replay,
        route_approval=route_approval,
        dp_ledger=dp_ledger,
        timeline_event=event,
    )
