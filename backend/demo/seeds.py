"""Deterministic seed values for the canonical S1 AML demo flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from backend.agents.a1_models import SignalCandidate
from shared.enums import BankId
from shared.identifiers import hash_identifier


CANONICAL_SESSION_ID = UUID("c634d027-2eb5-4c38-b3f8-580b52e99b24")
CANONICAL_RUN_LABEL = "s1_structuring_ring"
CANONICAL_WINDOW_START = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
CANONICAL_WINDOW_END = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
CANONICAL_ALERT_TRANSACTION_ID = "bank_alpha_s1_d_velocity_seed"
CANONICAL_ALERT_ACCOUNT_ID = "bank_alpha_s1_d_account_seed"
CANONICAL_INVESTIGATOR_ID = "bank_alpha.investigator"

S1_ENTITY_HASHES: tuple[str, ...] = (
    "9fbb6bce24886bd4",
    "588902ae2f263d9b",
    "c0dd241488d3203e",
    "9ca42fcf00e1dea0",
    "b85cb85f296db01c",
)
S1_PEP_ENTITY_HASH = "9ca42fcf00e1dea0"


@dataclass(frozen=True)
class CanonicalBankContributionSeed:
    """Fixture-level SAR contribution facts for a bank in the S1 scenario."""

    bank_id: BankId
    investigator_id: str
    entity_hashes: tuple[str, ...]
    suspicious_amount_range: tuple[int, int]
    rationale: str


S1_CONTRIBUTIONS: tuple[CanonicalBankContributionSeed, ...] = (
    CanonicalBankContributionSeed(
        bank_id=BankId.BANK_ALPHA,
        investigator_id="bank_alpha.investigator",
        entity_hashes=(S1_ENTITY_HASHES[0], S1_PEP_ENTITY_HASH, S1_ENTITY_HASHES[2]),
        suspicious_amount_range=(9_100_00, 9_900_00),
        rationale=(
            "bank_alpha observed repeated hash-only sub-CTR activity tied to "
            "the S1 structuring ring."
        ),
    ),
    CanonicalBankContributionSeed(
        bank_id=BankId.BANK_BETA,
        investigator_id="bank_beta.investigator",
        entity_hashes=(S1_ENTITY_HASHES[0], S1_ENTITY_HASHES[1], S1_PEP_ENTITY_HASH),
        suspicious_amount_range=(9_000_00, 9_850_00),
        rationale=(
            "bank_beta observed matching hash-only repeated sub-CTR activity "
            "over the same ring tokens."
        ),
    ),
    CanonicalBankContributionSeed(
        bank_id=BankId.BANK_GAMMA,
        investigator_id="bank_gamma.investigator",
        entity_hashes=(S1_ENTITY_HASHES[1], S1_ENTITY_HASHES[2], S1_ENTITY_HASHES[4]),
        suspicious_amount_range=(9_200_00, 9_950_00),
        rationale=(
            "bank_gamma observed hash-only counterpart activity completing the "
            "cross-bank structuring ring."
        ),
    ),
)

F4_STUB_NARRATIVE = (
    "Under Section 314(b), bank_alpha, bank_beta, and bank_gamma shared "
    "hash-only evidence for structuring_ring on 9fbb6bce24886bd4, "
    "588902ae2f263d9b, c0dd241488d3203e, 9ca42fcf00e1dea0, and "
    "b85cb85f296db01c. F2 confidence was high; F3 flagged "
    "9ca42fcf00e1dea0 for PEP relation. The facts support a structuring "
    "SAR draft without raw customer data."
)


def canonical_signal_candidate() -> SignalCandidate:
    """Return the fixed A1 candidate that starts the canonical S1 run."""
    return SignalCandidate(
        signal_id="canonical_s1_bank_alpha_velocity",
        transaction_id=CANONICAL_ALERT_TRANSACTION_ID,
        amount=9_650.0,
        transaction_type="debit",
        channel="cash",
        timestamp=CANONICAL_WINDOW_END,
        account_id=CANONICAL_ALERT_ACCOUNT_ID,
        account_id_hash=hash_identifier(CANONICAL_ALERT_ACCOUNT_ID),
        customer_name_hash=S1_PEP_ENTITY_HASH,
        customer_kyc_tier="commercial",
        transaction_id_hash=hash_identifier(CANONICAL_ALERT_TRANSACTION_ID),
        recent_near_ctr_count_24h=10,
        counterparty_account_id_hashed=S1_ENTITY_HASHES[0],
        source_signal_type="canonical_s1_velocity_spike",
        source_severity=0.97,
    )
