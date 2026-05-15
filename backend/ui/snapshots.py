"""Pydantic contracts for the judge-console control API."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints
from backend.security.replay import ReplayCacheSnapshot
from shared.enums import BankId, RouteKind


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# `ShortText` is the detail-text type for most snapshot fields. The cap is
# generous (2048) because several callers assign exception messages
# directly (e.g. `_envelope_snapshot(detail=str(exc))`), and a downstream
# security or transport library could produce a long error string. Static
# labels stay well under the cap; a 500-from-validation on an unusually
# long error string would mask the underlying failure mode.
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]
ProbePayloadText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
]

# Allowed values for ``target_instance_id`` on probe and interaction
# requests. Must mirror the frontend's ``TRUST_INSTANCES`` registry. The
# character-class constraint catches raw garbage; this set catches
# semantically wrong inputs (e.g. a ``ComponentId`` value, a random
# string, or an injected payload that happens to be alphanumeric).
KNOWN_TRUST_DOMAIN_IDS: frozenset[str] = frozenset(
    {"investigator", "federation", "bank_alpha", "bank_beta", "bank_gamma"}
)


def _validate_known_trust_domain(value: str) -> str:
    if value not in KNOWN_TRUST_DOMAIN_IDS:
        raise ValueError(
            f"target_instance_id {value!r} is not a known trust domain "
            f"(expected one of: {sorted(KNOWN_TRUST_DOMAIN_IDS)})"
        )
    return value


InstanceIdText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$"),
    AfterValidator(_validate_known_trust_domain),
]


def utc_now() -> datetime:
    return datetime.now(UTC)


class UiModel(BaseModel):
    """Strict base model for UI/API boundaries."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SnapshotStatus(StrEnum):
    """Readiness state for one inspectable subsystem."""

    LIVE = "live"
    BLOCKED = "blocked"
    NOT_BUILT = "not_built"
    PENDING = "pending"
    SIMULATED = "simulated"
    ERROR = "error"


class ComponentId(StrEnum):
    """Inspectable node or mechanism ids shown in the judge console."""

    A1 = "A1"
    A2 = "A2"
    F1 = "F1"
    BANK_ALPHA_A3 = "bank_alpha.A3"
    BANK_BETA_A3 = "bank_beta.A3"
    BANK_GAMMA_A3 = "bank_gamma.A3"
    P7 = "P7"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"
    F5 = "F5"
    LOBSTER_TRAP = "lobster_trap"
    LITELLM = "litellm"
    SIGNING = "signing"
    ENVELOPE = "envelope"
    REPLAY = "replay"
    ROUTE_APPROVAL = "route_approval"
    DP_LEDGER = "dp_ledger"
    AUDIT_CHAIN = "audit_chain"


class SecurityLayer(StrEnum):
    """Layer that accepted, blocked, or will later handle a probe."""

    SCHEMA = "schema"
    SIGNATURE = "signature"
    ALLOWLIST = "allowlist"
    FRESHNESS = "freshness"
    REPLAY = "replay"
    ROUTE_APPROVAL = "route_approval"
    LOBSTER_TRAP = "lobster_trap"
    A3_POLICY = "a3_policy"
    P7_BUDGET = "p7_budget"
    NOT_BUILT = "not_built"
    ACCEPTED = "accepted"
    INTERNAL_ERROR = "internal_error"


class ProbeKind(StrEnum):
    """Controlled adversarial inputs available through the demo API."""

    PROMPT_INJECTION = "prompt_injection"
    UNSIGNED_MESSAGE = "unsigned_message"
    BODY_TAMPER = "body_tamper"
    WRONG_ROLE = "wrong_role"
    REPLAY_NONCE = "replay_nonce"
    ROUTE_MISMATCH = "route_mismatch"
    UNSUPPORTED_QUERY_SHAPE = "unsupported_query_shape"
    BUDGET_EXHAUSTION = "budget_exhaustion"


