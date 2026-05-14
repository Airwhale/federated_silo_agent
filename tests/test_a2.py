from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.agents import (
    A2InvestigatorAgent,
    ConstraintViolation,
    InMemoryAuditEmitter,
    InvalidAgentInput,
    LLMClient,
)
from backend.agents.a2_states import (
    A2InboundQueryInput,
    A2PeerResponseInput,
    A2TurnInput,
    CorrelatedAlertSummary,
    QueryDraft,
    SynthesisDecision,
    TriageDecision,
)
from backend.runtime import AgentRuntimeContext, LLMClientConfig, TrustDomain
from shared.enums import (
    AgentRole,
    AuditEventKind,
    BankId,
    PrivacyUnit,
    QueryShape,
    ResponseValueKind,
    SignalType,
    TypologyCode,
)
from shared.messages import (
    AggregateActivityPayload,
    Alert,
    CounterpartyLinkagePayload,
    EvidenceItem,
    IntResponseValue,
    PrimitiveCallRecord,
    PurposeDeclaration,
    Sec314bQuery,
    Sec314bResponse,
)


HASH_A = "a" * 16
HASH_B = "b" * 16
ARGS_HASH = "c" * 64
LOCAL_ACCOUNT_HASH = "d" * 64


def runtime() -> AgentRuntimeContext:
    return AgentRuntimeContext(
        run_id="run-a2-test",
        node_id="bank-alpha-node",
        trust_domain=TrustDomain.INVESTIGATOR,
        llm=LLMClientConfig(
            base_url="http://bank-alpha.local:8080/v1/chat/completions",
            default_model="stub-model",
            stub_mode=True,
            node_id="bank-alpha-node",
        ),
    )


def agent_with_responses(
    *responses: object,
) -> tuple[A2InvestigatorAgent, LLMClient, InMemoryAuditEmitter]:
    ctx = runtime()
    audit = InMemoryAuditEmitter()
    llm = LLMClient(ctx.llm, stub_responses=responses)
    agent = A2InvestigatorAgent(
        bank_id=BankId.BANK_ALPHA,
        runtime=ctx,
        investigator_id="investigator-alpha-1",
        llm=llm,
        audit=audit,
    )
    return agent, llm, audit


def alert(
    *,
    signal_type: SignalType = SignalType.STRUCTURING,
    entity_hash: str = HASH_A,
    created_at: datetime | None = None,
) -> Alert:
    return Alert(
        sender_agent_id="bank_alpha.A1",
        sender_role=AgentRole.A1,
        sender_bank_id=BankId.BANK_ALPHA,
        recipient_agent_id="bank_alpha.A2",
        created_at=created_at or datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
        transaction_id="bank_alpha_txn_001",
        account_id="bank_alpha_acct_001",
        signal_type=signal_type,
        severity=0.92,
        rationale="Local monitoring found repeated sub-threshold activity.",
        evidence=[
            EvidenceItem(
                summary="Hashed entity shows repeated local monitoring alerts.",
                entity_hashes=[entity_hash],
                account_hashes=[LOCAL_ACCOUNT_HASH],
                counterparty_hashes=[HASH_B],
            )
        ],
    )


def query(alert_obj: Alert | None = None) -> Sec314bQuery:
    source_alert = alert_obj or alert()
    return Sec314bQuery(
        sender_agent_id="bank_alpha.A2",
        sender_role=AgentRole.A2,
        sender_bank_id=BankId.BANK_ALPHA,
        recipient_agent_id="federation.F1",
        requesting_investigator_id="investigator-alpha-1",
        requesting_bank_id=BankId.BANK_ALPHA,
        query_shape=QueryShape.AGGREGATE_ACTIVITY,
        query_payload=AggregateActivityPayload(
            name_hashes=[HASH_A],
            window_start=datetime(2026, 4, 13, tzinfo=UTC).date(),
            window_end=datetime(2026, 5, 13, tzinfo=UTC).date(),
            metrics=["alert_count"],
        ),
        purpose_declaration=PurposeDeclaration(
            typology_code=TypologyCode.STRUCTURING,
            suspicion_rationale="Repeated local alerts justify peer-bank corroboration.",
            supporting_alert_ids=[source_alert.alert_id],
        ),
        requested_rho_per_primitive=0.02,
    )


