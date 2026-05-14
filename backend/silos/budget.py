"""Per-requester privacy-budget accounting for bank-local primitives."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from shared.enums import BankId


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BudgetModel(BaseModel):
    """Strict Pydantic base for P7 budget boundary objects."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class RequesterKey(BudgetModel):
    """Budget key for one investigator querying one responding bank."""

    requesting_investigator_id: NonEmptyStr
    requesting_bank_id: BankId
    responding_bank_id: BankId

    @property
    def stable_key(self) -> str:
        return "|".join(
            (
                self.requesting_investigator_id,
                self.requesting_bank_id.value,
                self.responding_bank_id.value,
            )
        )


class BudgetDebit(BudgetModel):
    """Result of one budget debit attempt."""

    allowed: bool
    requester_key: RequesterKey
    rho_requested: float = Field(ge=0.0)
    rho_spent: float = Field(ge=0.0)
    rho_remaining: float = Field(ge=0.0)
    refusal_reason: Literal["budget_exhausted"] | None = None


class BudgetSnapshot(BudgetModel):
    """Serializable privacy-ledger snapshot."""

    rho_max: float = Field(gt=0.0)
    spent_by_key: dict[str, float] = Field(default_factory=dict)


class PrivacyBudgetLedger:
    """In-memory zCDP rho ledger with a persistence-friendly snapshot."""

    def __init__(
        self,
        *,
        rho_max: float = 1.0,
        spent_by_key: dict[str, float] | None = None,
    ) -> None:
        if rho_max <= 0.0:
            raise ValueError("rho_max must be positive")
        self.rho_max = rho_max
        self._spent_by_key = dict(spent_by_key or {})

    def spent(self, requester: RequesterKey) -> float:
        return self._spent_by_key.get(requester.stable_key, 0.0)

    def remaining(self, requester: RequesterKey) -> float:
        return max(self.rho_max - self.spent(requester), 0.0)

    def debit(self, requester: RequesterKey, rho: float) -> BudgetDebit:
        if rho < 0.0:
            raise ValueError("rho must be non-negative")

        current = self.spent(requester)
        if current + rho > self.rho_max:
            return BudgetDebit(
                allowed=False,
                requester_key=requester,
                rho_requested=rho,
                rho_spent=current,
                rho_remaining=max(self.rho_max - current, 0.0),
                refusal_reason="budget_exhausted",
            )

        updated = current + rho
        self._spent_by_key[requester.stable_key] = updated
        return BudgetDebit(
            allowed=True,
            requester_key=requester,
            rho_requested=rho,
            rho_spent=updated,
            rho_remaining=max(self.rho_max - updated, 0.0),
        )

    def to_snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(rho_max=self.rho_max, spent_by_key=self._spent_by_key)

    @classmethod
    def from_snapshot(cls, snapshot: BudgetSnapshot) -> PrivacyBudgetLedger:
        return cls(rho_max=snapshot.rho_max, spent_by_key=snapshot.spent_by_key)
