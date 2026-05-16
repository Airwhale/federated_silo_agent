from __future__ import annotations

import hashlib
from datetime import date

import numpy as np
import pytest

from backend.agents import F2GraphAnalysisAgent, InMemoryAuditEmitter, LLMClient
from backend.agents.base import ConstraintViolation, InvalidAgentInput
from backend.runtime import AgentRuntimeContext, LLMClientConfig, TrustDomain
from shared.enums import AgentRole, AuditEventKind, BankId, PatternClass
from shared.messages import BankAggregate, GraphPatternRequest


S1_HASHES = [f"f2{s:014x}" for s in range(1, 6)]
S3_HASHES = [f"f3{s:014x}" for s in range(1, 5)]


def runtime() -> AgentRuntimeContext:
    return AgentRuntimeContext(
        run_id="run-f2-test",
        node_id="federation-node",
        trust_domain=TrustDomain.FEDERATION,
        llm=LLMClientConfig(
            base_url="http://federation.local:8080/v1/chat/completions",
            default_model="stub-model",
            stub_mode=True,
            node_id="federation-node",
        ),
    )


def agent_with_audit(
    *,
    stub_responses: list[dict[str, object]] | None = None,
) -> tuple[F2GraphAnalysisAgent, LLMClient, InMemoryAuditEmitter]:
    ctx = runtime()
    audit = InMemoryAuditEmitter()
    llm = LLMClient(ctx.llm, stub_responses=stub_responses)
    agent = F2GraphAnalysisAgent(runtime=ctx, llm=llm, audit=audit)
    return agent, llm, audit


def graph_request(
    aggregates: list[BankAggregate],
    *,
    sender_role: AgentRole = AgentRole.F1,
    recipient_agent_id: str = "federation.F2",
) -> GraphPatternRequest:
    sender_bank_id = BankId.FEDERATION if sender_role == AgentRole.F1 else BankId.BANK_ALPHA
    sender_agent_id = "federation.F1" if sender_role == AgentRole.F1 else "bank_alpha.A2"
    return GraphPatternRequest(
        sender_agent_id=sender_agent_id,
        sender_role=sender_role,
        sender_bank_id=sender_bank_id,
        recipient_agent_id=recipient_agent_id,
        pattern_aggregates=aggregates,
        window_start=date(2026, 5, 1),
        window_end=date(2026, 5, 13),
    )


def aggregate(
    bank_id: BankId,
    *,
    edges: list[int],
    flow: list[int],
    hashes: list[str],
) -> BankAggregate:
    return BankAggregate(
        bank_id=bank_id,
        edge_count_distribution=edges,
        bucketed_flow_histogram=flow,
        candidate_entity_hashes=hashes,
        rho_debited=0.04,
    )


def s1_ring_aggregates() -> list[BankAggregate]:
    return [
        aggregate(
            BankId.BANK_ALPHA,
            edges=[1, 2, 2, 5],
            flow=[0, 3, 42, 3, 0],
            hashes=S1_HASHES[:4],
        ),
        aggregate(
            BankId.BANK_BETA,
            edges=[1, 2, 3, 6],
            flow=[0, 2, 48, 4, 0],
            hashes=[*S1_HASHES[:2], *S1_HASHES[3:]],
        ),
        aggregate(
            BankId.BANK_GAMMA,
            edges=[1, 1, 2, 4],
            flow=[0, 3, 39, 2, 0],
            hashes=S1_HASHES[1:],
        ),
    ]


def s3_layering_aggregates() -> list[BankAggregate]:
    return [
        aggregate(
            BankId.BANK_ALPHA,
            edges=[2, 2, 1, 0],
            flow=[0, 0, 0, 2, 14],
            hashes=S3_HASHES[:2],
        ),
        aggregate(
            BankId.BANK_BETA,
            edges=[1, 2, 2, 0],
            flow=[0, 0, 1, 2, 16],
            hashes=S3_HASHES[1:3],
        ),
        aggregate(
            BankId.BANK_GAMMA,
            edges=[1, 1, 2, 0],
            flow=[0, 0, 0, 3, 13],
            hashes=S3_HASHES[2:],
        ),
    ]