class ComponentInteractionKind(StrEnum):
    """Safe component-directed actions from the judge console."""

    PROMPT = "prompt"
    INSPECT = "inspect"
    EXPLAIN_STATE = "explain_state"
    SAFE_INPUT = "safe_input"


class AttackerProfile(StrEnum):
    """Demo principal profile used to build a probe."""

    UNKNOWN = "unknown"
    WRONG_ROLE = "wrong_role"
    VALID_BUT_MALICIOUS = "valid_but_malicious"


class SessionMode(StrEnum):
    """Execution mode selected for a demo session."""

    STUB = "stub"
    LIVE = "live"
    LIVE_WITH_STUB_FALLBACK = "live_with_stub_fallback"


class SnapshotField(UiModel):
    """One redacted key/value field for generic UI cards."""

    name: NonEmptyStr
    value: str
    redacted: bool = False


class ComponentReadinessSnapshot(UiModel):
    """Readiness for one component in the demo stack."""

    component_id: ComponentId
    label: NonEmptyStr
    status: SnapshotStatus
    available_after: str | None = None
    detail: ShortText


class SigningStateSnapshot(UiModel):
    """Public signing state. Private keys are never exposed."""

    status: SnapshotStatus
    known_signing_key_ids: list[NonEmptyStr]
    private_key_material_exposed: Literal[False] = False
    last_verified_key_id: str | None = None
    detail: ShortText


class EnvelopeVerificationSnapshot(UiModel):
    """Last signed-envelope verification result visible to the UI."""

    status: SnapshotStatus
    message_type: str | None = None
    sender_agent_id: str | None = None
    recipient_agent_id: str | None = None
    body_hash: str | None = None
    signature_status: Literal["valid", "invalid", "missing", "not_checked"] = "not_checked"
    freshness_status: Literal["fresh", "expired", "not_checked"] = "not_checked"
    blocked_by: SecurityLayer | None = None
    detail: ShortText


class RouteApprovalSnapshot(UiModel):
    """Route-approval binding state for UI inspection."""

    status: SnapshotStatus
    query_id: UUID | None = None
    route_kind: RouteKind | None = None
    approved_query_body_hash: str | None = None
    computed_query_body_hash: str | None = None
    requester_bank_id: BankId | None = None
    responder_bank_id: BankId | None = None
    binding_status: Literal["matched", "mismatched", "not_checked"] = "not_checked"
    detail: ShortText


class DpLedgerEntrySnapshot(UiModel):
    """One requester/bank rho budget row."""

    requester_key: NonEmptyStr
    responding_bank_id: BankId
    rho_spent: float = Field(ge=0.0)
    rho_remaining: float = Field(ge=0.0)
    rho_max: float = Field(gt=0.0)


class DpLedgerSnapshot(UiModel):
    """UI-facing DP ledger state."""

    status: SnapshotStatus
    entries: list[DpLedgerEntrySnapshot] = Field(default_factory=list)
    detail: ShortText


class ProviderHealthSnapshot(UiModel):
    """Provider and proxy health with secrets redacted."""

    status: SnapshotStatus
    lobster_trap_configured: bool
    litellm_configured: bool
    gemini_api_key_present: bool
    openrouter_api_key_present: bool
    secret_values: Literal["redacted"] = "redacted"
    detail: ShortText


class AuditChainSnapshot(UiModel):
    """Audit-chain state exposed to the UI."""

    status: SnapshotStatus
    event_count: int = Field(ge=0)
    latest_event_hash: str | None = None
    detail: ShortText


class ComponentSnapshot(UiModel):
    """Generic component inspector payload."""

    component_id: ComponentId
    status: SnapshotStatus
    title: NonEmptyStr
    fields: list[SnapshotField] = Field(default_factory=list)
    signing: SigningStateSnapshot | None = None
    envelope: EnvelopeVerificationSnapshot | None = None
    replay: ReplayCacheSnapshot | None = None
    route_approval: RouteApprovalSnapshot | None = None
    dp_ledger: DpLedgerSnapshot | None = None
    provider_health: ProviderHealthSnapshot | None = None
    audit_chain: AuditChainSnapshot | None = None


