"""Pydantic boundary models for cross-agent messages."""

from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime
from typing import Annotated, Literal, TypeAlias
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from shared.enums import (
    AgentRole,
    AuditEventKind,
    BankId,
    MessageType,
    PatternClass,
    PrivacyUnit,
    QueryShape,
    ResponseValueKind,
    RouteKind,
    SARPriority,
    SignalType,
    TypologyCode,
)


NonEmptyStr: TypeAlias = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
ShortText: TypeAlias = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
MediumText: TypeAlias = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
OpaqueHashToken: TypeAlias = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
]
# Demo cross-bank linkage tokens are truncated SHA-256 hex strings emitted by
# the synthetic data builders. Full local SHA-256 identifiers use Sha256Hex.
CrossBankHashToken: TypeAlias = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=16,
        max_length=16,
        pattern=r"^[a-f0-9]{16}$",
    ),
]
# Backwards-compatible broad hash alias. Prefer CrossBankHashToken or
# Sha256Hex at new boundaries when the expected shape is known.
HashString: TypeAlias = OpaqueHashToken
Sha256Hex: TypeAlias = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    ),
]

# Defense-in-depth regex against accidental leakage of customer-identifying
# strings into cross-bank-bound text fields. This list mirrors the planted
# shell-entity cover-business names from data/scripts/plant_scenarios.py
# (S1, S2, S3) plus the generic placeholder names used in tests / docs.
#
# Production deployments would replace this with a NER model or a per-bank
# customer-name dictionary loaded from the bank's own KYC tables; this regex
# is a demo-grade defensive check, not the primary privacy mechanism. The
# primary mechanisms are AML-adapter redaction, schema validation, and the
# stats-primitives layer's provenance enforcement.
_DEMO_CUSTOMER_NAME_RE = re.compile(
    r"\b(?:"
    # Generic placeholder names used in tests and example narratives
    r"Jane Doe|John Doe|Alice Smith|Bob Jones"
    # S1 ring — 5 shell entities across all three banks (S1-D is the PEP)
    r"|Acme Holdings LLC|Acme Holdings"
    r"|Beacon Logistics Inc|Beacon Logistics"
    r"|Citadel Trading Co|Citadel Trading"
    r"|Delta Imports Ltd|Delta Imports"
    r"|Eagle Consulting Group|Eagle Consulting"
    # S2 ring — 3 entities, Alpha + Beta only
    r"|Foxtrot Wholesale"
    r"|Gulf Stream Trading"
    r"|Horizon Ventures"
    # S3 layering chain — 4 entities, Alpha -> Beta -> Gamma -> Alpha
    r"|Iridium Capital Partners|Iridium Capital"
    r"|Juniper Asset Mgmt|Juniper Asset Management"
    r"|Kestrel Holdings"
    r"|Lattice Investments"
    r")\b",
    re.IGNORECASE,
)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def reject_demo_customer_names(value: str, field_name: str) -> str:
    """Public helper: raise if `value` contains a known demo customer name.

    Defense-in-depth check shared across boundary models (shared/messages.py)
    and agent-local draft models (e.g. backend/agents/a2_states.QueryDraft).
    Agents that draft user-visible text fields should pin this validator on
    the field so the violation is caught at the LLM-output boundary with
    retry, not later when the message envelope is constructed.
    """
    if _DEMO_CUSTOMER_NAME_RE.search(value):
        raise ValueError(f"{field_name} must not contain customer names")
    return value


# Backwards-compat alias for internal callers in this module.
_reject_demo_customer_names = reject_demo_customer_names


def _validate_window(start: date, end: date) -> None:
    if start > end:
        raise ValueError("window_start must be before or equal to window_end")


