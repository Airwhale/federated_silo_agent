from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.agents import F3SanctionsAgent, InMemoryAuditEmitter, LLMClient
from backend.agents.base import InvalidAgentInput
from backend.runtime import AgentRuntimeContext, LLMClientConfig, TrustDomain
from shared.enums import AgentRole, AuditEventKind, BankId
from shared.messages import SanctionsCheckRequest


SDN_HASH = "661f729972ae2156"
PEP_HASH = "9ca42fcf00e1dea0"
UNKNOWN_HASH = "0" * 16
BATCH_HASHES = [
    "661f729972ae2156",
    "1b4e8f70a9c2d351",
    "2c5f9011bad3e462",
    "3d60a122cbe4f573",
    "4e71b233dcf50684",
    "5f82c344ed061795",
    "6a93d455fe1728a6",
    "7ba4e5660f2839b7",
    "8cb5f6771a394ac8",
    "9dc607882b4a5bd9",
]


def runtime() -> AgentRuntimeContext:
    return AgentRuntimeContext(
        run_id="run-f3-test",
        node_id="federation-node",
        trust_domain=TrustDomain.FEDERATION,
        llm=LLMClientConfig(
            base_url="http://federation.local:8080/v1/chat/completions",
            default_model="stub-model",
            stub_mode=True,
            node_id="federation-node",
        ),
    )


def agent_with_audit() -> tuple[F3SanctionsAgent, LLMClient, InMemoryAuditEmitter]:
    ctx = runtime()
    audit = InMemoryAuditEmitter()
    llm = LLMClient(ctx.llm)
    agent = F3SanctionsAgent(runtime=ctx, llm=llm, audit=audit)
    return agent, llm, audit


def sanctions_request(
    hashes: list[str],
    *,
    sender_role: AgentRole = AgentRole.F1,
    recipient_agent_id: str = "federation.F3",
) -> SanctionsCheckRequest:
    sender_bank_id = BankId.FEDERATION if sender_role == AgentRole.F1 else BankId.BANK_ALPHA
    sender_agent_id = "federation.F1" if sender_role == AgentRole.F1 else "bank_alpha.A2"
    return SanctionsCheckRequest(
        sender_agent_id=sender_agent_id,
        sender_role=sender_role,
        sender_bank_id=sender_bank_id,
        recipient_agent_id=recipient_agent_id,
        entity_hashes=hashes,
        requesting_context="Screen supplied hash tokens for sanctions or PEP exposure.",
    )


def test_f3_flags_planted_pep_hash() -> None:
    agent, llm, audit = agent_with_audit()

    response = agent.run(sanctions_request([PEP_HASH]))

    assert response.recipient_agent_id == "federation.F1"
    assert response.results[PEP_HASH].pep_relation is True
    assert response.results[PEP_HASH].sdn_match is False
    assert response.in_reply_to is not None
    assert llm.requests == []
    assert any(
        event.kind == AuditEventKind.BYPASS_TRIGGERED and event.rule_name == "F3-B2"
        for event in audit.events
    )


def test_f3_flags_sdn_hash_without_disclosing_list_contents() -> None:
    agent, llm, audit = agent_with_audit()

    response = agent.run(sanctions_request([SDN_HASH]))

    assert response.results[SDN_HASH].sdn_match is True
    assert response.results[SDN_HASH].pep_relation is False
    assert llm.requests == []
    serialized = response.model_dump_json()
    assert "notes" not in serialized
    assert "source" not in serialized
    assert "Fictional SDN fixture" not in serialized
    assert any(
        event.kind == AuditEventKind.BYPASS_TRIGGERED and event.rule_name == "F3-B1"
        for event in audit.events
    )


def test_f3_unknown_hash_returns_false_flags_and_does_not_retain_prior_hashes() -> None:
    agent, _llm, _audit = agent_with_audit()

    first = agent.run(sanctions_request([PEP_HASH]))
    second = agent.run(sanctions_request([UNKNOWN_HASH]))

    assert first.results[PEP_HASH].pep_relation is True
    assert second.results[UNKNOWN_HASH].sdn_match is False
    assert second.results[UNKNOWN_HASH].pep_relation is False


def test_f3_batch_returns_one_result_per_unique_input_hash() -> None:
    agent, _llm, _audit = agent_with_audit()

    response = agent.run(sanctions_request(BATCH_HASHES))

    assert set(response.results) == set(BATCH_HASHES)
    assert len(response.results) == 10
    assert all(result.sdn_match for result in response.results.values())
    assert all(not result.pep_relation for result in response.results.values())


