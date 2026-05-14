from __future__ import annotations

import pytest
from typer.testing import CliRunner

from backend.agents import ConstraintViolation, InMemoryAuditEmitter, LLMClient
from backend.agents.a1_monitoring import (
    A1BatchResult,
    A1Decision,
    A1MonitoringAgent,
    app,
    build_alert,
    demo_stub_result,
    synthetic_ctr_candidate,
    synthetic_sdn_candidate,
    synthetic_velocity_candidate,
)
from backend.runtime import AgentRuntimeContext, LLMClientConfig, TrustDomain
from backend.silos.local_reader import read_signal_candidates
from shared.enums import AgentRole, AuditEventKind, BankId, SignalType
from shared.identifiers import is_cross_bank_hash_token


TEST_SDN_HASHES = frozenset({"661f729972ae2156"})


def runtime() -> AgentRuntimeContext:
    return AgentRuntimeContext(
        run_id="run-a1-test",
        node_id="bank-alpha-node",
        trust_domain=TrustDomain.BANK_SILO,
        llm=LLMClientConfig(
            base_url="http://bank-alpha.local:8080/v1/chat/completions",
            default_model="stub-model",
            stub_mode=True,
            node_id="bank-alpha-node",
        ),
    )


def agent_with_responses(
    *responses: object,
) -> tuple[A1MonitoringAgent, LLMClient, InMemoryAuditEmitter]:
    ctx = runtime()
    audit = InMemoryAuditEmitter()
    llm = LLMClient(ctx.llm, stub_responses=responses)
    agent = A1MonitoringAgent(
        bank_id=BankId.BANK_ALPHA,
        runtime=ctx,
        sdn_hashes=TEST_SDN_HASHES,
        llm=llm,
        audit=audit,
    )
    return agent, llm, audit


def suppress_result(signal_id: str) -> A1BatchResult:
    return A1BatchResult(
        decisions=[
            A1Decision(
                signal_id=signal_id,
                action="suppress",
                alert=None,
                llm_rationale="Low-severity local monitoring noise.",
            )
        ]
    )


def emit_result(agent: A1MonitoringAgent, candidate) -> A1BatchResult:
    input_data = agent.build_input([candidate])
    alert = build_alert(
        input_data=input_data,
        candidate=candidate,
        rationale="LLM triage: local signal merits investigator review.",
    )
    return A1BatchResult(
        decisions=[
            A1Decision(
                signal_id=candidate.signal_id,
                action="emit",
                alert=alert,
                llm_rationale="Source severity supports local A2 review.",
            )
        ]
    )


def test_local_reader_loads_typed_bank_alpha_candidates_with_s1_visibility() -> None:
    candidates = read_signal_candidates(BankId.BANK_ALPHA, limit=50)

    assert len(candidates) == 50
    assert candidates[0].signal_id > candidates[-1].signal_id
    assert all(candidate.amount >= 0 for candidate in candidates)
    assert all(candidate.recent_near_ctr_count_24h >= 0 for candidate in candidates)

    s1_near_ctr = [
        candidate
        for candidate in candidates
        if "_s1_" in candidate.transaction_id
        and candidate.source_signal_type == "amount_near_ctr_threshold"
    ]
    assert len(s1_near_ctr) >= 5


def test_ctr_bypass_emits_without_llm_call() -> None:
    agent, llm, audit = agent_with_responses()
    output = agent.run(agent.build_input([synthetic_ctr_candidate()]))

    assert llm.call_count == 0
    decision = output.decisions[0]
    assert decision.action == "emit"
    assert decision.bypass_rule_id == "A1-B1"
    assert decision.alert is not None
    assert decision.alert.signal_type == SignalType.CTR_REPORT
    assert decision.alert.recipient_agent_id == "bank_alpha.A2"
    assert [event.kind for event in audit.events] == [
        AuditEventKind.BYPASS_TRIGGERED,
        AuditEventKind.MESSAGE_SENT,
    ]
    assert audit.events[0].rule_name == "A1-B1"


def test_sdn_bypass_emits_without_llm_call() -> None:
    agent, llm, _audit = agent_with_responses()
    output = agent.run(agent.build_input([synthetic_sdn_candidate()]))

    assert llm.call_count == 0
    decision = output.decisions[0]
    assert decision.bypass_rule_id == "A1-B2"
    assert decision.alert is not None
    assert decision.alert.signal_type == SignalType.SANCTIONS_MATCH