class StrictModel(BaseModel):
    """Base model for strict boundary validation."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class Message(StrictModel):
    """Common envelope for cross-agent messages."""

    message_id: UUID = Field(default_factory=uuid4)
    sender_agent_id: NonEmptyStr
    sender_role: AgentRole
    sender_bank_id: BankId
    recipient_agent_id: NonEmptyStr
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    nonce: NonEmptyStr | None = None
    body_hash: Sha256Hex | None = None
    signature: NonEmptyStr | None = None
    signing_key_id: NonEmptyStr | None = None

    @field_validator("created_at", "expires_at")
    @classmethod
    def timestamps_must_be_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _normalize_utc(value)

    @model_validator(mode="after")
    def expires_after_created(self) -> Message:
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        return self


class EvidenceItem(StrictModel):
    """Hash-only evidence summary that can cross bank boundaries."""

    evidence_id: UUID = Field(default_factory=uuid4)
    summary: ShortText
    entity_hashes: list[CrossBankHashToken] = Field(default_factory=list, max_length=100)
    account_hashes: list[OpaqueHashToken] = Field(default_factory=list, max_length=100)
    counterparty_hashes: list[CrossBankHashToken] = Field(
        default_factory=list,
        max_length=100,
    )
    transaction_hashes: list[OpaqueHashToken] = Field(
        default_factory=list,
        max_length=100,
    )

    @field_validator("summary")
    @classmethod
    def summary_must_not_contain_customer_names(cls, value: str) -> str:
        return _reject_demo_customer_names(value, "summary")


class Alert(Message):
    """A1 alert delivered to a local A2 investigator."""

    message_type: Literal["alert"] = MessageType.ALERT.value
    alert_id: UUID = Field(default_factory=uuid4)
    transaction_id: NonEmptyStr
    account_id: NonEmptyStr
    signal_type: SignalType
    severity: float = Field(ge=0.0, le=1.0)
    rationale: ShortText
    evidence: list[EvidenceItem] = Field(default_factory=list)

    @field_validator("rationale")
    @classmethod
    def rationale_must_not_contain_customer_names(cls, value: str) -> str:
        return _reject_demo_customer_names(value, "rationale")


class PurposeDeclaration(StrictModel):
    """Structured USA PATRIOT Act Section 314(b) purpose declaration."""

    authority: Literal["USA_PATRIOT_314b"] = "USA_PATRIOT_314b"
    typology_code: TypologyCode
    suspicion_rationale: MediumText
    supporting_alert_ids: list[UUID] = Field(default_factory=list)

    @field_validator("suspicion_rationale")
    @classmethod
    def suspicion_rationale_must_not_contain_customer_names(cls, value: str) -> str:
        return _reject_demo_customer_names(value, "suspicion_rationale")


class EntityPresencePayload(StrictModel):
    """Query for whether hashed entities have relevant local signals."""

    query_shape: Literal["entity_presence"] = QueryShape.ENTITY_PRESENCE.value
    name_hashes: list[CrossBankHashToken] = Field(min_length=1, max_length=100)
    window_start: date | None = None
    window_end: date | None = None

    @model_validator(mode="after")
    def validate_optional_window(self) -> EntityPresencePayload:
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("window_start and window_end must be provided together")
        if self.window_start is not None and self.window_end is not None:
            _validate_window(self.window_start, self.window_end)
        return self


class AggregateActivityPayload(StrictModel):
    """Query for DP-protected aggregate activity about hashed entities."""

    query_shape: Literal["aggregate_activity"] = QueryShape.AGGREGATE_ACTIVITY.value
    name_hashes: list[CrossBankHashToken] = Field(min_length=1, max_length=100)
    window_start: date
    window_end: date
    metrics: list[NonEmptyStr] = Field(default_factory=lambda: ["alert_count"])

    @model_validator(mode="after")
    def validate_window(self) -> AggregateActivityPayload:
        _validate_window(self.window_start, self.window_end)
        return self


class CounterpartyLinkagePayload(StrictModel):
    """Query for counterparty linkage around cross-bank counterparty tokens."""

    query_shape: Literal["counterparty_linkage"] = QueryShape.COUNTERPARTY_LINKAGE.value
    counterparty_hashes: list[CrossBankHashToken] = Field(min_length=1, max_length=100)
    window_start: date
    window_end: date
    max_hops: int = Field(default=1, ge=1, le=2)

    @model_validator(mode="after")
    def validate_window(self) -> CounterpartyLinkagePayload:
        _validate_window(self.window_start, self.window_end)
        return self


QueryPayload: TypeAlias = Annotated[
    EntityPresencePayload | AggregateActivityPayload | CounterpartyLinkagePayload,
    Field(discriminator="query_shape"),
]


class RouteApproval(StrictModel):
    """F1 approval binding one approved query body to one A3 route."""

    approval_id: UUID = Field(default_factory=uuid4)
    query_id: UUID
    route_kind: RouteKind
    approved_query_body_hash: Sha256Hex
    requesting_bank_id: BankId
    responding_bank_id: BankId
    approved_by_agent_id: NonEmptyStr
    approved_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    signature: NonEmptyStr | None = None
    signing_key_id: NonEmptyStr | None = None

    @field_validator("approved_at", "expires_at")
    @classmethod
    def timestamps_must_be_utc(cls, value: datetime) -> datetime:
        return _normalize_utc(value)

    @model_validator(mode="after")
    def validate_route_shape(self) -> RouteApproval:
        if self.requesting_bank_id == BankId.FEDERATION:
            raise ValueError("requesting_bank_id must be a bank")
        if self.responding_bank_id == BankId.FEDERATION:
            raise ValueError("responding_bank_id must be a bank")
        if self.expires_at <= self.approved_at:
            raise ValueError("expires_at must be after approved_at")
        if (
            self.route_kind == RouteKind.PEER_314B
            and self.requesting_bank_id == self.responding_bank_id
        ):
            raise ValueError("peer_314b route cannot target the requesting bank")
        if (
            self.route_kind == RouteKind.LOCAL_CONTRIBUTION
            and self.requesting_bank_id != self.responding_bank_id
        ):
            raise ValueError(
                "local_contribution route must target the requesting bank"
            )
        return self


class Sec314bQuery(Message):
    """A Section 314(b) query routed from A2 to peer-bank A3s via F1."""

    message_type: Literal["sec314b_query"] = MessageType.SEC314B_QUERY.value
    query_id: UUID = Field(default_factory=uuid4)
    requesting_investigator_id: NonEmptyStr
    requesting_bank_id: BankId
    target_bank_ids: list[BankId] = Field(default_factory=list)
    query_shape: QueryShape
    query_payload: QueryPayload
    purpose_declaration: PurposeDeclaration
    requested_rho_per_primitive: NonNegativeFloat = 0.0
    route_approval: RouteApproval | None = None

    @model_validator(mode="after")
    def payload_shape_must_match_header(self) -> Sec314bQuery:
        payload_shape = QueryShape(self.query_payload.query_shape)
        if payload_shape != self.query_shape:
            raise ValueError("query_shape must match query_payload.query_shape")
        if self.requesting_bank_id == BankId.FEDERATION:
            raise ValueError("requesting_bank_id must be a bank")
        if not self.target_bank_ids:
            self.target_bank_ids = [
                bank_id
                for bank_id in (BankId.BANK_ALPHA, BankId.BANK_BETA, BankId.BANK_GAMMA)
                if bank_id != self.requesting_bank_id
            ]
        if BankId.FEDERATION in self.target_bank_ids:
            raise ValueError("target_bank_ids must contain only peer banks")
        if self.requesting_bank_id in self.target_bank_ids:
            raise ValueError("target_bank_ids must not include the requesting bank")
        if self.route_approval is not None:
            if self.route_approval.query_id != self.query_id:
                raise ValueError("route_approval.query_id must match query_id")
            if self.route_approval.route_kind != RouteKind.PEER_314B:
                raise ValueError("Sec314bQuery route_approval must be peer_314b")
            if self.route_approval.requesting_bank_id != self.requesting_bank_id:
                raise ValueError(
                    "route_approval.requesting_bank_id must match requesting_bank_id"
                )
            if self.route_approval.responding_bank_id not in self.target_bank_ids:
                raise ValueError(
                    "route_approval.responding_bank_id must be in target_bank_ids"
                )
        return self


class LocalSiloContributionRequest(Message):
    """Same-bank A3 request for the requester's own statistical intermediary."""

    message_type: Literal["local_silo_contribution_request"] = (
        MessageType.LOCAL_SILO_CONTRIBUTION_REQUEST.value
    )
    source_query_id: UUID
    requesting_investigator_id: NonEmptyStr
    requesting_bank_id: BankId
    responding_bank_id: BankId
    query_shape: QueryShape
    query_payload: QueryPayload
    purpose_declaration: PurposeDeclaration
    requested_rho_per_primitive: NonNegativeFloat = 0.0
    route_approval: RouteApproval

    @model_validator(mode="after")
    def validate_local_route(self) -> LocalSiloContributionRequest:
        payload_shape = QueryShape(self.query_payload.query_shape)
        if payload_shape != self.query_shape:
            raise ValueError("query_shape must match query_payload.query_shape")
        if self.requesting_bank_id == BankId.FEDERATION:
            raise ValueError("requesting_bank_id must be a bank")
        if self.responding_bank_id != self.requesting_bank_id:
            raise ValueError("local contribution must target the requesting bank")
        if self.route_approval.query_id != self.source_query_id:
            raise ValueError("route_approval.query_id must match source_query_id")
        if self.route_approval.route_kind != RouteKind.LOCAL_CONTRIBUTION:
            raise ValueError(
                "LocalSiloContributionRequest route_approval must be local_contribution"
            )
        if self.route_approval.requesting_bank_id != self.requesting_bank_id:
            raise ValueError(
                "route_approval.requesting_bank_id must match requesting_bank_id"
            )
        if self.route_approval.responding_bank_id != self.responding_bank_id:
            raise ValueError(
                "route_approval.responding_bank_id must match responding_bank_id"
            )
        return self


