"""Pydantic boundary models for the A1 monitoring agent."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from shared.enums import BankId
from shared.messages import Alert, Sha256Hex


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
HashText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
]
DecisionAction = Literal["emit", "suppress"]
BypassRuleId = Literal["A1-B1", "A1-B2", "A1-B3"]


class A1Model(BaseModel):
    """Strict Pydantic base for A1 boundary objects."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class SignalCandidate(A1Model):
    """A local suspicious-signal candidate with joined transaction context."""

    signal_id: NonEmptyStr
    transaction_id: NonEmptyStr
    amount: float = Field(ge=0.0)
    transaction_type: NonEmptyStr
    channel: NonEmptyStr
    timestamp: datetime
    account_id: NonEmptyStr
    account_id_hash: Sha256Hex
    customer_name_hash: HashText
    customer_kyc_tier: NonEmptyStr
    transaction_id_hash: Sha256Hex
    recent_near_ctr_count_24h: int = Field(ge=0)
    counterparty_account_id_hashed: HashText
    source_signal_type: NonEmptyStr
    source_severity: float = Field(ge=0.0, le=1.0)


class A1BatchInput(A1Model):
    """Batch input for one local A1 monitoring pass."""

    bank_id: BankId
    a1_agent_id: NonEmptyStr
    local_a2_agent_id: NonEmptyStr
    candidates: list[SignalCandidate] = Field(min_length=1, max_length=50)


class A1Decision(A1Model):
    """A1 decision for exactly one suspicious-signal candidate."""

    signal_id: NonEmptyStr
    action: DecisionAction
    alert: Alert | None = None
    llm_rationale: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    ]
    bypass_rule_id: BypassRuleId | None = None

    @model_validator(mode="after")
    def alert_presence_must_match_action(self) -> A1Decision:
        if self.action == "emit" and self.alert is None:
            raise ValueError("emit decisions must include an alert")
        if self.action == "suppress" and self.alert is not None:
            raise ValueError("suppress decisions cannot include an alert")
        return self


class A1BatchResult(A1Model):
    """Structured output from A1 for one local monitoring batch."""

    decisions: list[A1Decision] = Field(min_length=1, max_length=50)