def test_velocity_bypass_emits_without_llm_call() -> None:
    agent, llm, _audit = agent_with_responses()
    output = agent.run(agent.build_input([synthetic_velocity_candidate()]))

    assert llm.call_count == 0
    decision = output.decisions[0]
    assert decision.bypass_rule_id == "A1-B3"
    assert decision.alert is not None
    assert decision.alert.signal_type == SignalType.RAPID_MOVEMENT


def test_mixed_batch_bypass_is_materialized_before_llm_call() -> None:
    ctr_candidate = synthetic_ctr_candidate()
    normal_candidate = read_signal_candidates(BankId.BANK_ALPHA, limit=1)[0]
    agent, llm, audit = agent_with_responses(suppress_result(normal_candidate.signal_id))

    output = agent.run(agent.build_input([ctr_candidate, normal_candidate]))

    assert llm.call_count == 1
    assert [decision.signal_id for decision in output.decisions] == [
        ctr_candidate.signal_id,
        normal_candidate.signal_id,
    ]
    ctr_decision = output.decisions[0]
    assert ctr_decision.action == "emit"
    assert ctr_decision.bypass_rule_id == "A1-B1"
    assert ctr_decision.alert is not None
    assert ctr_decision.alert.signal_type == SignalType.CTR_REPORT
    assert output.decisions[1].action == "suppress"
    assert audit.events[0].kind == AuditEventKind.BYPASS_TRIGGERED
    assert audit.events[0].rule_name == "A1-B1"


def test_bypass_policy_constraint_rejects_suppressed_bypass_decision() -> None:
    candidate = synthetic_ctr_candidate()
    agent, _llm, _audit = agent_with_responses()
    input_data = agent.build_input([candidate])
    bad_output = A1BatchResult(
        decisions=[
            A1Decision(
                signal_id=candidate.signal_id,
                action="suppress",
                alert=None,
                llm_rationale="Incorrectly suppressed CTR threshold candidate.",
            )
        ]
    )

    violations = agent._constraint_violations(input_data, bad_output)

    assert violations[0][0].name == "bypass_decisions_match_policy"


def test_normal_candidate_path_calls_llm_stub_and_validates_alert() -> None:
    candidate = read_signal_candidates(BankId.BANK_ALPHA, limit=1)[0]
    agent, llm, _audit = agent_with_responses()
    llm.set_stub_responses([emit_result(agent, candidate)])

    output = agent.run(agent.build_input([candidate]))

    assert llm.call_count == 1
    decision = output.decisions[0]
    assert decision.action == "emit"
    assert decision.alert is not None
    assert decision.alert.sender_agent_id == "bank_alpha.A1"
    assert decision.alert.recipient_agent_id == "bank_alpha.A2"
    assert decision.alert.evidence[0].account_hashes != [candidate.account_id]
    if is_cross_bank_hash_token(candidate.counterparty_account_id_hashed):
        assert candidate.counterparty_account_id_hashed in (
            decision.alert.evidence[0].counterparty_hashes
        )
    assert decision.alert.evidence[0].transaction_hashes != [candidate.transaction_id]


def test_malformed_llm_output_gets_repaired_by_base_runtime() -> None:
    candidate = read_signal_candidates(BankId.BANK_ALPHA, limit=1)[0]
    agent, llm, audit = agent_with_responses("not-json", suppress_result(candidate.signal_id))

    output = agent.run(agent.build_input([candidate]))

    assert output.decisions[0].action == "suppress"
    assert llm.call_count == 2
    assert audit.events[0].phase == "llm_parse"
    assert audit.events[0].status == "retry"


def test_bad_alert_recipient_raises_constraint_violation_after_retry() -> None:
    candidate = read_signal_candidates(BankId.BANK_ALPHA, limit=1)[0]
    agent, llm, audit = agent_with_responses()
    input_data = agent.build_input([candidate])
    wrong_alert = build_alert(
        input_data=input_data,
        candidate=candidate,
        rationale="LLM triage: local signal merits investigator review.",
    ).model_copy(update={"recipient_agent_id": "bank_beta.A2"})
    wrong_result = A1BatchResult(
        decisions=[
            A1Decision(
                signal_id=candidate.signal_id,
                action="emit",
                alert=wrong_alert,
                llm_rationale="Incorrectly routed alert.",
            )
        ]
    )
    llm.set_stub_responses([wrong_result, wrong_result])

    with pytest.raises(ConstraintViolation):
        agent.run(input_data)

    assert llm.call_count == 2
    assert audit.events[-1].kind == AuditEventKind.CONSTRAINT_VIOLATION
    assert audit.events[-1].rule_name == "alert_routing"
    assert audit.events[-1].status == "blocked"


