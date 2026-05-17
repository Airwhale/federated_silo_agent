"""Local live orchestrator for the P15 control API adapter."""

from __future__ import annotations

from collections.abc import Container
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from uuid import UUID, uuid5

from backend.demo.seeds import (
    CANONICAL_ALERT_TRANSACTION_ID,
    CANONICAL_WINDOW_END,
    S1_CONTRIBUTIONS,
    S1_ENTITY_HASHES,
    canonical_signal_candidate,
)
from backend.agents.a2_states import CorrelatedAlertSummary
from backend.agents.a3_states import A3TurnInput
from backend.agents.f1_states import (
    F1AggregationInput,
    F1InboundQueryInput,
    F1RoutePlan,
    F1TurnInput,
)
from backend.orchestrator.audit_normalizer import (
    PolicyEvaluationRecord,
    PrimitiveAuditRecord,
    build_audit_review_request,
)
from backend.orchestrator.agents import AgentRegistry, OrchestratorPrincipals
from backend.orchestrator.audit import OrchestratorAuditRecorder
from backend.orchestrator.state_machine import AgentTurn, next_turn
from backend.security import approved_body_hash, sign_message
from backend.silos.budget import RequesterKey
from shared.enums import (
    AgentRole,
    BankId,
    MessageType,
    PatternClass,
    PolicyContentChannel,
)
from shared.messages import (
    AgentMessage,
    Alert,
    AuditReviewRequest,
    AuditReviewResult,
    DismissalRationale,
    EvidenceItem,
    GraphPatternRequest,
    GraphPatternResponse,
    LocalSiloContributionRequest,
    PolicyEvaluationRequest,
    SARAssemblyRequest,
    SARContribution,
    SARContributionRequest,
    SARDraft,
    SanctionsCheckRequest,
    SanctionsCheckResponse,
    Sec314bQuery,
    Sec314bResponse,
    utc_now,
)


_CORRELATED_ALERT_NAMESPACE = UUID("4ad75c24-d9b4-4f71-a947-3ff21cc6fba1")
F2_AGGREGATE_PRIMITIVE_RHO = 0.04
NO_PURPOSE_DECLARED = "No purpose declared for this message type."


class TerminalCode(StrEnum):
    """Machine-readable terminal states for orchestrator control flow."""

    A1_NO_ALERT = "a1_no_alert"
    A2_DISMISSED = "a2_dismissed"
    A2_DISMISSED_AFTER_PEER = "a2_dismissed_after_peer"
    A2_REJECTED = "a2_rejected"
    A2_SAR_BEFORE_FEDERATION = "a2_sar_before_federation"
    A2_SYNTHESIS_NO_ARTIFACT = "a2_synthesis_no_artifact"
    F1_AGGREGATION_EMPTY = "f1_aggregation_empty"
    F1_NO_ROUTE_PLAN = "f1_no_route_plan"
    F1_REFUSAL = "f1_refusal"
    F2_AGGREGATE_REFUSED = "f2_aggregate_refused"
    F4_PENDING = "f4_pending"
    F4_MISSING_INPUTS = "f4_missing_inputs"
    F5_HUMAN_REVIEW_REQUIRED = "f5_human_review_required"
    NO_SAR_WARRANTED = "no_sar_warranted"
    ROUTE_PLAN_INVALID = "route_plan_invalid"
    SAR_DRAFT_READY = "sar_draft_ready"


