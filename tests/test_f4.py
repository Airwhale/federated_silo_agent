from __future__ import annotations

from uuid import uuid4

import pytest

from backend.agents import (
    ConstraintViolation,
    F4SARDrafterAgent,
    InMemoryAuditEmitter,
    LLMClient,
)
from backend.runtime import AgentRuntimeContext, LLMClientConfig, TrustDomain
from shared.enums import (
    AgentRole,
    AuditEventKind,
    BankId,
    PatternClass,
    SARPriority,
    TypologyCode,
)
from shared.messages import (
    EvidenceItem,
    GraphPatternResponse,
    SARAssemblyRequest,
    SARContribution,
    SARContributionRequest,
    SARDraft,
    SanctionsCheckResponse,
    SanctionsResult,
)


PEP_HASH = "9ca42fcf00e1dea0"
HASH_A = "aaaaaaaaaaaaaaaa"
HASH_B = "bbbbbbbbbbbbbbbb"
GOOD_NARRATIVE = (
    "Under Section 314(b), bank_alpha, bank_beta, and bank_gamma shared "
    "hash-only evidence for structuring_ring on 9ca42fcf00e1dea0, "
    "aaaaaaaaaaaaaaaa, and bbbbbbbbbbbbbbbb. F2 confidence was 0.91; F3 "
    "flagged 9ca42fcf00e1dea0 for PEP relation. The facts support a "
    "structuring SAR draft without raw customer data."
)


def runtime() -> AgentRuntimeContext:
    return AgentRuntimeContext(
        node_id="federation-test",
        trust_domain=TrustDomain.FEDERATION,
        llm=LLMClientConfig(
            stub_mode=True,
            default_model="gemini-2.5-pro",
            node_id="federation-test",
        ),
    )


def agent_with_responses(
    *responses: object,
) -> tuple[F4SARDrafterAgent, LLMClient, InMemoryAuditEmitter]:
    ctx = runtime()
    llm = LLMClient(ctx.llm, stub_responses=responses)
    audit = InMemoryAuditEmitter()
    return F4SARDrafterAgent(runtime=ctx, llm=llm, audit=audit), llm, audit


def contribution(
    *,
    bank_id: BankId,
    investigator_id: str,
    entity_hashes: list[str],
    amount_range: tuple[int, int] | None,
    query_id,
) -> SARContribution:
    return SARContribution(
        sender_agent_id=f"{bank_id.value}.A2",
        sender_role=AgentRole.A2,
        sender_bank_id=bank_id,
        recipient_agent_id="federation.F4",
        contributing_bank_id=bank_id,
        contributing_investigator_id=investigator_id,
        contributed_evidence=[
            EvidenceItem(
                summary=f"{bank_id.value} hash-only evidence supports SAR drafting.",
                entity_hashes=entity_hashes,
            )
        ],
        suspicious_amount_range=amount_range,
        local_rationale=f"{bank_id.value} observed hash-only corroborating activity.",
        related_query_ids=[query_id],
    )


def graph_pattern() -> GraphPatternResponse:
    return GraphPatternResponse(
        sender_agent_id="federation.F2",
        sender_role=AgentRole.F2,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="federation.F1",
        pattern_class=PatternClass.STRUCTURING_RING,
        confidence=0.91,
        suspect_entity_hashes=[PEP_HASH, HASH_A, HASH_B],
        narrative="Cross-bank aggregate pattern is consistent with structuring.",
    )


def sanctions_response() -> SanctionsCheckResponse:
    return SanctionsCheckResponse(
        sender_agent_id="federation.F3",
        sender_role=AgentRole.F3,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="federation.F1",
        in_reply_to=uuid4(),
        results={
            PEP_HASH: SanctionsResult(sdn_match=False, pep_relation=True),
            HASH_A: SanctionsResult(sdn_match=False, pep_relation=False),
        },
    )


def assembly_request(
    *,
    include_amounts: bool = True,
    include_graph: bool = True,
    include_sanctions: bool = True,
) -> SARAssemblyRequest:
    query_alpha = uuid4()
    query_beta = uuid4()
    query_gamma = uuid4()
    return SARAssemblyRequest(
        sender_agent_id="federation.F1",
        sender_role=AgentRole.F1,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="federation.F4",
        filing_bank_id=BankId.BANK_ALPHA,
        contributions=[
            contribution(
                bank_id=BankId.BANK_ALPHA,
                investigator_id="investigator-alpha-1",
                entity_hashes=[PEP_HASH],
                amount_range=(10_000_000, 25_000_000) if include_amounts else None,
                query_id=query_alpha,
            ),
            contribution(
                bank_id=BankId.BANK_BETA,
                investigator_id="investigator-beta-1",
                entity_hashes=[HASH_A],
                amount_range=(20_000_000, 79_500_000) if include_amounts else None,
                query_id=query_beta,
            ),
            contribution(
                bank_id=BankId.BANK_GAMMA,
                investigator_id="investigator-gamma-1",
                entity_hashes=[HASH_B],
                amount_range=(15_000_000, 60_000_000) if include_amounts else None,
                query_id=query_gamma,
            ),
        ],
        graph_pattern=graph_pattern() if include_graph else None,
        sanctions=sanctions_response() if include_sanctions else None,
        related_query_ids=[query_alpha, query_beta, query_gamma],
    )


