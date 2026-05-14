"""Pydantic state models for the F1 federation coordinator."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from shared.enums import BankId
from shared.messages import (
    LocalSiloContributionRequest,
    SanctionsCheckRequest,
    Sec314bQuery,
    Sec314bResponse,
)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class F1Model(BaseModel):
    """Strict Pydantic base for F1 state objects."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


F1RoutedRequest: TypeAlias = Annotated[
    Sec314bQuery | LocalSiloContributionRequest,
    Field(discriminator="message_type"),
]


class F1InboundQueryInput(F1Model):
    """One signed A2 query awaiting F1 route planning."""

    kind: Literal["inbound_query"] = "inbound_query"
    query: Sec314bQuery


class F1AggregationInput(F1Model):
    """A3 responses to aggregate for one original A2 query."""

    kind: Literal["aggregate_responses"] = "aggregate_responses"
    original_query: Sec314bQuery
    routed_requests: list[F1RoutedRequest] = Field(default_factory=list)
    responses: list[Sec314bResponse] = Field(default_factory=list)


F1InputPayload: TypeAlias = Annotated[
    F1InboundQueryInput | F1AggregationInput,
    Field(discriminator="kind"),
]


class F1TurnInput(F1Model):
    """One F1 state-machine turn."""

    payload: F1InputPayload


class F1NegotiationNote(F1Model):
    """Bounded retry or refusal decision for one silo response."""

    responding_bank_id: BankId
    refusal_reason: NonEmptyStr
    decision: Literal[
        "retry_with_lower_rho",
        "retry_with_valid_rho",
        "retry_with_supported_metric",
        "partial_result",
        "terminal_refusal",
        "human_review",
    ]
    detail: NonEmptyStr


class F1RoutePlan(F1Model):
    """Signed outbound work items produced by F1."""

    peer_requests: list[Sec314bQuery] = Field(default_factory=list)
    local_request: LocalSiloContributionRequest | None = None
    sanctions_request: SanctionsCheckRequest | None = None
    negotiation_notes: list[F1NegotiationNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def route_plan_must_have_work(self) -> F1RoutePlan:
        if not self.peer_requests and self.local_request is None and self.sanctions_request is None:
            raise ValueError("route plan must contain at least one outbound request")
        return self


class F1TurnResult(F1Model):
    """Result of one F1 coordinator turn."""

    action: Literal["route_plan", "retry_plan", "aggregate", "refusal"]
    route_plan: F1RoutePlan | None = None
    response: Sec314bResponse | None = None

    @model_validator(mode="after")
    def action_payload_must_match(self) -> F1TurnResult:
        if self.action in {"route_plan", "retry_plan"} and self.route_plan is None:
            raise ValueError("route actions require route_plan")
        if self.action in {"aggregate", "refusal"} and self.response is None:
            raise ValueError("response actions require response")
        return self
