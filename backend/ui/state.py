"""In-memory P9a demo-control service.

This module deliberately exposes only a demo control plane. It can inspect
state and inject probes through normal security boundaries, but it does not
own privileged mutators such as "approve route" or "mark signature valid".
"""

from __future__ import annotations

import os
import hashlib
from datetime import timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.a3_silo_responder import A3SiloResponderAgent
from backend.agents.a3_states import A3TurnInput
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
    """Mutable in-memory session state for local demo control."""

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

    def append_event(self, event: TimelineEventSnapshot) -> TimelineEventSnapshot:
        self.timeline.append(event)
        self.updated_at = utc_now()
        return event

    def to_snapshot(self, components: list[ComponentReadinessSnapshot]) -> SessionSnapshot:
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


class DemoControlService:
    """Session registry plus controlled probe harness for the P9a API."""

    def __init__(self) -> None:
        self._principals = _build_demo_principals()
        self._allowlist = PrincipalAllowlist(_allowlist_entries(self._principals))
        self._sessions: dict[UUID, DemoSessionRuntime] = {}

    def create_session(self, request: SessionCreateRequest) -> SessionSnapshot:
        session = DemoSessionRuntime(request)
        self._sessions[session.session_id] = session
        return session.to_snapshot(self.component_readiness())

    def get_session(self, session_id: UUID) -> SessionSnapshot:
        return self._session(session_id).to_snapshot(self.component_readiness())

    def step_session(self, session_id: UUID) -> SessionSnapshot:
        session = self._session(session_id)
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
        return list(self._session(session_id).timeline)

    def component_snapshot(self, session_id: UUID, component_id: ComponentId) -> ComponentSnapshot:
        session = self._session(session_id)
        readiness = {item.component_id: item for item in self.component_readiness()}
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
        if component_id == ComponentId.ENVELOPE:
            return ComponentSnapshot(
                component_id=component_id,
                status=session.latest_envelope.status,
                title=item.label,
                fields=fields,
                envelope=session.latest_envelope,
            )
        if component_id == ComponentId.REPLAY:
            return ComponentSnapshot(
                component_id=component_id,
                status=item.status,
                title=item.label,
                fields=fields,
                replay=session.replay_cache.to_snapshot(),
            )
        if component_id == ComponentId.ROUTE_APPROVAL:
            return ComponentSnapshot(
                component_id=component_id,
                status=session.latest_route.status,
                title=item.label,
                fields=fields,
                route_approval=session.latest_route,
            )
        if component_id == ComponentId.DP_LEDGER:
            return ComponentSnapshot(
                component_id=component_id,
                status=session.dp_ledger.status,
                title=item.label,
                fields=fields,
                dp_ledger=session.dp_ledger,
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

    def run_probe(self, session_id: UUID, request: ProbeRequest) -> ProbeResult:
        session = self._session(session_id)
        if request.probe_kind == ProbeKind.UNSIGNED_MESSAGE:
            result = self._unsigned_message_probe(session, request)
        elif request.probe_kind == ProbeKind.BODY_TAMPER:
            result = self._body_tamper_probe(session, request)
        elif request.probe_kind == ProbeKind.WRONG_ROLE:
            result = self._wrong_role_probe(session, request)
        elif request.probe_kind == ProbeKind.REPLAY_NONCE:
            result = self._replay_probe(session, request)
        elif request.probe_kind == ProbeKind.ROUTE_MISMATCH:
            result = self._route_mismatch_probe(session, request)
        elif request.probe_kind == ProbeKind.BUDGET_EXHAUSTION:
            result = self._budget_exhaustion_probe(session, request)
        else:
            result = self._placeholder_probe(session, request)

        session.append_event(result.timeline_event)
        return result

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
        infra_root = Path("infra")
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
            _component(ComponentId.F3, "F3 sanctions", SnapshotStatus.NOT_BUILT, "Available after P10.", "P10"),
            _component(ComponentId.F2, "F2 graph analysis", SnapshotStatus.NOT_BUILT, "Available after P11.", "P11"),
            _component(ComponentId.F4, "F4 SAR drafter", SnapshotStatus.NOT_BUILT, "Available after P12.", "P12"),
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
        except PrincipalNotAllowed as exc:
            envelope = _envelope_snapshot(
                message,
                status=SnapshotStatus.LIVE,
                signature_status="missing",
                blocked_by=SecurityLayer.SIGNATURE,
                detail=str(exc),
            )
            session.latest_envelope = envelope
            return _probe_result(
                request,
                accepted=False,
                blocked_by=SecurityLayer.SIGNATURE,
                reason="Unsigned message was rejected before F1 route planning.",
                envelope=envelope,
            )
        raise AssertionError("unsigned probe unexpectedly passed")

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
            session.latest_envelope = envelope
            return _probe_result(
                request,
                accepted=False,
                blocked_by=SecurityLayer.SIGNATURE,
                reason="Body was modified after signing; canonical body hash failed.",
                envelope=envelope,
            )
        raise AssertionError("body tamper probe unexpectedly passed")

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
            session.latest_envelope = envelope
            return _probe_result(
                request,
                accepted=False,
                blocked_by=SecurityLayer.ALLOWLIST,
                reason="A3 signing key claimed an F1 sender role and was denied.",
                envelope=envelope,
            )
        raise AssertionError("wrong-role probe unexpectedly passed")

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
            session.latest_envelope = envelope
            return _probe_result(
                request,
                accepted=False,
                blocked_by=SecurityLayer.REPLAY,
                reason="Second use of the same nonce was rejected.",
                envelope=envelope,
                replay=session.replay_cache.to_snapshot(),
            )
        raise AssertionError("replay probe unexpectedly passed")

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
            raise AssertionError("route mismatch probe did not change approved body hash")
        response = self._beta_a3(session).run(A3TurnInput(request=tampered))
        if response.refusal_reason != "route_violation":
            raise AssertionError("route mismatch probe did not reach A3 route validation")
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
        session.latest_envelope = envelope
        session.latest_route = route
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
        session.dp_ledger = DpLedgerSnapshot(
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
        routed = Sec314bQuery.model_validate(
            unsigned.model_copy(update={"route_approval": signed_approval}).model_dump()
        )
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
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"unknown session_id: {session_id}") from exc


def _build_demo_principals() -> dict[str, DemoPrincipal]:
    specs = [
        ("bank_alpha.A2", AgentRole.A2, BankId.BANK_ALPHA),
        ("bank_beta.A3", AgentRole.A3, BankId.BANK_BETA),
        ("federation.F1", AgentRole.F1, BankId.FEDERATION),
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
    return [
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
        detail=detail,
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
        timeline_event=event,
    )


def security_error_layer(exc: SecurityEnvelopeError) -> SecurityLayer:
    """Map envelope exceptions to UI layer labels."""
    if isinstance(exc, SignatureInvalid):
        return SecurityLayer.SIGNATURE
    if isinstance(exc, PrincipalNotAllowed):
        return SecurityLayer.ALLOWLIST
    if isinstance(exc, ReplayDetected):
        return SecurityLayer.REPLAY
    return SecurityLayer.FRESHNESS
