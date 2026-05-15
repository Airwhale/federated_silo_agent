"""Deterministic turn scheduling for the local P15 orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from shared.enums import BankId
from shared.messages import LocalSiloContributionRequest, Sec314bQuery


TurnKind = Literal[
    "a1_monitor",
    "a2_alert_triage",
    "f1_route",
    "f3_sanctions",
    "a3_silo_response",
    "f1_aggregate",
    "a2_response_synthesis",
]


@dataclass(frozen=True)
class AgentTurn:
    """One visible orchestrator turn."""

    kind: TurnKind
    agent_id: str
    bank_id: BankId | None = None
    request: Sec314bQuery | LocalSiloContributionRequest | None = None


def next_turn(state: object) -> AgentTurn | None:
    """Return the next canonical turn for the session state."""
    if getattr(state, "terminal_reason", None) is not None:
        return None
    if getattr(state, "latest_alert", None) is None:
        return AgentTurn(
            kind="a1_monitor",
            agent_id="bank_alpha.A1",
            bank_id=BankId.BANK_ALPHA,
        )
    if getattr(state, "original_query", None) is None:
        return AgentTurn(
            kind="a2_alert_triage",
            agent_id="bank_alpha.A2",
            bank_id=BankId.BANK_ALPHA,
        )
    if getattr(state, "route_plan", None) is None:
        return AgentTurn(kind="f1_route", agent_id="federation.F1")

    route_plan = state.route_plan
    if route_plan.sanctions_request is not None and state.sanctions_response is None:
        return AgentTurn(kind="f3_sanctions", agent_id="federation.F3")

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
        return AgentTurn(
            kind="a2_response_synthesis",
            agent_id="bank_alpha.A2",
            bank_id=BankId.BANK_ALPHA,
        )
    return None


def _routed_bank(request: Sec314bQuery | LocalSiloContributionRequest) -> BankId:
    if isinstance(request, Sec314bQuery):
        if not request.target_bank_ids:
            raise ValueError("routed Sec314bQuery is missing target_bank_ids")
        return request.target_bank_ids[0]
    return request.responding_bank_id