def noise_aggregates(seed: int) -> list[BankAggregate]:
    rng = np.random.default_rng(seed)
    noised: list[BankAggregate] = []
    for original in s1_ring_aggregates():
        noised.append(
            aggregate(
                original.bank_id,
                edges=[
                    max(0, int(round(value + rng.normal(0.0, 1.2))))
                    for value in original.edge_count_distribution
                ],
                flow=[
                    max(0, int(round(value + rng.normal(0.0, 2.0))))
                    for value in original.bucketed_flow_histogram
                ],
                hashes=original.candidate_entity_hashes,
            )
        )
    return noised


def test_f2_detects_s1_structuring_ring_with_hash_only_output() -> None:
    agent, llm, audit = agent_with_audit()

    response = agent.run(graph_request(s1_ring_aggregates()))

    assert response.pattern_class == PatternClass.STRUCTURING_RING
    assert response.confidence >= 0.85
    assert set(response.suspect_entity_hashes) == set(S1_HASHES)
    assert response.recipient_agent_id == "federation.F1"
    assert "DP-noised" in response.narrative
    assert "Acme Holdings" not in response.model_dump_json()
    assert llm.requests == []
    assert any(
        event.kind == AuditEventKind.BYPASS_TRIGGERED and event.rule_name == "F2-B1"
        for event in audit.events
    )


def test_f2_detects_s3_layering_chain() -> None:
    agent, llm, audit = agent_with_audit()

    response = agent.run(graph_request(s3_layering_aggregates()))

    assert response.pattern_class == PatternClass.LAYERING_CHAIN
    assert response.confidence >= 0.85
    assert set(response.suspect_entity_hashes) == set(S3_HASHES)
    assert llm.requests == []
    assert any(
        event.kind == AuditEventKind.BYPASS_TRIGGERED and event.rule_name == "F2-B2"
        for event in audit.events
    )


def test_f2_returns_none_for_noise_without_candidate_graph() -> None:
    agent, llm, audit = agent_with_audit()
    noise = [
        aggregate(BankId.BANK_ALPHA, edges=[1, 0, 0, 0], flow=[4, 2, 1, 0, 0], hashes=[]),
        aggregate(BankId.BANK_BETA, edges=[0, 0, 0, 0], flow=[2, 1, 1, 0, 0], hashes=[]),
    ]

    response = agent.run(graph_request(noise))

    assert response.pattern_class == PatternClass.NONE
    assert response.confidence < 0.4
    assert response.suspect_entity_hashes == []
    assert llm.requests == []
    assert any(
        event.kind == AuditEventKind.BYPASS_TRIGGERED and event.rule_name == "F2-B0"
        for event in audit.events
    )


def test_f2_structuring_ring_survives_dp_noise_draws() -> None:
    detections = 0

    for seed in range(50):
        agent, _llm, _audit = agent_with_audit()
        response = agent.run(graph_request(noise_aggregates(seed)))
        if (
            response.pattern_class == PatternClass.STRUCTURING_RING
            and response.confidence >= 0.85
        ):
            detections += 1

    assert detections >= 45


def test_f2_ambiguous_case_uses_llm_classifier() -> None:
    stub_response = {
        "pattern_class": "structuring_ring",
        "confidence": 0.62,
        "suspect_entity_hashes": S1_HASHES[:3],
        "narrative": "DP-noised aggregates show a moderate repeated-flow graph over hash tokens.",
    }
    agent, llm, _audit = agent_with_audit(stub_responses=[stub_response])
    ambiguous = [
        aggregate(
            BankId.BANK_ALPHA,
            edges=[3, 2, 1, 1],
            flow=[0, 1, 7, 4, 3],
            hashes=S1_HASHES[:3],
        ),
        aggregate(
            BankId.BANK_BETA,
            edges=[2, 2, 1, 0],
            flow=[0, 1, 6, 3, 3],
            hashes=S1_HASHES[:3],
        ),
    ]

    response = agent.run(graph_request(ambiguous))

    assert response.pattern_class == PatternClass.STRUCTURING_RING
    assert response.confidence == 0.62
    assert response.suspect_entity_hashes == S1_HASHES[:3]
    assert len(llm.requests) == 1
    assert "candidate_entity_hashes" in llm.requests[0].messages[1].content


