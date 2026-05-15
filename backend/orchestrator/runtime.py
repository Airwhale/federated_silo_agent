"""Local live orchestrator for the P15 control API adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from backend.agents.a1_monitoring import synthetic_velocity_candidate
from backend.agents.a2_states import CorrelatedAlertSummary
from backend.agents.a3_states import A3TurnInput
from backend.agents.f1_states import (
    F1AggregationInput,
    F1InboundQueryInput,
    F1RoutePlan,
    F1TurnInput,
)
from backend.orchestrator.agents import AgentRegistry, OrchestratorPrincipals
from backend.orchestrator.audit import OrchestratorAuditRecorder
from backend.orchestrator.state_machine import AgentTurn, next_turn
from backend.security import sign_message
from shared.enums import BankId
from shared.messages import (
    Alert,
    DismissalRationale,
    LocalSiloContributionRequest,
    SARContribution,
    SanctionsCheckResponse,
    Sec314bQuery,
    Sec314bResponse,
    utc_now,
)


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
    F4_PENDING = "f4_pending"


@dataclass
class SessionOrchestratorState:
    """Mutable live-run state attached to one UI session."""

    run_id: str
    mode: str
    principals: OrchestratorPrincipals
    audit: OrchestratorAuditRecorder
    registry: AgentRegistry
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
    dismissal: DismissalRationale | None = None
    terminal_reason: str | None = None
    terminal_code: TerminalCode | None = None
    turn_count: int = 0


class Orchestrator:
    """Single-process P15 orchestrator used by the demo API."""

    def __init__(self, *, principals: OrchestratorPrincipals) -> None:
        self._principals = principals

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
        raise ValueError(f"unsupported orchestrator turn: {turn.kind}")

    def _run_a1(self, state: SessionOrchestratorState) -> str:
        bank_id = BankId.BANK_ALPHA
        agent = state.registry.a1_by_bank[bank_id]
        candidate = synthetic_velocity_candidate()
        result = agent.run(agent.build_input([candidate]))
        emitted = [decision.alert for decision in result.decisions if decision.alert]
        if not emitted:
            state.terminal_reason = "A1 emitted no alert"
            state.terminal_code = TerminalCode.A1_NO_ALERT
            return state.terminal_reason
        # This state machine carries one active alert per session cascade.
        state.latest_alert = emitted[0]
        return f"A1 emitted alert {state.latest_alert.alert_id}."

    def _run_a2_alert(self, state: SessionOrchestratorState) -> str:
        if state.latest_alert is None:
            raise ValueError("A2 alert turn requires latest_alert")
        bank_id = state.latest_alert.sender_bank_id
        agent = state.registry.a2_by_bank[bank_id]
        correlated = [
            CorrelatedAlertSummary(
                alert_id=uuid4(),
                entity_hashes=state.latest_alert.evidence[0].entity_hashes,
                signal_type=state.latest_alert.signal_type.value,
                created_at=state.latest_alert.created_at - timedelta(days=1),
            ),
            CorrelatedAlertSummary(
                alert_id=uuid4(),
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
        return f"F1 routed {len(state.routed_requests)} A3 request(s)."

    def _run_f3(self, state: SessionOrchestratorState) -> str:
        if state.route_plan is None or state.route_plan.sanctions_request is None:
            raise ValueError("F3 turn requires sanctions_request")
        state.sanctions_response = state.registry.f3.run(state.route_plan.sanctions_request)
        return "F3 completed sanctions and PEP screening."

    def _run_a3(self, state: SessionOrchestratorState, turn: AgentTurn) -> str:
        if turn.request is None:
            raise ValueError("A3 turn requires routed request")
        bank_id = turn.bank_id
        if bank_id is None:
            raise ValueError("A3 turn requires bank_id")
        response = state.registry.a3_by_bank[bank_id].run(A3TurnInput(request=turn.request))
        state.a3_responses.append(response)
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
            state.sar_contribution = result.sar_contribution
            state.terminal_reason = "F4 pending after A2 SAR contribution."
            state.terminal_code = TerminalCode.F4_PENDING
            return state.terminal_reason
        if result.dismissal is not None:
            state.dismissal = result.dismissal
            state.terminal_reason = "A2 dismissed after peer synthesis."
            state.terminal_code = TerminalCode.A2_DISMISSED_AFTER_PEER
            return state.terminal_reason
        state.terminal_reason = result.rejection_reason or "A2 synthesis ended without artifact."
        state.terminal_code = TerminalCode.A2_SYNTHESIS_NO_ARTIFACT
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