def test_complete_s1_style_input_emits_sar_draft_with_deterministic_fields() -> None:
    agent, llm, audit = agent_with_responses({"narrative": GOOD_NARRATIVE})
    request = assembly_request()

    result = agent.run(request)

    assert isinstance(result, SARDraft)
    assert result.sender_agent_id == "federation.F4"
    assert result.recipient_agent_id == "federation.F1"
    assert result.filing_institution == "bank_alpha"
    assert result.suspicious_amount_range == (10_000_000, 79_500_000)
    assert result.typology_code == TypologyCode.STRUCTURING
    assert result.sar_priority == SARPriority.HIGH
    assert result.mandatory_fields_complete is True
    assert len(result.contributors) == 3
    assert {item.bank_id for item in result.contributors} == {
        BankId.BANK_ALPHA,
        BankId.BANK_BETA,
        BankId.BANK_GAMMA,
    }
    assert result.related_query_ids == request.related_query_ids
    assert "Section 314(b)" in result.narrative
    for bank_id in ("bank_alpha", "bank_beta", "bank_gamma"):
        assert bank_id in result.narrative
    for hash_value in (PEP_HASH, HASH_A, HASH_B):
        assert hash_value in result.narrative

    assert llm.call_count == 1
    assert llm.requests[0].response_format["json_schema"]["name"] == "F4NarrativeDraft"
    assert any(event.kind == AuditEventKind.MESSAGE_SENT for event in audit.events)


def test_missing_amount_range_emits_contribution_request_without_llm_call() -> None:
    agent, llm, audit = agent_with_responses()
    request = assembly_request(include_amounts=False)

    result = agent.run(request)

    assert isinstance(result, SARContributionRequest)
    assert result.sender_agent_id == "federation.F4"
    assert result.recipient_agent_id == "federation.F1"
    assert result.in_reply_to == request.case_id
    assert result.requested_bank_id == BankId.BANK_ALPHA
    assert result.missing_fields == ["suspicious_amount_range"]
    assert "suspicious_amount_range" in result.request_reason
    assert llm.call_count == 0
    assert audit.events[-1].model_name == "deterministic_mandatory_gate"


def test_missing_graph_pattern_emits_contribution_request_without_llm_call() -> None:
    agent, llm, _audit = agent_with_responses()
    request = assembly_request(include_graph=False)

    result = agent.run(request)

    assert isinstance(result, SARContributionRequest)
    assert result.missing_fields == ["graph_pattern"]
    assert llm.call_count == 0


def test_without_sanctions_or_pep_evidence_priority_is_standard() -> None:
    agent, _llm, _audit = agent_with_responses({"narrative": GOOD_NARRATIVE})
    request = assembly_request(include_sanctions=False)

    result = agent.run(request)

    assert isinstance(result, SARDraft)
    assert result.sar_priority == SARPriority.STANDARD


def test_customer_name_in_narrative_is_rejected_and_repaired() -> None:
    unsafe_narrative = (
        "Under Section 314(b), bank_alpha, bank_beta, and bank_gamma shared "
        "hash-only evidence for 9ca42fcf00e1dea0, aaaaaaaaaaaaaaaa, and "
        "bbbbbbbbbbbbbbbb involving Jane Doe. F2 confidence was 0.91."
    )
    agent, llm, audit = agent_with_responses(
        {"narrative": unsafe_narrative},
        {"narrative": GOOD_NARRATIVE},
    )
    request = assembly_request()

    result = agent.run(request)

    assert isinstance(result, SARDraft)
    assert "Jane Doe" not in result.narrative
    assert llm.call_count == 2
    assert any(
        event.kind == AuditEventKind.CONSTRAINT_VIOLATION
        and event.phase == "narrative"
        and event.status == "retry"
        for event in audit.events
    )


def test_unrepaired_narrative_violation_blocks() -> None:
    agent, llm, audit = agent_with_responses(
        {"narrative": "bank_alpha only."},
        {"narrative": "bank_alpha only."},
    )
    request = assembly_request()

    with pytest.raises(ConstraintViolation):
        agent.run(request)

    assert llm.call_count == 2
    assert any(
        event.kind == AuditEventKind.CONSTRAINT_VIOLATION
        and event.status == "blocked"
        and event.rule_name == "F4-C1"
        for event in audit.events
    )
