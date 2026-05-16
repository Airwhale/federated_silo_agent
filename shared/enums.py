"""Shared enum values for cross-agent message contracts."""

from __future__ import annotations

from enum import StrEnum


class AgentRole(StrEnum):
    """Agent roles that can appear on message envelopes."""

    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"
    F5 = "F5"
    F6 = "F6"
    ORCHESTRATOR = "orchestrator"


class BankId(StrEnum):
    """Known bank identifiers plus the federation runtime."""

    BANK_ALPHA = "bank_alpha"
    BANK_BETA = "bank_beta"
    BANK_GAMMA = "bank_gamma"
    FEDERATION = "federation"

    @property
    def is_peer_bank(self) -> bool:
        """Return True for peer-bank participants in cross-bank §314(b) flows.

        FEDERATION is the federation runtime, not a peer; any future non-bank
        role (regulator, auditor, sandbox) must explicitly be excluded here so
        that places like F1's route planning do not accidentally treat the
        role as a target bank.
        """
        return self != BankId.FEDERATION


class MessageType(StrEnum):
    """Serialized top-level message type discriminators."""

    ALERT = "alert"
    SEC314B_QUERY = "sec314b_query"
    LOCAL_SILO_CONTRIBUTION_REQUEST = "local_silo_contribution_request"
    SEC314B_RESPONSE = "sec314b_response"
    SANCTIONS_CHECK_REQUEST = "sanctions_check_request"
    SANCTIONS_CHECK_RESPONSE = "sanctions_check_response"
    GRAPH_PATTERN_REQUEST = "graph_pattern_request"
    GRAPH_PATTERN_RESPONSE = "graph_pattern_response"
    POLICY_EVALUATION_REQUEST = "policy_evaluation_request"
    POLICY_EVALUATION_RESULT = "policy_evaluation_result"
    SAR_CONTRIBUTION = "sar_contribution"
    SAR_ASSEMBLY_REQUEST = "sar_assembly_request"
    SAR_CONTRIBUTION_REQUEST = "sar_contribution_request"
    SAR_DRAFT = "sar_draft"
    AUDIT_REVIEW_REQUEST = "audit_review_request"
    AUDIT_REVIEW_RESULT = "audit_review_result"
    AUDIT_EVENT = "audit_event"
    DISMISSAL_RATIONALE = "dismissal_rationale"


class SignalType(StrEnum):
    """Local alert signal types surfaced by A1.

    `CTR_REPORT` is distinct from `STRUCTURING`. A Currency Transaction Report
    is the federal reporting requirement triggered by single transactions at
    or above $10,000 (FFIEC BSA/AML Examination Manual). Structuring is the
    deliberate splitting of sub-$10K transactions to evade the CTR threshold.
    They are opposite typologies, not synonyms.
    """

    STRUCTURING = "structuring"
    LAYERING = "layering"
    RAPID_MOVEMENT = "rapid_movement"
    COUNTERPARTY_RISK = "counterparty_risk"
    SANCTIONS_MATCH = "sanctions_match"
    PEP_RELATION = "pep_relation"
    CTR_REPORT = "ctr_report"


class TypologyCode(StrEnum):
    """AML typology codes used in purpose declarations and SAR drafts."""

    STRUCTURING = "structuring"
    LAYERING = "layering"
    TERRORIST_FINANCING = "terrorist_financing"
    SANCTIONS_EVASION = "sanctions_evasion"
    PEP_EXPOSURE = "pep_exposure"


class QueryShape(StrEnum):
    """Allowed cross-bank query shapes."""

    ENTITY_PRESENCE = "entity_presence"
    AGGREGATE_ACTIVITY = "aggregate_activity"
    COUNTERPARTY_LINKAGE = "counterparty_linkage"


class RouteKind(StrEnum):
    """F1-to-A3 route kinds with different disclosure semantics."""

    PEER_314B = "peer_314b"
    LOCAL_CONTRIBUTION = "local_contribution"


class PatternClass(StrEnum):
    """Cross-bank graph pattern labels emitted by F2."""

    STRUCTURING_RING = "structuring_ring"
    LAYERING_CHAIN = "layering_chain"
    NONE = "none"


class SARPriority(StrEnum):
    """SAR priority classes."""

    STANDARD = "standard"
    HIGH = "high"


class PolicyDecision(StrEnum):
    """Normalized Lobster Trap / AML policy adapter decisions."""

    ALLOW = "allow"
    REDACT = "redact"
    ESCALATE = "escalate"
    BLOCK = "block"


class PolicySeverity(StrEnum):
    """Severity labels used by policy and audit review outputs."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyContentChannel(StrEnum):
    """Content channels evaluated by the F6 policy actor."""

    NATURAL_LANGUAGE = "natural_language"
    STRUCTURED_MESSAGE = "structured_message"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    AUDIT_EVENT = "audit_event"


class AuditReviewScope(StrEnum):
    """F5 audit review scopes."""

    INVESTIGATION = "investigation"
    RATE_LIMIT = "rate_limit"
    DISMISSAL = "dismissal"
    FULL_RUN = "full_run"


class AuditEventKind(StrEnum):
    """Audit event types consumed by the audit stream and F5."""

    MESSAGE_SENT = "message_sent"
    LT_VERDICT = "lt_verdict"
    CONSTRAINT_VIOLATION = "constraint_violation"
    BYPASS_TRIGGERED = "bypass_triggered"
    RHO_DEBITED = "rho_debited"
    BUDGET_EXHAUSTED = "budget_exhausted"
    HUMAN_REVIEW = "human_review"
    RATE_LIMIT = "rate_limit"


class PrivacyUnit(StrEnum):
    """Privacy unit attached to primitive provenance records."""

    TRANSACTION = "transaction"
    ACCOUNT = "account"
    CUSTOMER = "customer"
    NONE = "none"


class ResponseValueKind(StrEnum):
    """Value shapes allowed in Sec314bResponse fields."""

    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    HISTOGRAM = "histogram"
    HASH_LIST = "hash_list"