@dataclass
class SessionOrchestratorState:
    """Mutable live-run state attached to one UI session."""

    run_id: str
    mode: str
    principals: OrchestratorPrincipals
    audit: OrchestratorAuditRecorder
    registry: AgentRegistry
    monitor_bank_id: BankId = BankId.BANK_ALPHA
    latest_alert: Alert | None = None
    original_query: Sec314bQuery | None = None
    route_plan: F1RoutePlan | None = None
    routed_requests: list[Sec314bQuery | LocalSiloContributionRequest] = field(
        default_factory=list
    )
    a3_responses: list[Sec314bResponse] = field(default_factory=list)
    aggregate_response: Sec314bResponse | None = None
    sanctions_response: SanctionsCheckResponse | None = None
    sar_contribution: SARContribution | None = None
    graph_pattern_request: GraphPatternRequest | None = None
    graph_pattern_response: GraphPatternResponse | None = None
    pattern_aggregate_provenance: list[PrimitiveAuditRecord] = field(default_factory=list)
    policy_evaluations: list[PolicyEvaluationRecord] = field(default_factory=list)
    sar_assembly_request: SARAssemblyRequest | None = None
    sar_contribution_request: SARContributionRequest | None = None
    sar_draft: SARDraft | None = None
    audit_review_request: AuditReviewRequest | None = None
    audit_review_result: AuditReviewResult | None = None
    dismissal: DismissalRationale | None = None
    terminal_reason: str | None = None
    terminal_code: TerminalCode | None = None
    turn_count: int = 0