def primitive_record(field_name: str = "alert_count") -> PrimitiveCallRecord:
    return PrimitiveCallRecord(
        field_name=field_name,
        primitive_name="alert_count_for_entity",
        args_hash=ARGS_HASH,
        privacy_unit=PrivacyUnit.TRANSACTION,
        rho_debited=0.02,
        eps_delta_display=(0.5, 0.000001),
        sigma_applied=5.0,
        sensitivity=1.0,
        returned_value_kind=ResponseValueKind.INT,
    )


def peer_response(
    source_query: Sec314bQuery,
    *,
    corroborating: bool,
) -> Sec314bResponse:
    fields = {"alert_count": IntResponseValue(int=3)} if corroborating else {}
    provenance = [primitive_record()] if corroborating else []
    return Sec314bResponse(
        sender_agent_id="federation.F1",
        sender_role=AgentRole.F1,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="bank_alpha.A2",
        in_reply_to=source_query.query_id,
        responding_bank_id=BankId.BANK_BETA,
        fields=fields,
        provenance=provenance,
        rho_debited_total=0.02 if corroborating else 0.0,
    )


def test_outbound_query_from_s1_style_alert() -> None:
    triage = TriageDecision(
        action="escalate_cross_bank",
        reason="Repeated local structuring signal merits peer corroboration.",
    )
    draft = QueryDraft(
        query_shape=QueryShape.AGGREGATE_ACTIVITY,
        typology_code=TypologyCode.STRUCTURING,
        suspicion_rationale="Repeated local structuring signal merits peer review.",
        name_hashes=[HASH_A],
        metrics=["alert_count"],
        requested_rho_per_primitive=0.02,
    )
    agent, llm, _audit = agent_with_responses(triage, draft)

    result = agent.run(agent.build_alert_input(alert()))

    assert llm.call_count == 2
    assert result.action == "query"
    assert result.query is not None
    assert result.query.recipient_agent_id == "federation.F1"
    assert result.query.purpose_declaration.typology_code == TypologyCode.STRUCTURING
    assert result.query.target_bank_ids == [BankId.BANK_BETA, BankId.BANK_GAMMA]
    assert "Acme Holdings LLC" not in result.query.purpose_declaration.suspicion_rationale


def test_counterparty_linkage_draft_uses_counterparty_hashes() -> None:
    triage = TriageDecision(
        action="escalate_cross_bank",
        reason="Counterparty evidence merits peer corroboration.",
    )
    draft = QueryDraft(
        query_shape=QueryShape.COUNTERPARTY_LINKAGE,
        typology_code=TypologyCode.LAYERING,
        suspicion_rationale="Known counterparty token merits peer linkage review.",
        counterparty_hashes=[HASH_B],
        requested_rho_per_primitive=0.02,
    )
    agent, llm, _audit = agent_with_responses(triage, draft)

    result = agent.run(agent.build_alert_input(alert()))

    assert llm.call_count == 2
    assert result.action == "query"
    assert result.query is not None
    assert isinstance(result.query.query_payload, CounterpartyLinkagePayload)
    assert result.query.query_payload.counterparty_hashes == [HASH_B]


def test_query_draft_hash_fields_must_match_query_shape() -> None:
    with pytest.raises(ValidationError, match="counterparty_linkage requires"):
        QueryDraft(
            query_shape=QueryShape.COUNTERPARTY_LINKAGE,
            typology_code=TypologyCode.LAYERING,
            suspicion_rationale="Invalid draft uses entity hashes for linkage.",
            name_hashes=[HASH_A],
            requested_rho_per_primitive=0.02,
        )

    with pytest.raises(ValidationError, match="must not include counterparty_hashes"):
        QueryDraft(
            query_shape=QueryShape.AGGREGATE_ACTIVITY,
            typology_code=TypologyCode.STRUCTURING,
            suspicion_rationale="Invalid draft mixes hash fields.",
            name_hashes=[HASH_A],
            counterparty_hashes=[HASH_B],
            metrics=["alert_count"],
            requested_rho_per_primitive=0.02,
        )


