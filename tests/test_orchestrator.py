from datetime import date

from backend.orchestrator.agents import StubBankStatsPrimitives
from backend.silos.budget import RequesterKey
from shared.enums import BankId


def test_stub_pattern_aggregate_for_f2_matches_real_primitive_contract() -> None:
    primitive = StubBankStatsPrimitives(bank_id=BankId.BANK_BETA)
    requester = RequesterKey(
        requesting_investigator_id="investigator-alpha",
        requesting_bank_id=BankId.BANK_ALPHA,
        responding_bank_id=BankId.BANK_BETA,
    )
    candidate_hashes = ["0123456789abcdef", "fedcba9876543210"]

    result = primitive.pattern_aggregate_for_f2(
        window=(date(2026, 1, 1), date(2026, 1, 31)),
        requester=requester,
        candidate_entity_hashes=list(reversed(candidate_hashes)),
        rho=0.04,
    )

    assert result.refusal_reason is None
    assert result.value.candidate_entity_hashes == candidate_hashes
    assert {record.field_name for record in result.records} == {
        "edge_count_distribution",
        "bucketed_flow_histogram",
        "candidate_entity_hashes",
    }
    debited = [record for record in result.records if record.rho_debited > 0.0]
    assert debited
    assert all(record.rho_remaining == 0.96 for record in debited)
