"""Pydantic state models for the A2 investigator agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from shared.enums import QueryShape, TypologyCode
from shared.messages import (
    Alert,
    CrossBankHashToken,
    DismissalRationale,
    SARContribution,
    Sec314bQuery,
    Sec314bResponse,
    reject_demo_customer_names,
)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ShortReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
MediumReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class A2Model(BaseModel):
    """Strict Pydantic base for A2 state objects."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class CorrelatedAlertSummary(A2Model):
    """Safe alert-history summary available to A2 without raw DB access."""

    alert_id: UUID
    entity_hashes: list[CrossBankHashToken] = Field(min_length=1)
    signal_type: NonEmptyStr
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)


class A2AlertInput(A2Model):
    """A2 turn that starts from a local A1 alert."""

    turn_type: Literal["alert"] = "alert"
    alert: Alert
    investigator_id: NonEmptyStr
    correlated_alerts: list[CorrelatedAlertSummary] = Field(default_factory=list)


class A2PeerResponseInput(A2Model):
    """A2 turn that starts from an aggregated peer response."""

    turn_type: Literal["peer_response"] = "peer_response"
    alert: Alert
    original_query: Sec314bQuery
    response: Sec314bResponse
    investigator_id: NonEmptyStr


class A2InboundQueryInput(A2Model):
    """A2 turn representing an incorrectly routed peer query."""

    turn_type: Literal["inbound_query"] = "inbound_query"
    query: Sec314bQuery


A2InputPayload: TypeAlias = Annotated[
    A2AlertInput | A2PeerResponseInput | A2InboundQueryInput,
    Field(discriminator="turn_type"),
]


class A2TurnInput(A2Model):
    """One A2 state-machine turn."""

    payload: A2InputPayload


class TriageDecision(A2Model):
    """LLM triage result for a local alert."""

    action: Literal["dismiss", "escalate_cross_bank"]
    reason: ShortReason


class QueryDraft(A2Model):
    """LLM draft for a cross-bank query body."""

    query_shape: QueryShape
    typology_code: TypologyCode
    suspicion_rationale: MediumReason
    name_hashes: list[CrossBankHashToken] = Field(default_factory=list, max_length=100)
    counterparty_hashes: list[CrossBankHashToken] = Field(
        default_factory=list,
        max_length=100,
    )
    metrics: list[NonEmptyStr] = Field(default_factory=lambda: ["alert_count"])
    requested_rho_per_primitive: float = Field(default=0.02, ge=0.0, le=1.0)

    @field_validator("suspicion_rationale")
    @classmethod
    def suspicion_rationale_must_not_contain_customer_names(cls, value: str) -> str:
        """Reject draft narratives that leak demo customer-name strings.

        The downstream `PurposeDeclaration.suspicion_rationale` also rejects
        these strings, but catching the leak HERE means a hallucinating LLM
        is rejected at the draft boundary with retry (via the base class's
        `_call_structured` ValidationError handler) rather than crashing later
        when the `Sec314bQuery` envelope is assembled. Same regex either way.
        """
        return reject_demo_customer_names(value, "suspicion_rationale")

    @model_validator(mode="after")
    def hash_fields_must_match_shape(self) -> QueryDraft:
        """Enforce that the populated hash field matches the query shape.

        Error messages are deliberately descriptive — LLM-generated drafts
        are the primary source of validation failures here, and the message
        is what feeds into `_call_state_with_constraint`'s retry prompt. The
        retry prompt needs to tell the model exactly what was wrong (which
        field was missing, which was unexpectedly populated, and a short
        sample of any offending hashes) so the model can correct course.
        """
        if self.query_shape == QueryShape.COUNTERPARTY_LINKAGE:
            if not self.counterparty_hashes:
                raise ValueError(
                    "counterparty_linkage requires non-empty counterparty_hashes "
                    "(got 0 entries); populate the counterparty_hashes field from "
                    "the alert's evidence counterparty_hashes"
                )
            if self.name_hashes:
                preview = list(self.name_hashes)[:3]
                raise ValueError(
                    "counterparty_linkage must not include name_hashes "
                    f"(got {len(self.name_hashes)} entries, e.g. {preview}); "
                    "move the tokens into counterparty_hashes if they are real "
                    "counterparty values, or remove them otherwise"
                )
            return self

        if not self.name_hashes:
            raise ValueError(
                f"{self.query_shape.value} requires non-empty name_hashes "
                "(got 0 entries); populate name_hashes from the alert's "
                "evidence entity_hashes"
            )
        if self.counterparty_hashes:
            preview = list(self.counterparty_hashes)[:3]
            raise ValueError(
                f"{self.query_shape.value} must not include counterparty_hashes "
                f"(got {len(self.counterparty_hashes)} entries, e.g. {preview}); "
                "use query_shape=counterparty_linkage if you need to query by "
                "counterparty tokens, otherwise remove them"
            )
        return self


class SynthesisDecision(A2Model):
    """LLM synthesis result for an aggregated peer response."""

    action: Literal["sar_contribution", "dismiss"]
    rationale: MediumReason


class A2TurnResult(A2Model):
    """Outbound result from one A2 state-machine turn."""

    action: Literal["query", "sar_contribution", "dismiss", "rejected"]
    query: Sec314bQuery | None = None
    sar_contribution: SARContribution | None = None
    dismissal: DismissalRationale | None = None
    rejection_reason: ShortReason | None = None
    bypass_rule_id: Literal["A2-B1", "A2-B2"] | None = None

    @model_validator(mode="after")
    def action_must_match_payload(self) -> A2TurnResult:
        payload_count = sum(
            item is not None
            for item in (
                self.query,
                self.sar_contribution,
                self.dismissal,
                self.rejection_reason,
            )
        )
        if payload_count != 1:
            raise ValueError("A2 result must carry exactly one output payload")
        if self.action == "query" and self.query is None:
            raise ValueError("query action requires query")
        if self.action == "sar_contribution" and self.sar_contribution is None:
            raise ValueError("sar_contribution action requires sar_contribution")
        if self.action == "dismiss" and self.dismissal is None:
            raise ValueError("dismiss action requires dismissal")
        if self.action == "rejected" and self.rejection_reason is None:
            raise ValueError("rejected action requires rejection_reason")
        return self