def test_peer_response_with_corroboration_emits_sar_contribution() -> None:
    alert_obj = alert()
    original_query = query(alert_obj)
    response = peer_response(original_query, corroborating=True)
    agent, llm, _audit = agent_with_responses(
        SynthesisDecision(
            action="sar_contribution",
            rationale="Peer-bank alert count corroborates the local structuring alert.",
        )
    )

    result = agent.run(
        A2TurnInput(
            payload=A2PeerResponseInput(
                alert=alert_obj,
                original_query=original_query,
                response=response,
                investigator_id="investigator-alpha-1",
            )
        )
    )

    assert llm.call_count == 1
    assert result.action == "sar_contribution"
    assert result.sar_contribution is not None
    assert result.sar_contribution.recipient_agent_id == "federation.F4"
    assert result.sar_contribution.related_query_ids == [original_query.query_id]


def test_empty_peer_response_emits_dismissal_without_llm() -> None:
    alert_obj = alert()
    original_query = query(alert_obj)
    response = peer_response(original_query, corroborating=False)
    agent, llm, _audit = agent_with_responses()

    result = agent.run(
        A2TurnInput(
            payload=A2PeerResponseInput(
                alert=alert_obj,
                original_query=original_query,
                response=response,
                investigator_id="investigator-alpha-1",
            )
        )
    )

    assert llm.call_count == 0
    assert result.action == "dismiss"
    assert result.dismissal is not None
    assert result.dismissal.recipient_agent_id == "federation.F5"


def test_correlated_alert_bypass_dedupes_hashes_within_one_summary() -> None:
    """A single summary mentioning the same hash twice still counts as one alert.

    The A2-B1 threshold is `>= 3 correlated alerts on the same name_hash within
    30 days`. The correlated-alert counter dedupes entity_hashes within each
    summary so duplicate entries inside one summary cannot prematurely
    trigger the bypass. We send TWO summaries each repeating HASH_A multiple
    times — that's still only 2 correlated alerts (plus the current one = 3
    total), which is exactly at the threshold but verifying we don't see
    e.g. 7+ from naive counting.

    Without dedup, summary 1 (`[HASH_A, HASH_A, HASH_A]`) would contribute 3
    increments and summary 2 (`[HASH_A, HASH_A]`) another 2, giving count=6.
    With dedup, each summary contributes exactly 1, giving count=3. The
    bypass should fire AT threshold (3) with the dedup logic, NOT
    over-aggressively (>=2) with the naive count.
    """
    alert_obj = alert()
    prior_time = alert_obj.created_at - timedelta(days=3)
    one_only = [
        CorrelatedAlertSummary(
            alert_id=uuid4(),
            entity_hashes=[HASH_A, HASH_A, HASH_A],
            signal_type=SignalType.STRUCTURING.value,
            created_at=prior_time,
        ),
    ]
    agent, llm, _audit = agent_with_responses(
        TriageDecision(action="dismiss", reason="Not enough corroboration."),
    )

    # One summary with duplicates → count=2 (initial 1 + this summary's 1).
    # Below threshold 3, so bypass must NOT fire and we go through the LLM.
    result = agent.run(
        agent.build_alert_input(alert_obj, correlated_alerts=one_only)
    )
    assert llm.call_count == 1, "single summary with duplicates must NOT trigger A2-B1"
    assert result.bypass_rule_id is None
    assert result.action == "dismiss"


def test_correlated_alert_bypass_emits_query_without_llm() -> None:
    alert_obj = alert()
    prior_time = alert_obj.created_at - timedelta(days=3)
    correlated = [
        CorrelatedAlertSummary(
            alert_id=uuid4(),
            entity_hashes=[HASH_A],
            signal_type=SignalType.STRUCTURING.value,
            created_at=prior_time,
        ),
        CorrelatedAlertSummary(
            alert_id=uuid4(),
            entity_hashes=[HASH_A],
            signal_type=SignalType.RAPID_MOVEMENT.value,
            created_at=prior_time,
        ),
    ]
    agent, llm, audit = agent_with_responses()

    result = agent.run(agent.build_alert_input(alert_obj, correlated_alerts=correlated))

    assert llm.call_count == 0
    assert result.action == "query"
    assert result.bypass_rule_id == "A2-B1"
    assert result.query is not None
    assert [event.kind for event in audit.events] == [
        AuditEventKind.BYPASS_TRIGGERED,
        AuditEventKind.MESSAGE_SENT,
    ]