class Orchestrator:
    """Single-process P15 orchestrator used by the demo API."""

    def __init__(
        self,
        *,
        principals: OrchestratorPrincipals,
        monitor_bank_id: BankId = BankId.BANK_ALPHA,
    ) -> None:
        self._principals = principals
        self._monitor_bank_id = monitor_bank_id

    def bootstrap(self, *, session_id: UUID, mode: str) -> SessionOrchestratorState:
        run_id = str(session_id)
        audit = OrchestratorAuditRecorder()
        registry = AgentRegistry.build(
            run_id=run_id,
            session_mode=mode,
            principals=self._principals,
            audit=audit,
        )
        audit.emit_orchestrator_event(
            run_id=run_id,
            phase="bootstrap",
            status="ok",
            detail="P15 orchestrator initialized local agent registry.",
        )
        return SessionOrchestratorState(
            run_id=run_id,
            mode=mode,
            principals=self._principals,
            audit=audit,
            registry=registry,
            monitor_bank_id=self._monitor_bank_id,
        )

    def next_turn(self, state: SessionOrchestratorState) -> AgentTurn | None:
        return next_turn(state)

    def run_turn(self, state: SessionOrchestratorState, turn: AgentTurn) -> str:
        state.turn_count += 1
        if turn.kind == "a1_monitor":
            return self._run_a1(state)
        if turn.kind == "a2_alert_triage":
            return self._run_a2_alert(state)
        if turn.kind == "f1_route":
            return self._run_f1_route(state)
        if turn.kind == "f3_sanctions":
            return self._run_f3(state)
        if turn.kind == "a3_silo_response":
            return self._run_a3(state, turn)
        if turn.kind == "f1_aggregate":
            return self._run_f1_aggregate(state)
        if turn.kind == "a2_response_synthesis":
            return self._run_a2_synthesis(state)
        if turn.kind == "f2_graph_analysis":
            return self._run_f2_graph_analysis(state)
        if turn.kind == "f4_sar_draft":
            return self._run_f4_sar_draft(state)
        if turn.kind == "f5_audit_review":
            return self._run_f5_audit_review(state)
        raise ValueError(f"unsupported orchestrator turn: {turn.kind}")

    def _run_a1(self, state: SessionOrchestratorState) -> str:
        bank_id = state.monitor_bank_id
        agent = state.registry.a1_by_bank[bank_id]
        candidate = canonical_signal_candidate()
        result = agent.run(agent.build_input([candidate]))
        emitted = [decision.alert for decision in result.decisions if decision.alert]
        if not emitted:
            state.terminal_reason = "A1 emitted no alert"
            state.terminal_code = TerminalCode.A1_NO_ALERT
            return state.terminal_reason
        # This state machine carries one active alert per session cascade.
        state.latest_alert = Alert.model_validate(
            {
                **emitted[0].model_dump(),
                "created_at": CANONICAL_WINDOW_END,
            }
        )
        return f"A1 emitted alert {state.latest_alert.alert_id}."

    def _run_a2_alert(self, state: SessionOrchestratorState) -> str:
        if state.latest_alert is None:
            raise ValueError("A2 alert turn requires latest_alert")
        bank_id = state.latest_alert.sender_bank_id
        agent = state.registry.a2_by_bank[bank_id]
        correlated = [
            CorrelatedAlertSummary(
                alert_id=_correlated_alert_id(state.latest_alert.alert_id, 1),
                entity_hashes=state.latest_alert.evidence[0].entity_hashes,
                signal_type=state.latest_alert.signal_type.value,
                created_at=state.latest_alert.created_at - timedelta(days=1),
            ),
            CorrelatedAlertSummary(
                alert_id=_correlated_alert_id(state.latest_alert.alert_id, 2),
                entity_hashes=state.latest_alert.evidence[0].entity_hashes,
                signal_type=state.latest_alert.signal_type.value,
                created_at=state.latest_alert.created_at - timedelta(days=2),
            ),
        ]
        result = agent.run(
            agent.build_alert_input(state.latest_alert, correlated_alerts=correlated)
        )
        if result.query is not None:
            state.original_query = self._sign_a2_query(result.query, bank_id=bank_id)
            self._record_policy_evaluation(
                state,
                turn_id="a2_alert_triage",
                message=state.original_query,
            )
            return f"A2 emitted signed Section 314(b) query {state.original_query.query_id}."
        if result.sar_contribution is not None:
            state.sar_contribution = result.sar_contribution
            state.terminal_reason = "A2 emitted SAR contribution before federation."
            state.terminal_code = TerminalCode.A2_SAR_BEFORE_FEDERATION
            return state.terminal_reason
        if result.dismissal is not None:
            state.dismissal = result.dismissal
            state.terminal_reason = "A2 dismissed the alert."
            state.terminal_code = TerminalCode.A2_DISMISSED
            return state.terminal_reason
        state.terminal_reason = result.rejection_reason or "A2 rejected the turn."
        state.terminal_code = TerminalCode.A2_REJECTED
        return state.terminal_reason

    def _run_f1_route(self, state: SessionOrchestratorState) -> str:
        if state.original_query is None:
            raise ValueError("F1 route turn requires original_query")
        result = state.registry.f1.run(
            F1TurnInput(payload=F1InboundQueryInput(query=state.original_query))
        )
        if result.response is not None:
            state.aggregate_response = result.response
            state.terminal_reason = f"F1 refused query: {result.response.refusal_reason}"
            state.terminal_code = TerminalCode.F1_REFUSAL
            return state.terminal_reason
        if result.route_plan is None:
            state.terminal_reason = "F1 produced no route plan."
            state.terminal_code = TerminalCode.F1_NO_ROUTE_PLAN
            return state.terminal_reason
        state.route_plan = result.route_plan
        state.routed_requests = [
            *result.route_plan.peer_requests,
            *([result.route_plan.local_request] if result.route_plan.local_request else []),
        ]
        for request in state.routed_requests:
            self._record_policy_evaluation(
                state,
                turn_id="f1_route",
                message=request,
            )
        if result.route_plan.sanctions_request is not None:
            self._record_policy_evaluation(
                state,
                turn_id="f1_route",
                message=result.route_plan.sanctions_request,
            )
        return f"F1 routed {len(state.routed_requests)} A3 request(s)."

    def _run_f3(self, state: SessionOrchestratorState) -> str:
        if state.graph_pattern_response is None:
            raise ValueError("F3 turn requires graph pattern response from F2")
        request = self._build_canonical_sanctions_request(state)
        self._record_policy_evaluation(
            state,
            turn_id="f3_sanctions",
            message=request,
        )
        state.sanctions_response = state.registry.f3.run(request)
        self._record_policy_evaluation(
            state,
            turn_id="f3_sanctions",
            message=state.sanctions_response,
        )
        return "F3 completed sanctions and PEP screening."

    def _run_a3(self, state: SessionOrchestratorState, turn: AgentTurn) -> str:
        if turn.request is None:
            raise ValueError("A3 turn requires routed request")
        bank_id = turn.bank_id
        if bank_id is None:
            state.terminal_reason = "A3 turn could not resolve a single routed bank."
            state.terminal_code = TerminalCode.ROUTE_PLAN_INVALID
            return state.terminal_reason
        response = state.registry.a3_by_bank[bank_id].run(A3TurnInput(request=turn.request))
        state.a3_responses.append(response)
        self._record_policy_evaluation(
            state,
            turn_id=f"a3_silo_response:{bank_id.value}",
            message=response,
        )
        if response.refusal_reason:
            return f"{bank_id.value}.A3 refused with {response.refusal_reason}."
        return f"{bank_id.value}.A3 returned {len(response.fields)} field(s)."

    def _run_f1_aggregate(self, state: SessionOrchestratorState) -> str:
        if state.original_query is None:
            raise ValueError("F1 aggregation requires original_query")
        result = state.registry.f1.run(
            F1TurnInput(
                payload=F1AggregationInput(
                    original_query=state.original_query,
                    routed_requests=state.routed_requests,
                    responses=state.a3_responses,
                )
            )
        )
        if result.route_plan is not None:
            state.route_plan = result.route_plan
            state.routed_requests = [
                *result.route_plan.peer_requests,
                *([result.route_plan.local_request] if result.route_plan.local_request else []),
            ]
            state.a3_responses = []
            return "F1 negotiated a retry route plan."
        if result.response is None:
            state.terminal_reason = "F1 aggregation produced no response."
            state.terminal_code = TerminalCode.F1_AGGREGATION_EMPTY
            return state.terminal_reason
        state.aggregate_response = result.response
        self._record_policy_evaluation(
            state,
            turn_id="f1_aggregate",
            message=state.aggregate_response,
        )
        return f"F1 aggregated response with {len(result.response.fields)} field(s)."

    def _run_a2_synthesis(self, state: SessionOrchestratorState) -> str:
        if (
            state.latest_alert is None
            or state.original_query is None
            or state.aggregate_response is None
        ):
            raise ValueError("A2 synthesis requires alert, query, and aggregate response")
        bank_id = state.latest_alert.sender_bank_id
        agent = state.registry.a2_by_bank[bank_id]
        result = agent.run(
            agent.build_peer_response_input(
                alert=state.latest_alert,
                original_query=state.original_query,
                response=state.aggregate_response,
            )
        )
        if result.sar_contribution is not None:
            state.sar_contribution = _with_canonical_amount_range(result.sar_contribution)
            return "A2 emitted SAR contribution for canonical F2/F4 assembly."
        if result.dismissal is not None:
            state.dismissal = result.dismissal
            state.terminal_reason = "A2 dismissed after peer synthesis."
            state.terminal_code = TerminalCode.A2_DISMISSED_AFTER_PEER
            return state.terminal_reason
        state.terminal_reason = result.rejection_reason or "A2 synthesis ended without artifact."
        state.terminal_code = TerminalCode.A2_SYNTHESIS_NO_ARTIFACT
        return state.terminal_reason

    def _run_f2_graph_analysis(self, state: SessionOrchestratorState) -> str:
        if state.original_query is None:
            raise ValueError("F2 graph analysis requires original_query")
        try:
            request = self._build_graph_pattern_request(state)
        except GraphAggregateRefused as exc:
            state.terminal_reason = str(exc)
            state.terminal_code = TerminalCode.F2_AGGREGATE_REFUSED
            return state.terminal_reason
        state.graph_pattern_request = request
        self._record_policy_evaluation(
            state,
            turn_id="f2_graph_analysis",
            message=request,
        )
        response = state.registry.f2.run(request)
        state.graph_pattern_response = response
        self._record_policy_evaluation(
            state,
            turn_id="f2_graph_analysis",
            message=response,
        )
        if response.pattern_class == PatternClass.NONE:
            state.terminal_reason = "F2 found no cross-bank pattern warranting SAR assembly."
            state.terminal_code = TerminalCode.NO_SAR_WARRANTED
            return state.terminal_reason
        return (
            f"F2 found {response.pattern_class.value} with "
            f"{response.confidence:.2f} confidence."
        )

    def _run_f4_sar_draft(self, state: SessionOrchestratorState) -> str:
        request = self._build_sar_assembly_request(state)
        state.sar_assembly_request = request
        self._record_policy_evaluation(
            state,
            turn_id="f4_sar_draft",
            message=request,
        )
        result = state.registry.f4.run(request)
        if isinstance(result, SARContributionRequest):
            state.sar_contribution_request = result
            self._record_policy_evaluation(
                state,
                turn_id="f4_sar_draft",
                message=result,
            )
            state.terminal_reason = "F4 requested missing SAR inputs."
            state.terminal_code = TerminalCode.F4_MISSING_INPUTS
            return state.terminal_reason
        state.sar_draft = result
        self._record_policy_evaluation(
            state,
            turn_id="f4_sar_draft",
            message=result,
        )
        return (
            "F4 emitted SAR draft "
            f"{result.sar_id} with priority {result.sar_priority.value}."
        )

    def _run_f5_audit_review(self, state: SessionOrchestratorState) -> str:
        request = build_audit_review_request(
            sender_agent_id="federation.F1",
            policy_records=state.policy_evaluations,
            a3_responses=state.a3_responses,
            primitive_records=state.pattern_aggregate_provenance,
            dismissals=[state.dismissal] if state.dismissal is not None else [],
            related_query_ids=_related_query_ids(state),
        )
        state.audit_review_request = request
        self._record_policy_evaluation(
            state,
            turn_id="f5_audit_review",
            message=request,
        )
        result = state.registry.f5.run(request)
        state.audit_review_result = result
        self._record_policy_evaluation(
            state,
            turn_id="f5_audit_review",
            message=result,
        )
        if result.human_review_required:
            state.terminal_reason = "F5 found audit issues requiring human review."
            state.terminal_code = TerminalCode.F5_HUMAN_REVIEW_REQUIRED
            return state.terminal_reason
        state.terminal_reason = "Canonical demo completed with SAR draft and clean audit."
        state.terminal_code = TerminalCode.SAR_DRAFT_READY
        return state.terminal_reason

    def _sign_a2_query(self, query: Sec314bQuery, *, bank_id: BankId) -> Sec314bQuery:
        principal = self._principals.principals[f"{bank_id.value}.A2"]
        with_boundary = query.model_copy(
            update={
                "expires_at": utc_now() + timedelta(minutes=5),
                "nonce": f"{query.query_id}:a2-f1",
            }
        )
        return sign_message(
            with_boundary,
            private_key=principal.private_key,
            signing_key_id=principal.signing_key_id,
        )

    def _build_graph_pattern_request(
        self,
        state: SessionOrchestratorState,
    ) -> GraphPatternRequest:
        if state.original_query is None:
            raise ValueError("graph pattern request requires original_query")
        window = _query_window(state)
        aggregates = []
        state.pattern_aggregate_provenance = []
        for bank_id, agent in state.registry.a3_by_bank.items():
            requester = RequesterKey(
                requesting_investigator_id=state.original_query.requesting_investigator_id,
                requesting_bank_id=state.original_query.requesting_bank_id,
                responding_bank_id=bank_id,
            )
            result = agent.primitives.pattern_aggregate_for_f2(
                window=window,
                requester=requester,
                candidate_entity_hashes=_graph_candidate_hashes(state),
                rho=F2_AGGREGATE_PRIMITIVE_RHO,
            )
            if result.refusal_reason is not None:
                raise GraphAggregateRefused(
                    f"F2 aggregate refused by {bank_id}: {result.refusal_reason}"
                )
            aggregates.append(result.value)
            state.pattern_aggregate_provenance.extend(
                PrimitiveAuditRecord(bank_id=bank_id, record=record)
                for record in result.records
            )
        return GraphPatternRequest(
            sender_agent_id="federation.F1",
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="federation.F2",
            pattern_aggregates=aggregates,
            window_start=window[0],
            window_end=window[1],
        )

    def _build_sar_assembly_request(
        self,
        state: SessionOrchestratorState,
    ) -> SARAssemblyRequest:
        if state.original_query is None or state.graph_pattern_response is None:
            raise ValueError("SAR assembly requires original_query and graph pattern")
        contributions = _canonical_sar_contributions(state)
        return SARAssemblyRequest(
            sender_agent_id="federation.F1",
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="federation.F4",
            filing_bank_id=state.original_query.requesting_bank_id,
            contributions=contributions,
            graph_pattern=state.graph_pattern_response,
            sanctions=state.sanctions_response,
            policy_evaluations=[record.policy_result for record in state.policy_evaluations],
            related_query_ids=_related_query_ids(state),
        )

    def _build_canonical_sanctions_request(
        self,
        state: SessionOrchestratorState,
    ) -> SanctionsCheckRequest:
        if state.graph_pattern_response is None:
            raise ValueError("canonical F3 screening requires graph pattern response")
        return SanctionsCheckRequest(
            sender_agent_id="federation.F1",
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="federation.F3",
            entity_hashes=_sanctions_hashes_for_graph(state),
            requesting_context=(
                "Canonical S1 hash-only screening before SAR assembly."
            ),
        )

    def _record_policy_evaluation(
        self,
        state: SessionOrchestratorState,
        *,
        turn_id: str,
        message: AgentMessage,
    ) -> None:
        policy_agent_id = _policy_agent_id_for_message(
            message,
            state.registry.f6_by_agent_id.keys(),
        )
        evaluator = state.registry.f6_by_agent_id[policy_agent_id]
        request = PolicyEvaluationRequest(
            sender_agent_id="local-orchestrator",
            sender_role=AgentRole.ORCHESTRATOR,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id=policy_agent_id,
            evaluated_message_type=MessageType(message.message_type),
            evaluated_sender_agent_id=message.sender_agent_id,
            evaluated_sender_role=message.sender_role,
            evaluated_sender_bank_id=message.sender_bank_id,
            content_channel=PolicyContentChannel.STRUCTURED_MESSAGE,
            content_hash=approved_body_hash(message),
            content_summary=(
                f"{message.message_type} from {message.sender_agent_id} to "
                f"{message.recipient_agent_id} in the canonical S1 demo flow."
            ),
            declared_purpose=_declared_purpose(message),
        )
        evaluation = evaluator.evaluate(request, evaluated_message=message)
        state.policy_evaluations.append(
            PolicyEvaluationRecord(
                turn_id=turn_id,
                message_id=message.message_id,
                evaluated_message_type=MessageType(message.message_type),
                evaluated_sender_agent_id=message.sender_agent_id,
                evaluated_recipient_agent_id=message.recipient_agent_id,
                policy_result=evaluation.result,
                audit_events=evaluation.audit_events,
            )
        )


