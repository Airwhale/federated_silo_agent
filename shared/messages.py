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
    PatternClass,
    PrivacyUnit,
    QueryShape,
    ResponseValueKind,
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
HashString: TypeAlias = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
]
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
# primary mechanisms are LT egress redaction, schema validation, and the
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


def _reject_demo_customer_names(value: str, field_name: str) -> str:
    if _DEMO_CUSTOMER_NAME_RE.search(value):
        raise ValueError(f"{field_name} must not contain customer names")
    return value


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

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_utc(cls, value: datetime) -> datetime:
        return _normalize_utc(value)


class EvidenceItem(StrictModel):
    """Hash-only evidence summary that can cross bank boundaries."""

    evidence_id: UUID = Field(default_factory=uuid4)
    summary: ShortText
    entity_hashes: list[HashString] = Field(default_factory=list)
    account_hashes: list[HashString] = Field(default_factory=list)
    transaction_hashes: list[HashString] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def summary_must_not_contain_customer_names(cls, value: str) -> str:
        return _reject_demo_customer_names(value, "summary")


class Alert(Message):
    """A1 alert delivered to a local A2 investigator."""

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
    name_hashes: list[HashString] = Field(min_length=1)
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
    name_hashes: list[HashString] = Field(min_length=1)
    window_start: date
    window_end: date
    metrics: list[NonEmptyStr] = Field(default_factory=lambda: ["alert_count"])

    @model_validator(mode="after")
    def validate_window(self) -> AggregateActivityPayload:
        _validate_window(self.window_start, self.window_end)
        return self


class CounterpartyLinkagePayload(StrictModel):
    """Query for counterparty linkage around hashed account identifiers."""

    query_shape: Literal["counterparty_linkage"] = QueryShape.COUNTERPARTY_LINKAGE.value
    account_hashes: list[HashString] = Field(min_length=1)
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


class Sec314bQuery(Message):
    """A Section 314(b) query routed from one A2 to peer-bank A2s via F1."""

    query_id: UUID = Field(default_factory=uuid4)
    requesting_investigator_id: NonEmptyStr
    requesting_bank_id: BankId
    target_bank_ids: list[BankId] = Field(
        default_factory=lambda: [BankId.BANK_ALPHA, BankId.BANK_BETA, BankId.BANK_GAMMA],
        min_length=1,
    )
    query_shape: QueryShape
    query_payload: QueryPayload
    purpose_declaration: PurposeDeclaration
    requested_rho_per_primitive: NonNegativeFloat = 0.0

    @model_validator(mode="after")
    def payload_shape_must_match_header(self) -> Sec314bQuery:
        payload_shape = QueryShape(self.query_payload.query_shape)
        if payload_shape != self.query_shape:
            raise ValueError("query_shape must match query_payload.query_shape")
        if BankId.FEDERATION in self.target_bank_ids:
            raise ValueError("target_bank_ids must contain only peer banks")
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

    hash_list: list[HashString]


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
    """Peer-bank response to a Section 314(b) query."""

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

    entity_hashes: list[HashString] = Field(min_length=1)
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

    in_reply_to: UUID
    results: dict[HashString, SanctionsResult]


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

    pattern_aggregates: list[BankAggregate] = Field(min_length=1)
    window_start: date
    window_end: date

    @model_validator(mode="after")
    def validate_window(self) -> GraphPatternRequest:
        _validate_window(self.window_start, self.window_end)
        return self


class GraphPatternResponse(Message):
    """F2 graph-pattern analysis result."""

    pattern_class: PatternClass
    confidence: float = Field(ge=0.0, le=1.0)
    suspect_entity_hashes: list[HashString] = Field(default_factory=list)
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

    contributing_bank_id: BankId
    contributing_investigator_id: NonEmptyStr
    contributed_evidence: list[EvidenceItem] = Field(min_length=1)
    local_rationale: MediumText

    @field_validator("local_rationale")
    @classmethod
    def local_rationale_must_not_contain_customer_names(cls, value: str) -> str:
        return _reject_demo_customer_names(value, "local_rationale")


class SARDraft(Message):
    """Structured SAR draft emitted by F4."""

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
    """Normalized audit event emitted by runtime, policy, and DP layers."""

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