def test_f3_accepts_a2_direct_request() -> None:
    agent, _llm, _audit = agent_with_audit()

    response = agent.run(sanctions_request([UNKNOWN_HASH], sender_role=AgentRole.A2))

    assert response.recipient_agent_id == "bank_alpha.A2"
    assert response.results[UNKNOWN_HASH].sdn_match is False


def test_f3_rejects_wrong_recipient() -> None:
    agent, _llm, _audit = agent_with_audit()

    with pytest.raises(InvalidAgentInput, match="addressed to federation.F3"):
        agent.run(sanctions_request([UNKNOWN_HASH], recipient_agent_id="federation.F4"))


def test_f3_rejects_wrong_sender_role() -> None:
    agent, _llm, _audit = agent_with_audit()

    with pytest.raises(InvalidAgentInput, match="A2 or F1"):
        agent.run(sanctions_request([UNKNOWN_HASH], sender_role=AgentRole.A3))


def test_f3_requires_federation_runtime() -> None:
    ctx = runtime().model_copy(update={"trust_domain": TrustDomain.BANK_SILO})

    with pytest.raises(ValueError, match="federation trust domain"):
        F3SanctionsAgent(runtime=ctx)


def test_f3_mixed_flag_batch_emits_both_bypass_events() -> None:
    # When a single request batches one SDN-only hash and one PEP-only
    # hash, F3 must emit both F3-B1 and F3-B2 bypass events (not collapse
    # to one) so downstream F4 / F5 see the full bypass picture, and the
    # response must carry the correct per-hash flag combination.
    agent, _llm, audit = agent_with_audit()

    response = agent.run(sanctions_request([SDN_HASH, PEP_HASH]))

    assert response.results[SDN_HASH].sdn_match is True
    assert response.results[SDN_HASH].pep_relation is False
    assert response.results[PEP_HASH].sdn_match is False
    assert response.results[PEP_HASH].pep_relation is True

    bypass_rules = {
        event.rule_name
        for event in audit.events
        if event.kind == AuditEventKind.BYPASS_TRIGGERED
    }
    assert bypass_rules == {"F3-B1", "F3-B2"}


def test_f3_duplicate_input_hashes_collapse_to_one_result() -> None:
    # ``entity_hashes`` is a list (so duplicates are admissible at the
    # schema), but ``results`` is a dict keyed by hash. A request with
    # three copies of the same hash must produce exactly one result
    # entry with the correct flags, not three -- otherwise downstream
    # consumers that iterate ``results.items()`` would double-count.
    agent, _llm, audit = agent_with_audit()

    response = agent.run(sanctions_request([SDN_HASH, SDN_HASH, SDN_HASH]))

    assert list(response.results.keys()) == [SDN_HASH]
    assert response.results[SDN_HASH].sdn_match is True
    # The single hit still produces exactly one F3-B1 bypass event, not
    # three -- F3 emits per-hit-class, not per-hash-occurrence.
    f3_b1_events = [
        event for event in audit.events
        if event.kind == AuditEventKind.BYPASS_TRIGGERED and event.rule_name == "F3-B1"
    ]
    assert len(f3_b1_events) == 1


def test_f3_request_rejects_customer_name_in_requesting_context() -> None:
    # ``SanctionsCheckRequest.requesting_context`` runs through the
    # shared ``_reject_demo_customer_names`` field validator. Any
    # planted-entity cover-business name embedded in the
    # free-text context must raise ``ValidationError`` *before* the
    # request reaches the agent, so customer-name leakage cannot land
    # in F3's audit trail via the requesting_context field.
    with pytest.raises(ValidationError):
        SanctionsCheckRequest(
            sender_agent_id="bank_alpha.A2",
            sender_role=AgentRole.A2,
            sender_bank_id=BankId.BANK_ALPHA,
            recipient_agent_id="federation.F3",
            entity_hashes=[SDN_HASH],
            # ``Acme Holdings LLC`` is one of the planted S1-ring
            # cover-business names defined in
            # data/scripts/plant_scenarios.py and listed in the
            # ``_PLANTED_ENTITY_NAMES`` regression fixture in
            # tests/test_messages.py.
            requesting_context="Acme Holdings LLC appears suspicious; please screen.",
        )
