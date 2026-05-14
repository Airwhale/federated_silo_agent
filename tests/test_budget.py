from __future__ import annotations

import math

from backend.silos.budget import BudgetSnapshot, PrivacyBudgetLedger, RequesterKey
from shared.enums import BankId


def requester(
    investigator: str = "investigator-alpha",
    requesting_bank: BankId = BankId.BANK_ALPHA,
    responding_bank: BankId = BankId.BANK_BETA,
) -> RequesterKey:
    return RequesterKey(
        requesting_investigator_id=investigator,
        requesting_bank_id=requesting_bank,
        responding_bank_id=responding_bank,
    )


def test_budget_debits_compose_in_rho_and_refuse_after_cap() -> None:
    ledger = PrivacyBudgetLedger(rho_max=0.05)
    key = requester()

    first = ledger.debit(key, 0.02)
    second = ledger.debit(key, 0.03)
    refused = ledger.debit(key, 0.001)

    assert first.allowed
    assert second.allowed
    assert second.rho_spent == 0.05
    assert refused.allowed is False
    assert refused.refusal_reason == "budget_exhausted"
    assert refused.rho_spent == 0.05


def test_budget_keys_are_isolated_by_requesting_and_responding_bank() -> None:
    ledger = PrivacyBudgetLedger(rho_max=0.05)
    alpha_to_beta = requester(responding_bank=BankId.BANK_BETA)
    alpha_to_gamma = requester(responding_bank=BankId.BANK_GAMMA)
    beta_to_alpha = requester(requesting_bank=BankId.BANK_BETA, responding_bank=BankId.BANK_ALPHA)

    assert ledger.debit(alpha_to_beta, 0.05).allowed
    assert ledger.debit(alpha_to_beta, 0.001).allowed is False

    assert ledger.debit(alpha_to_gamma, 0.05).allowed
    assert ledger.debit(beta_to_alpha, 0.05).allowed


def test_budget_snapshot_round_trips() -> None:
    ledger = PrivacyBudgetLedger(rho_max=0.1)
    key = requester()
    ledger.debit(key, 0.04)

    snapshot = BudgetSnapshot.model_validate_json(ledger.to_snapshot().model_dump_json())
    restored = PrivacyBudgetLedger.from_snapshot(snapshot)

    assert restored.rho_max == 0.1
    assert restored.spent(key) == 0.04
    assert math.isclose(restored.remaining(key), 0.06)


def test_stable_key_resists_adversarial_delimiter_collisions() -> None:
    """An investigator id containing the `|` separator must not collide.

    Without length-prefixed components, an adversarial investigator id of
    `"investigator|bank_alpha"` querying `bank_beta` would produce the same
    naive joined key as investigator `"investigator"` at a fabricated bank
    `"bank_alpha|bank_beta"`. Length-prefixing the components prevents this.
    """
    adversarial = RequesterKey(
        requesting_investigator_id="investigator|bank_alpha",
        requesting_bank_id=BankId.BANK_GAMMA,
        responding_bank_id=BankId.BANK_BETA,
    )
    benign = RequesterKey(
        requesting_investigator_id="investigator",
        requesting_bank_id=BankId.BANK_ALPHA,
        responding_bank_id=BankId.BANK_BETA,
    )

    assert adversarial.stable_key != benign.stable_key

    # Concrete budget-isolation check: debiting the adversarial key must not
    # touch the benign key's allowance, and vice versa.
    ledger = PrivacyBudgetLedger(rho_max=0.05)
    assert ledger.debit(adversarial, 0.04).allowed
    assert ledger.spent(benign) == 0.0
    assert ledger.debit(benign, 0.05).allowed
    assert ledger.spent(adversarial) == 0.04