def test_f2_repairs_llm_hashes_outside_candidate_set() -> None:
    invalid_hash = hashlib.sha256(b"not a candidate").hexdigest()[:16]
    agent, _llm, _audit = agent_with_audit(
        stub_responses=[
            {
                "pattern_class": "structuring_ring",
                "confidence": 0.61,
                "suspect_entity_hashes": [invalid_hash],
                "narrative": "DP-noised aggregates show a possible repeated-flow graph.",
            },
            {
                "pattern_class": "none",
                "confidence": 0.2,
                "suspect_entity_hashes": [],
                "narrative": "DP-noised aggregates do not show a clear pattern.",
            },
        ]
    )
    ambiguous = [
        aggregate(
            BankId.BANK_ALPHA,
            edges=[3, 2, 1, 1],
            flow=[0, 1, 7, 4, 3],
            hashes=S1_HASHES[:3],
        ),
        aggregate(
            BankId.BANK_BETA,
            edges=[2, 2, 1, 0],
            flow=[0, 1, 6, 3, 3],
            hashes=S1_HASHES[:3],
        ),
    ]

    response = agent.run(graph_request(ambiguous))

    assert response.pattern_class == PatternClass.NONE
    assert response.suspect_entity_hashes == []


def test_f2_blocks_unrepairable_llm_hash_hallucination() -> None:
    invalid_hash = hashlib.sha256(b"not a candidate").hexdigest()[:16]
    agent, _llm, _audit = agent_with_audit(
        stub_responses=[
            {
                "pattern_class": "structuring_ring",
                "confidence": 0.61,
                "suspect_entity_hashes": [invalid_hash],
                "narrative": "DP-noised aggregates show a possible repeated-flow graph.",
            },
            {
                "pattern_class": "structuring_ring",
                "confidence": 0.61,
                "suspect_entity_hashes": [invalid_hash],
                "narrative": "DP-noised aggregates show a possible repeated-flow graph.",
            },
        ]
    )
    ambiguous = [
        aggregate(
            BankId.BANK_ALPHA,
            edges=[3, 2, 1, 1],
            flow=[0, 1, 7, 4, 3],
            hashes=S1_HASHES[:3],
        ),
        aggregate(
            BankId.BANK_BETA,
            edges=[2, 2, 1, 0],
            flow=[0, 1, 6, 3, 3],
            hashes=S1_HASHES[:3],
        ),
    ]

    with pytest.raises(ConstraintViolation, match="candidate_entity_hashes"):
        agent.run(graph_request(ambiguous))


def test_f2_rejects_wrong_recipient() -> None:
    agent, _llm, _audit = agent_with_audit()

    with pytest.raises(InvalidAgentInput, match="addressed to federation.F2"):
        agent.run(graph_request(s1_ring_aggregates(), recipient_agent_id="federation.F3"))


def test_f2_rejects_wrong_sender_role() -> None:
    agent, _llm, _audit = agent_with_audit()

    with pytest.raises(InvalidAgentInput, match="from F1"):
        agent.run(graph_request(s1_ring_aggregates(), sender_role=AgentRole.A2))


def test_f2_requires_federation_runtime() -> None:
    ctx = runtime().model_copy(update={"trust_domain": TrustDomain.BANK_SILO})

    with pytest.raises(ValueError, match="federation trust domain"):
        F2GraphAnalysisAgent(runtime=ctx)