def test_future_correlated_alerts_do_not_trigger_bypass() -> None:
    alert_obj = alert()
    future_time = alert_obj.created_at + timedelta(days=3)
    correlated = [
        CorrelatedAlertSummary(
            alert_id=uuid4(),
            entity_hashes=[HASH_A],
            signal_type=SignalType.STRUCTURING.value,
            created_at=future_time,
        ),
        CorrelatedAlertSummary(
            alert_id=uuid4(),
            entity_hashes=[HASH_A],
            signal_type=SignalType.RAPID_MOVEMENT.value,
            created_at=future_time,
        ),
    ]
    agent, llm, _audit = agent_with_responses(
        TriageDecision(action="dismiss", reason="Future summaries are ignored.")
    )

    result = agent.run(agent.build_alert_input(alert_obj, correlated_alerts=correlated))

    assert llm.call_count == 1
    assert result.action == "dismiss"


def test_inbound_peer_query_is_rejected_before_llm() -> None:
    agent, llm, audit = agent_with_responses()

    result = agent.run(A2TurnInput(payload=A2InboundQueryInput(query=query())))

    assert llm.call_count == 0
    assert result.action == "rejected"
    assert result.rejection_reason is not None
    assert audit.events[0].kind == AuditEventKind.CONSTRAINT_VIOLATION
    assert audit.events[0].status == "blocked"


def test_sanctions_alert_bypass_emits_sar_contribution_without_llm() -> None:
    agent, llm, _audit = agent_with_responses()

    result = agent.run(
        agent.build_alert_input(alert(signal_type=SignalType.SANCTIONS_MATCH))
    )

    assert llm.call_count == 0
    assert result.action == "sar_contribution"
    assert result.bypass_rule_id == "A2-B2"
    assert result.sar_contribution is not None
    assert result.sar_contribution.recipient_agent_id == "federation.F4"


def test_hallucinated_query_hash_triggers_retry_then_blocks() -> None:
    """LLM-proposed name_hashes must come from the alert's evidence.

    If the LLM drafts a query referencing an entity hash the alert has no
    evidence for, A2 emits a CONSTRAINT_VIOLATION audit event and retries
    once. A persistent violation raises ConstraintViolation rather than
    sending peer banks a query about an entity A2 cannot justify.
    """
    triage = TriageDecision(
        action="escalate_cross_bank",
        reason="Repeated local signal merits peer corroboration.",
    )
    hallucinated_hash = "f" * 16
    bad_draft = QueryDraft(
        query_shape=QueryShape.AGGREGATE_ACTIVITY,
        typology_code=TypologyCode.STRUCTURING,
        suspicion_rationale="Drafted query targets an invented entity hash.",
        name_hashes=[hallucinated_hash],
        metrics=["alert_count"],
        requested_rho_per_primitive=0.02,
    )
    agent, llm, audit = agent_with_responses(triage, bad_draft, bad_draft)

    with pytest.raises(ConstraintViolation, match="not present in the alert"):
        agent.run(agent.build_alert_input(alert()))

    # triage call + first bad draft + retry that also hallucinated.
    assert llm.call_count == 3
    constraint_events = [
        event
        for event in audit.events
        if event.kind == AuditEventKind.CONSTRAINT_VIOLATION
        and event.rule_name == "query_draft_hashes_in_alert"
    ]
    assert [event.status for event in constraint_events] == ["retry", "blocked"]
    assert all("name_hashes" in str(event.detail) for event in constraint_events)


