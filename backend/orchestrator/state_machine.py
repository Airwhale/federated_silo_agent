"""Deterministic turn scheduling for the local P15 orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from shared.enums import BankId
from shared.messages import LocalSiloContributionRequest, Sec314bQuery

if TYPE_CHECKING:
    from backend.orchestrator.runtime import SessionOrchestratorState


TurnKind = Literal[
    "a1_monitor",
    "a2_alert_triage",
    "f1_route",
    "f3_sanctions",
    "a3_silo_response",
    "f1_aggregate",
    "a2_response_synthesis",
    "f2_graph_analysis",
    "f4_sar_draft",
    "f5_audit_review",
]


@dataclass(frozen=True)
class AgentTurn:
    """One visible orchestrator turn."""

    kind: TurnKind
    agent_id: str
    bank_id: BankId | None = None
    request: Sec314bQuery | LocalSiloContributionRequest | None = None


def next_turn(state: SessionOrchestratorState) -> AgentTurn | None:
    """Return the next canonical turn for the session state."""
    if state.terminal_reason is not None:
        return None
    if state.latest_alert is None:
        monitor_bank_id = state.monitor_bank_id
        return AgentTurn(
            kind="a1_monitor",
            agent_id=f"{monitor_bank_id.value}.A1",
            bank_id=monitor_bank_id,
        )
    if state.original_query is None:
        monitor_bank_id = state.monitor_bank_id
        return AgentTurn(
            kind="a2_alert_triage",
            agent_id=f"{monitor_bank_id.value}.A2",
            bank_id=monitor_bank_id,
        )
    if state.route_plan is None:
        return AgentTurn(kind="f1_route", agent_id="federation.F1")

    routed_requests = state.routed_requests
    if len(state.a3_responses) < len(routed_requests):
        request = routed_requests[len(state.a3_responses)]
        return AgentTurn(
            kind="a3_silo_response",
            agent_id=request.recipient_agent_id,
            bank_id=_routed_bank(request),
            request=request,
        )

    if state.aggregate_response is None:
        return AgentTurn(kind="f1_aggregate", agent_id="federation.F1")
    if state.sar_contribution is None and state.dismissal is None:
        monitor_bank_id = state.monitor_bank_id
        return AgentTurn(
            kind="a2_response_synthesis",
            agent_id=f"{monitor_bank_id.value}.A2",
            bank_id=monitor_bank_id,
        )
    if state.sar_contribution is not None and state.graph_pattern_response is None:
        return AgentTurn(kind="f2_graph_analysis", agent_id="federation.F2")
    if state.graph_pattern_response is not None and state.sanctions_response is None:
        return AgentTurn(kind="f3_sanctions", agent_id="federation.F3")
    if (
        state.graph_pattern_response is not None
        and state.sar_draft is None
        and state.sar_contribution_request is None
    ):
        return AgentTurn(kind="f4_sar_draft", agent_id="federation.F4")
    if state.sar_draft is not None and state.audit_review_result is None:
        return AgentTurn(kind="f5_audit_review", agent_id="federation.F5")
    return None


def _routed_bank(request: Sec314bQuery | LocalSiloContributionRequest) -> BankId | None:
    if isinstance(request, Sec314bQuery):
        if not request.target_bank_ids:
            return None
        if len(request.target_bank_ids) != 1:
            return None
        return request.target_bank_ids[0]
    return request.responding_bank_id