class IntResponseValue(StrictModel):
    """Integer response value."""

    int: int


class FloatResponseValue(StrictModel):
    """Float response value."""

    float: float


class BoolResponseValue(StrictModel):
    """Boolean response value."""

    bool: bool


class HistogramResponseValue(StrictModel):
    """Histogram response value."""

    histogram: list[NonNegativeInt]


class HashListResponseValue(StrictModel):
    """Hash-list response value."""

    hash_list: list[OpaqueHashToken] = Field(max_length=100)


ResponseValue: TypeAlias = (
    IntResponseValue
    | FloatResponseValue
    | BoolResponseValue
    | HistogramResponseValue
    | HashListResponseValue
)


def response_value_kind(value: ResponseValue) -> ResponseValueKind:
    """Return the enum kind for a typed response value."""
    if isinstance(value, IntResponseValue):
        return ResponseValueKind.INT
    if isinstance(value, FloatResponseValue):
        return ResponseValueKind.FLOAT
    if isinstance(value, BoolResponseValue):
        return ResponseValueKind.BOOL
    if isinstance(value, HistogramResponseValue):
        return ResponseValueKind.HISTOGRAM
    if isinstance(value, HashListResponseValue):
        return ResponseValueKind.HASH_LIST
    raise TypeError(f"Unsupported response value type: {type(value)!r}")