def test_raw_identifier_in_evidence_summary_raises_constraint_violation() -> None:
    candidate = read_signal_candidates(BankId.BANK_ALPHA, limit=1)[0]
    agent, llm, audit = agent_with_responses()
    input_data = agent.build_input([candidate])
    bad_alert = build_alert(
        input_data=input_data,
        candidate=candidate,
        rationale="LLM triage: local signal merits investigator review.",
    )
    bad_evidence = bad_alert.evidence[0].model_copy(
        update={
            "summary": f"Raw local account leaked: {candidate.account_id}",
            "entity_hashes": [candidate.customer_name_hash],
            "account_hashes": [candidate.account_id_hash],
            "transaction_hashes": [candidate.transaction_id_hash],
        }
    )
    wrong_alert = bad_alert.model_copy(update={"evidence": [bad_evidence]})
    wrong_result = A1BatchResult(
        decisions=[
            A1Decision(
                signal_id=candidate.signal_id,
                action="emit",
                alert=wrong_alert,
                llm_rationale="Incorrectly leaked a local identifier in evidence.",
            )
        ]
    )
    llm.set_stub_responses([wrong_result, wrong_result])

    with pytest.raises(ConstraintViolation):
        agent.run(input_data)

    assert llm.call_count == 2
    assert audit.events[-1].kind == AuditEventKind.CONSTRAINT_VIOLATION
    assert audit.events[-1].rule_name == "evidence_uses_hashed_identifiers"
    assert audit.events[-1].status == "blocked"


def test_full_llm_path_emits_alerts_for_planted_s1_candidates() -> None:
    """End-to-end through the LLM path: every S1-related candidate produces an Alert.

    This is the structural property A1 needs to support: the data layer's
    planted S1 ring is visible to A1 as `amount_near_ctr_threshold` signals,
    and when A1 runs through the (stubbed) LLM path with sensible triage
    logic, those S1 candidates emit Alerts addressed to local A2. The LLM
    is mocked via the deterministic `demo_stub_result`; the assertion is
    about A1's plumbing, not the model's judgment.
    """
    candidates = read_signal_candidates(BankId.BANK_ALPHA, limit=50)
    s1_candidates = [
        c
        for c in candidates
        if "_s1_" in c.transaction_id
        and c.source_signal_type == "amount_near_ctr_threshold"
    ]
    assert len(s1_candidates) >= 5, "data layer must expose >=5 S1 candidates to A1"

    agent, llm, audit = agent_with_responses()
    input_data = agent.build_input(candidates)
    llm.set_stub_responses([demo_stub_result(input_data, TEST_SDN_HASHES)])

    output = agent.run(input_data)

    # Every S1-related candidate gets exactly one decision and emits an Alert.
    s1_signal_ids = {c.signal_id for c in s1_candidates}
    s1_decisions = [d for d in output.decisions if d.signal_id in s1_signal_ids]
    assert len(s1_decisions) == len(s1_candidates)
    s1_emits = [d for d in s1_decisions if d.action == "emit"]
    assert len(s1_emits) >= 5, "at least 5 S1 candidates must emit Alerts"
    for decision in s1_emits:
        assert decision.alert is not None
        assert decision.alert.sender_agent_id == "bank_alpha.A1"
        assert decision.alert.sender_role == AgentRole.A1
        assert decision.alert.sender_bank_id == BankId.BANK_ALPHA
        assert decision.alert.recipient_agent_id == "bank_alpha.A2"
        # Defense-in-depth: evidence carries hashed identifiers, not raw IDs.
        evidence = decision.alert.evidence[0]
        for candidate in s1_candidates:
            if candidate.signal_id == decision.signal_id:
                assert candidate.account_id not in evidence.account_hashes
                if is_cross_bank_hash_token(candidate.counterparty_account_id_hashed):
                    assert candidate.counterparty_account_id_hashed in (
                        evidence.counterparty_hashes
                    )
                assert candidate.transaction_id not in evidence.transaction_hashes
                break

    # And the LLM was actually called (this is not a bypass-only path).
    assert llm.call_count == 1
    # Final audit event is MESSAGE_SENT for the LLM-path return.
    assert audit.events[-1].kind == AuditEventKind.MESSAGE_SENT


def test_demo_command_runs_in_stub_mode_and_prints_counts() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["demo", "--bank", "bank_alpha", "--limit", "10", "--stub"],
    )

    assert result.exit_code == 0, result.output
    assert "Loaded 10 suspicious signal candidates" in result.output
    assert "Injected 2 deterministic bypass examples" in result.output
    assert "Emitted" in result.output
    assert "Suppressed" in result.output
    assert "A1-B1" in result.output