class TimelineEventSnapshot(UiModel):
    """One event in the demo timeline."""

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    component_id: ComponentId
    title: NonEmptyStr
    detail: ShortText
    status: SnapshotStatus
    blocked_by: SecurityLayer | None = None


class SessionCreateRequest(UiModel):
    """Create or reset one demo session."""

    scenario_id: NonEmptyStr = "s1_structuring_ring"
    mode: SessionMode = SessionMode.STUB


class SessionSnapshot(UiModel):
    """Summary of one demo session."""

    session_id: UUID
    scenario_id: NonEmptyStr
    mode: SessionMode
    phase: NonEmptyStr
    created_at: datetime
    updated_at: datetime
    components: list[ComponentReadinessSnapshot]
    latest_events: list[TimelineEventSnapshot] = Field(default_factory=list)


class SystemSnapshot(UiModel):
    """Global API/system readiness."""

    status: SnapshotStatus
    components: list[ComponentReadinessSnapshot]
    provider_health: ProviderHealthSnapshot
    detail: ShortText


class ProbeRequest(UiModel):
    """Controlled attack request sent through a real or placeholder boundary."""

    probe_kind: ProbeKind
    target_component: ComponentId
    attacker_profile: AttackerProfile = AttackerProfile.VALID_BUT_MALICIOUS
    payload_text: ProbePayloadText | None = None
    target_instance_id: InstanceIdText | None = None


class ComponentInteractionRequest(UiModel):
    """Safe component interaction request for the judge console."""

    interaction_kind: ComponentInteractionKind
    payload_text: ProbePayloadText | None = None
    attacker_profile: AttackerProfile = AttackerProfile.VALID_BUT_MALICIOUS
    target_instance_id: InstanceIdText | None = None


class HealthSnapshot(UiModel):
    """Minimal readiness response for process health probes."""

    status: Literal["ok"] = "ok"


class ProbeResult(UiModel):
    """Outcome of one adversarial probe.

    Carries the full state bundle that ``DemoControlService.run_probe``
    commits to the session under one short critical section. Handlers
    set the relevant ``envelope`` / ``route_approval`` / ``dp_ledger``
    fields here instead of mutating session state directly, so probe
    execution can run outside the session lock.
    """

    probe_id: UUID = Field(default_factory=uuid4)
    probe_kind: ProbeKind
    target_component: ComponentId
    attacker_profile: AttackerProfile
    accepted: bool
    blocked_by: SecurityLayer
    reason: ShortText
    envelope: EnvelopeVerificationSnapshot | None = None
    replay: ReplayCacheSnapshot | None = None
    route_approval: RouteApprovalSnapshot | None = None
    dp_ledger: DpLedgerSnapshot | None = None
    timeline_event: TimelineEventSnapshot


class ComponentInteractionResult(UiModel):
    """Outcome of one safe component-directed interaction.

    Two boolean fields disambiguate "we got it" from "we ran it":

    * ``accepted`` -- the request passed validation and was recorded.
      False only when the component is not built yet (and therefore
      cannot be interacted with at all).
    * ``executed`` -- a live handler actually ran and produced
      meaningful output. False for PROMPT / SAFE_INPUT today because
      the live LT / LLM adapter lands with P14/P15; the request is
      still ``accepted`` and shows up on the timeline.

    The UI uses both to distinguish "successfully inspected" from
    "queued for a future handler" from "refused / not built".
    """

    interaction_id: UUID = Field(default_factory=uuid4)
    interaction_kind: ComponentInteractionKind
    target_component: ComponentId
    target_instance_id: str | None = None
    attacker_profile: AttackerProfile
    accepted: bool
    executed: bool
    status: SnapshotStatus
    blocked_by: SecurityLayer | None = None
    reason: ShortText
    timeline_event: TimelineEventSnapshot
    component_snapshot: ComponentSnapshot | None = None
    available_after: str | None = None