class PrimitiveCallRecord(StrictModel):
    """Provenance record for one stats-primitive output field."""

    field_name: NonEmptyStr
    primitive_name: NonEmptyStr
    args_hash: Sha256Hex
    privacy_unit: PrivacyUnit = PrivacyUnit.TRANSACTION
    rho_debited: NonNegativeFloat = 0.0
    eps_delta_display: tuple[NonNegativeFloat, NonNegativeFloat] | None = None
    sigma_applied: NonNegativeFloat | None = None
    sensitivity: NonNegativeFloat
    returned_value_kind: ResponseValueKind
    timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_utc(cls, value: datetime) -> datetime:
        return _normalize_utc(value)


class Sec314bResponse(Message):
    """A3 response to an approved peer query or local contribution route.

    For `LocalSiloContributionRequest`, `in_reply_to` carries the upstream
    `source_query_id` so F1 can merge requester-bank and peer-bank
    contributions under one investigation query.
    """

    message_type: Literal["sec314b_response"] = MessageType.SEC314B_RESPONSE.value
    in_reply_to: UUID
    responding_bank_id: BankId
    fields: dict[str, ResponseValue] = Field(default_factory=dict)
    provenance: list[PrimitiveCallRecord] = Field(default_factory=list)
    rho_debited_total: NonNegativeFloat = 0.0
    refusal_reason: str | None = None

    @field_validator("refusal_reason")
    @classmethod
    def refusal_reason_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("refusal_reason cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_provenance(self) -> Sec314bResponse:
        field_names = set(self.fields)
        provenance_names = [record.field_name for record in self.provenance]
        if len(provenance_names) != len(set(provenance_names)):
            raise ValueError("provenance field_name values must be unique")
        if field_names != set(provenance_names):
            raise ValueError("fields must exactly match provenance field_name values")

        for record in self.provenance:
            actual_kind = response_value_kind(self.fields[record.field_name])
            if actual_kind != record.returned_value_kind:
                raise ValueError(
                    f"provenance kind mismatch for {record.field_name}: "
                    f"{record.returned_value_kind} != {actual_kind}"
                )

        expected_rho = sum(record.rho_debited for record in self.provenance)
        if not math.isclose(self.rho_debited_total, expected_rho, abs_tol=1e-12):
            raise ValueError("rho_debited_total must equal provenance rho_debited sum")

        if self.refusal_reason is not None and (self.fields or self.provenance):
            raise ValueError("refusal responses cannot include fields or provenance")
        return self


class SanctionsCheckRequest(Message):
    """Request to screen hashed entities against the mock sanctions and PEP list."""

    message_type: Literal["sanctions_check_request"] = (
        MessageType.SANCTIONS_CHECK_REQUEST.value
    )
    entity_hashes: list[CrossBankHashToken] = Field(min_length=1, max_length=100)
    requesting_context: MediumText

    @field_validator("requesting_context")
    @classmethod
    def context_must_not_contain_customer_names(cls, value: str) -> str:
        return _reject_demo_customer_names(value, "requesting_context")


class SanctionsResult(StrictModel):
    """Sanctions and PEP result for one hashed entity."""

    sdn_match: bool
    pep_relation: bool


class SanctionsCheckResponse(Message):
    """Sanctions response keyed by hashed entity, with no list contents disclosed."""

    message_type: Literal["sanctions_check_response"] = (
        MessageType.SANCTIONS_CHECK_RESPONSE.value
    )
    in_reply_to: UUID
    results: dict[CrossBankHashToken, SanctionsResult]


class BankAggregate(StrictModel):
    """DP-noised per-bank aggregate sent to F2."""

    bank_id: BankId
    edge_count_distribution: list[NonNegativeInt]
    bucketed_flow_histogram: list[NonNegativeInt]
    rho_debited: NonNegativeFloat = 0.0

    @model_validator(mode="after")
    def bank_id_must_be_real_bank(self) -> BankAggregate:
        if self.bank_id == BankId.FEDERATION:
            raise ValueError("bank aggregate must come from a bank")
        return self


class GraphPatternRequest(Message):
    """Request for F2 graph-pattern analysis."""

    message_type: Literal["graph_pattern_request"] = (
        MessageType.GRAPH_PATTERN_REQUEST.value
    )
    pattern_aggregates: list[BankAggregate] = Field(min_length=1)
    window_start: date
    window_end: date

    @model_validator(mode="after")
    def validate_window(self) -> GraphPatternRequest:
        _validate_window(self.window_start, self.window_end)
        return self


class GraphPatternResponse(Message):
    """F2 graph-pattern analysis result."""

    message_type: Literal["graph_pattern_response"] = (
        MessageType.GRAPH_PATTERN_RESPONSE.value
    )
    pattern_class: PatternClass
    confidence: float = Field(ge=0.0, le=1.0)
    suspect_entity_hashes: list[CrossBankHashToken] = Field(default_factory=list)
    narrative: MediumText

    @field_validator("narrative")
    @classmethod
    def narrative_must_not_contain_customer_names(cls, value: str) -> str:
        return _reject_demo_customer_names(value, "narrative")


class ContributorAttribution(StrictModel):
    """Per-bank attribution block in a SAR draft."""

    bank_id: BankId
    investigator_id: NonEmptyStr
    evidence_item_ids: list[UUID] = Field(default_factory=list)
    contribution_summary: MediumText

    @field_validator("contribution_summary")
    @classmethod
    def contribution_summary_must_not_contain_customer_names(cls, value: str) -> str:
        return _reject_demo_customer_names(value, "contribution_summary")


class SARContribution(Message):
    """A2 contribution sent to F4 for SAR drafting."""

    message_type: Literal["sar_contribution"] = MessageType.SAR_CONTRIBUTION.value
    contributing_bank_id: BankId
    contributing_investigator_id: NonEmptyStr
    contributed_evidence: list[EvidenceItem] = Field(min_length=1)
    local_rationale: MediumText
    related_query_ids: list[UUID] = Field(default_factory=list)

    @field_validator("local_rationale")
    @classmethod
    def local_rationale_must_not_contain_customer_names(cls, value: str) -> str:
        return _reject_demo_customer_names(value, "local_rationale")


class SARDraft(Message):
    """Structured SAR draft emitted by F4."""

    message_type: Literal["sar_draft"] = MessageType.SAR_DRAFT.value
    sar_id: UUID = Field(default_factory=uuid4)
    filing_institution: NonEmptyStr | None = None
    suspicious_amount_range: tuple[NonNegativeInt, NonNegativeInt] | None = None
    typology_code: TypologyCode | None = None
    narrative: MediumText | None = None
    contributors: list[ContributorAttribution] = Field(default_factory=list)
    sar_priority: SARPriority = SARPriority.STANDARD
    mandatory_fields_complete: bool = False
    related_query_ids: list[UUID] = Field(default_factory=list)

    @field_validator("narrative")
    @classmethod
    def sar_narrative_must_not_contain_customer_names(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _reject_demo_customer_names(value, "narrative")

    @model_validator(mode="after")
    def validate_required_fields(self) -> SARDraft:
        if self.suspicious_amount_range is not None:
            low, high = self.suspicious_amount_range
            if low > high:
                raise ValueError("suspicious_amount_range lower bound cannot exceed upper")

        if self.mandatory_fields_complete:
            missing = [
                name
                for name, value in (
                    ("filing_institution", self.filing_institution),
                    ("suspicious_amount_range", self.suspicious_amount_range),
                    ("typology_code", self.typology_code),
                    ("narrative", self.narrative),
                )
                if value is None or value == ""
            ]
            if missing:
                raise ValueError(
                    "mandatory_fields_complete cannot be true when fields are missing: "
                    + ", ".join(missing)
                )
        return self


class MessageSentPayload(StrictModel):
    """Audit payload for routed messages."""

    kind: Literal["message_sent"] = AuditEventKind.MESSAGE_SENT.value
    message_type: NonEmptyStr
    source_agent_id: NonEmptyStr
    destination_agent_id: NonEmptyStr


class LtVerdictPayload(StrictModel):
    """Audit payload for Lobster Trap verdicts."""

    kind: Literal["lt_verdict"] = AuditEventKind.LT_VERDICT.value
    verdict: NonEmptyStr
    request_id: NonEmptyStr | None = None
    rule_name: NonEmptyStr | None = None


class ConstraintViolationPayload(StrictModel):
    """Audit payload for deterministic constraint failures."""

    kind: Literal["constraint_violation"] = AuditEventKind.CONSTRAINT_VIOLATION.value
    violation: NonEmptyStr
    blocked: bool = True


class BypassTriggeredPayload(StrictModel):
    """Audit payload for deterministic bypass rules."""

    kind: Literal["bypass_triggered"] = AuditEventKind.BYPASS_TRIGGERED.value
    rule_name: NonEmptyStr
    reason: MediumText


class RhoDebitedPayload(StrictModel):
    """Audit payload for privacy-budget debits."""

    kind: Literal["rho_debited"] = AuditEventKind.RHO_DEBITED.value
    requester_key: NonEmptyStr
    bank_id: BankId
    rho_debited: NonNegativeFloat
    rho_remaining: NonNegativeFloat


class BudgetExhaustedPayload(StrictModel):
    """Audit payload for refused DP calls after budget exhaustion."""

    kind: Literal["budget_exhausted"] = AuditEventKind.BUDGET_EXHAUSTED.value
    requester_key: NonEmptyStr
    bank_id: BankId
    rho_requested: NonNegativeFloat
    rho_remaining: NonNegativeFloat


class HumanReviewPayload(StrictModel):
    """Audit payload for F5 human-review annotations."""

    kind: Literal["human_review"] = AuditEventKind.HUMAN_REVIEW.value
    reason: MediumText
    severity: Literal["low", "medium", "high"] = "medium"


class RateLimitPayload(StrictModel):
    """Audit payload for rate-limit advisory events."""

    kind: Literal["rate_limit"] = AuditEventKind.RATE_LIMIT.value
    requester_id: NonEmptyStr
    window_seconds: int = Field(gt=0)
    count: int = Field(ge=0)
    limit: int = Field(gt=0)


AuditPayload: TypeAlias = Annotated[
    MessageSentPayload
    | LtVerdictPayload
    | ConstraintViolationPayload
    | BypassTriggeredPayload
    | RhoDebitedPayload
    | BudgetExhaustedPayload
    | HumanReviewPayload
    | RateLimitPayload,
    Field(discriminator="kind"),
]


class AuditEvent(Message):
    """Signed wire-level audit event emitted to the federation audit stream.

    Runtime agents emit backend.agents.base.RuntimeAuditEvent first; P15 maps
    those local records into this cross-node envelope.
    """

    message_type: Literal["audit_event"] = MessageType.AUDIT_EVENT.value
    event_id: UUID = Field(default_factory=uuid4)
    kind: AuditEventKind
    actor_agent_id: NonEmptyStr
    payload: AuditPayload

    @model_validator(mode="after")
    def payload_kind_must_match_header(self) -> AuditEvent:
        payload_kind = AuditEventKind(self.payload.kind)
        if payload_kind != self.kind:
            raise ValueError("kind must match payload.kind")
        return self


class DismissalRationale(Message):
    """A2 dismissal rationale emitted for F5 audit review."""

    message_type: Literal["dismissal_rationale"] = MessageType.DISMISSAL_RATIONALE.value
    alert_id: UUID
    reason: MediumText
    evidence_considered: list[UUID] = Field(default_factory=list)

    @field_validator("reason")
    @classmethod
    def reason_must_not_contain_customer_names(cls, value: str) -> str:
        return _reject_demo_customer_names(value, "reason")


PUBLIC_MESSAGE_MODELS: tuple[type[BaseModel], ...] = (
    Alert,
    Sec314bQuery,
    LocalSiloContributionRequest,
    Sec314bResponse,
    SanctionsCheckRequest,
    SanctionsCheckResponse,
    GraphPatternRequest,
    GraphPatternResponse,
    SARContribution,
    SARDraft,
    AuditEvent,
    DismissalRationale,
)


AgentMessage: TypeAlias = Annotated[
    Alert
    | Sec314bQuery
    | LocalSiloContributionRequest
    | Sec314bResponse
    | SanctionsCheckRequest
    | SanctionsCheckResponse
    | GraphPatternRequest
    | GraphPatternResponse
    | SARContribution
    | SARDraft
    | AuditEvent
    | DismissalRationale,
    Field(discriminator="message_type"),
]