def test_hallucinated_counterparty_hash_triggers_retry_then_blocks() -> None:
    """Counterparty-linkage drafts must use counterparty evidence tokens."""
    triage = TriageDecision(
        action="escalate_cross_bank",
        reason="Counterparty evidence merits peer corroboration.",
    )
    hallucinated_hash = "e" * 16
    bad_draft = QueryDraft(
        query_shape=QueryShape.COUNTERPARTY_LINKAGE,
        typology_code=TypologyCode.LAYERING,
        suspicion_rationale="Drafted query targets an invented counterparty hash.",
        counterparty_hashes=[hallucinated_hash],
        requested_rho_per_primitive=0.02,
    )
    agent, llm, audit = agent_with_responses(triage, bad_draft, bad_draft)

    with pytest.raises(ConstraintViolation, match="not present in the alert"):
        agent.run(agent.build_alert_input(alert()))

    assert llm.call_count == 3
    constraint_events = [
        event
        for event in audit.events
        if event.kind == AuditEventKind.CONSTRAINT_VIOLATION
        and event.rule_name == "query_draft_hashes_in_alert"
    ]
    assert [event.status for event in constraint_events] == ["retry", "blocked"]
    assert all(
        "counterparty_hashes" in str(event.detail) for event in constraint_events
    )


def test_response_in_reply_to_mismatch_is_rejected() -> None:
    """A2 must reject peer responses misbound to a different query.

    An orchestrator bug could pair a Sec314bResponse with the wrong
    original_query. A2 enforces response.in_reply_to == original.query_id
    structurally; the mismatch raises InvalidAgentInput before any
    synthesis call.
    """
    alert_obj = alert()
    original_query = query(alert_obj)
    foreign_query = query()  # a different query with a different query_id
    response = peer_response(foreign_query, corroborating=True)
    agent, llm, _audit = agent_with_responses()

    with pytest.raises(InvalidAgentInput, match="in_reply_to"):
        agent.run(
            A2TurnInput(
                payload=A2PeerResponseInput(
                    alert=alert_obj,
                    original_query=original_query,
                    response=response,
                    investigator_id="investigator-alpha-1",
                )
            )
        )
    assert llm.call_count == 0


def test_peer_response_original_query_must_belong_to_this_a2() -> None:
    alert_obj = alert()
    original_query = query(alert_obj)
    bad_query = original_query.model_copy(update={"sender_agent_id": "bank_beta.A2"})
    response = peer_response(bad_query, corroborating=True)
    agent, llm, _audit = agent_with_responses()

    with pytest.raises(InvalidAgentInput, match="sender_agent_id"):
        agent.run(
            A2TurnInput(
                payload=A2PeerResponseInput(
                    alert=alert_obj,
                    original_query=bad_query,
                    response=response,
                    investigator_id="investigator-alpha-1",
                )
            )
        )
    assert llm.call_count == 0


def test_peer_response_original_query_must_support_local_alert() -> None:
    alert_obj = alert()
    foreign_alert = alert(entity_hash=HASH_B)
    bad_query = query(foreign_alert)
    response = peer_response(bad_query, corroborating=True)
    agent, llm, _audit = agent_with_responses()

    with pytest.raises(InvalidAgentInput, match="supporting_alert_ids"):
        agent.run(
            A2TurnInput(
                payload=A2PeerResponseInput(
                    alert=alert_obj,
                    original_query=bad_query,
                    response=response,
                    investigator_id="investigator-alpha-1",
                )
            )
        )
    assert llm.call_count == 0


def test_customer_name_in_query_draft_is_rejected_at_validation() -> None:
    """QueryDraft.suspicion_rationale must not leak demo customer names.

    The downstream PurposeDeclaration already rejects customer-name strings;
    the QueryDraft mirror catches the violation at the LLM-output boundary
    so the failure surfaces through the retry path rather than crashing
    later during Sec314bQuery construction.
    """
    with pytest.raises(ValidationError, match="suspicion_rationale"):
        QueryDraft(
            query_shape=QueryShape.AGGREGATE_ACTIVITY,
            typology_code=TypologyCode.STRUCTURING,
            suspicion_rationale=(
                "Acme Holdings LLC has repeated near-CTR activity; leaking a "
                "demo customer name in the LLM draft."
            ),
            name_hashes=[HASH_A],
            metrics=["alert_count"],
            requested_rho_per_primitive=0.02,
        )


def test_malformed_triage_output_gets_repaired() -> None:
    agent, llm, audit = agent_with_responses(
        "not-json",
        TriageDecision(action="dismiss", reason="Insufficient evidence."),
    )

    result = agent.run(agent.build_alert_input(alert()))

    assert result.action == "dismiss"
    assert llm.call_count == 2
    assert audit.events[0].kind == AuditEventKind.CONSTRAINT_VIOLATION
    assert audit.events[0].status == "retry"