def _correlated_alert_id(source_alert_id: UUID, ordinal: int) -> UUID:
    """Derive stable synthetic correlation ids from the active alert id."""
    return uuid5(
        _CORRELATED_ALERT_NAMESPACE,
        f"federated_silo_agent:p15:correlated:{source_alert_id}:{ordinal}",
    )


def _query_window(state: SessionOrchestratorState) -> tuple[date, date]:
    if state.original_query is not None:
        payload = state.original_query.query_payload
        window_start = getattr(payload, "window_start", None)
        window_end = getattr(payload, "window_end", None)
        if window_start is not None and window_end is not None:
            return window_start, window_end
    if state.latest_alert is None:
        raise ValueError("query window requires original_query or latest_alert")
    end = state.latest_alert.created_at.date()
    return end - timedelta(days=30), end


def _graph_candidate_hashes(state: SessionOrchestratorState) -> list[str]:
    """Return approved hash tokens that F2 may carry through to output."""
    hashes: set[str] = set()
    if state.original_query is not None:
        payload = state.original_query.query_payload
        hashes.update(getattr(payload, "name_hashes", []))
        hashes.update(getattr(payload, "counterparty_hashes", []))
    if state.sar_contribution is not None:
        for item in state.sar_contribution.contributed_evidence:
            hashes.update(item.entity_hashes)
            hashes.update(item.counterparty_hashes)

    if (
        state.latest_alert is not None
        and state.latest_alert.transaction_id == CANONICAL_ALERT_TRANSACTION_ID
    ):
        # The canonical S1 seed represents an investigator-approved expansion
        # from one local alert token to the known hash-only ring candidate set.
        # F2 still receives only candidate tokens plus DP aggregates, never raw
        # customer names, accounts, or transaction rows.
        hashes.update(S1_ENTITY_HASHES)
    return sorted(hashes)


