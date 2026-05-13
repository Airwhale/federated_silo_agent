"""Shared enum values for cross-agent message contracts."""

from __future__ import annotations

from enum import StrEnum


class AgentRole(StrEnum):
    """Agent roles that can appear on message envelopes."""

    A1 = "A1"
    A2 = "A2"
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"
    F5 = "F5"
    ORCHESTRATOR = "orchestrator"


class BankId(StrEnum):
    """Known bank identifiers plus the federation runtime."""

    BANK_ALPHA = "bank_alpha"
    BANK_BETA = "bank_beta"
    BANK_GAMMA = "bank_gamma"
    FEDERATION = "federation"


class SignalType(StrEnum):
    """Local alert signal types surfaced by A1."""

    STRUCTURING = "structuring"
    LAYERING = "layering"
    RAPID_MOVEMENT = "rapid_movement"
    COUNTERPARTY_RISK = "counterparty_risk"
    SANCTIONS_MATCH = "sanctions_match"
    PEP_RELATION = "pep_relation"


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


class PatternClass(StrEnum):
    """Cross-bank graph pattern labels emitted by F2."""

    STRUCTURING_RING = "structuring_ring"
    LAYERING_CHAIN = "layering_chain"
    NONE = "none"


class SARPriority(StrEnum):
    """SAR priority classes."""

    STANDARD = "standard"
    HIGH = "high"


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