def _sanctions_hashes_for_graph(state: SessionOrchestratorState) -> list[str]:
    if state.graph_pattern_response is None:
        raise ValueError("sanctions screening requires graph pattern response")
    hashes = state.graph_pattern_response.suspect_entity_hashes
    if hashes:
        return list(hashes)
    return _graph_candidate_hashes(state)


def _canonical_sar_contributions(
    state: SessionOrchestratorState,
) -> list[SARContribution]:
    """Build P16 seeded SAR contributions for F4's mandatory fields.

    P16 proves terminal composition. It does not introduce a new peer-A2
    contribution request contract, so peer amount ranges come from deterministic
    S1 seed facts while hash evidence still flows through typed contribution
    models. A future peer-A2 collection protocol should replace this helper.
    """
    if state.original_query is None:
        raise ValueError("canonical SAR contributions require original_query")
    related_query_ids = _related_query_ids(state)
    contributions: list[SARContribution] = []
    for seed in S1_CONTRIBUTIONS:
        evidence_summary = (
            f"{seed.bank_id.value} hash-only evidence supports canonical SAR drafting."
        )
        if (
            state.sar_contribution is not None
            and seed.bank_id == state.sar_contribution.contributing_bank_id
        ):
            evidence = state.sar_contribution.contributed_evidence
        else:
            evidence = [
                EvidenceItem(
                    summary=evidence_summary,
                    entity_hashes=list(seed.entity_hashes),
                )
            ]
        contributions.append(
            SARContribution(
                sender_agent_id=f"{seed.bank_id.value}.A2",
                sender_role=AgentRole.A2,
                sender_bank_id=seed.bank_id,
                recipient_agent_id="federation.F4",
                contributing_bank_id=seed.bank_id,
                contributing_investigator_id=seed.investigator_id,
                contributed_evidence=evidence,
                suspicious_amount_range=seed.suspicious_amount_range,
                local_rationale=seed.rationale,
                related_query_ids=related_query_ids,
            )
        )
    return contributions


def _with_canonical_amount_range(contribution: SARContribution) -> SARContribution:
    for seed in S1_CONTRIBUTIONS:
        if seed.bank_id == contribution.contributing_bank_id:
            return SARContribution.model_validate(
                {
                    **contribution.model_dump(),
                    "suspicious_amount_range": seed.suspicious_amount_range,
                }
            )
    return contribution


def _related_query_ids(state: SessionOrchestratorState) -> list[UUID]:
    if state.original_query is None:
        return []
    return [state.original_query.query_id]


class GraphAggregateRefused(RuntimeError):
    """Raised when a silo refuses the F2 aggregate primitive."""


def _policy_agent_id_for_message(
    message: AgentMessage,
    f6_agent_ids: Container[str],
) -> str:
    recipient_domain = message.recipient_agent_id.split(".", maxsplit=1)[0]
    policy_agent_id = f"{recipient_domain}.F6"
    if policy_agent_id in f6_agent_ids:
        return policy_agent_id
    return "federation.F6"


def _declared_purpose(message: AgentMessage) -> str:
    purpose = getattr(message, "purpose_declaration", None)
    if purpose is not None:
        return purpose.suspicion_rationale
    return NO_PURPOSE_DECLARED
