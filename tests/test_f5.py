from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backend.agents import F5ComplianceAuditorAgent, InMemoryAuditEmitter
from backend.agents.f5_compliance_auditor import (
    BUDGET_PRESSURE_FINDING,
    DISMISSAL_REVIEW_FINDING,
    F5AuditConfig,
    MISSING_LT_VERDICT_FINDING,
    PURPOSE_REVIEW_FINDING,
    RATE_LIMIT_FINDING,
    ROUTE_ANOMALY_FINDING,
)
from backend.runtime.context import AgentRuntimeContext, LLMClientConfig, TrustDomain
from shared.enums import (
    AgentRole,
    AuditEventKind,
    AuditReviewScope,
    BankId,
    MessageType,
    PolicySeverity,
)
from shared.messages import (
    AuditEvent,
    AuditReviewRequest,
    BudgetExhaustedPayload,
    ConstraintViolationPayload,
    DismissalRationale,
    LtVerdictPayload,
    MessageSentPayload,
    RhoDebitedPayload,
)


BASE_TIME = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)


def agent(
    config: F5AuditConfig | None = None,
) -> tuple[F5ComplianceAuditorAgent, InMemoryAuditEmitter]:
    audit = InMemoryAuditEmitter()
    runtime = AgentRuntimeContext(
        run_id="f5-test-run",
        node_id="federation-node",
        trust_domain=TrustDomain.FEDERATION,
        llm=LLMClientConfig(stub_mode=True),
    )
    return (
        F5ComplianceAuditorAgent(runtime=runtime, config=config, audit=audit),
        audit,
    )


def request(
    events: list[AuditEvent],
    *,
    review_scope: AuditReviewScope = AuditReviewScope.INVESTIGATION,
    dismissals: list[DismissalRationale] | None = None,
) -> AuditReviewRequest:
    return AuditReviewRequest(
        sender_agent_id="federation.F1",
        sender_role=AgentRole.F1,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="federation.F5",
        review_scope=review_scope,
        audit_events=events,
        dismissals=dismissals or [],
        related_query_ids=[uuid4()],
    )


def message_event(
    *,
    message_type: str = MessageType.SEC314B_QUERY.value,
    source_agent_id: str = "bank_alpha.A2",
    destination_agent_id: str = "federation.F1",
    created_at: datetime = BASE_TIME,
) -> AuditEvent:
    return AuditEvent(
        sender_agent_id="federation.orchestrator",
        sender_role=AgentRole.ORCHESTRATOR,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="audit",
        created_at=created_at,
        kind=AuditEventKind.MESSAGE_SENT,
        actor_agent_id=source_agent_id,
        payload=MessageSentPayload(
            message_type=message_type,
            source_agent_id=source_agent_id,
            destination_agent_id=destination_agent_id,
        ),
    )


def lt_allow_event(event: AuditEvent, *, created_at: datetime | None = None) -> AuditEvent:
    return AuditEvent(
        sender_agent_id="federation.F6",
        sender_role=AgentRole.F6,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="audit",
        created_at=created_at or event.created_at + timedelta(milliseconds=1),
        kind=AuditEventKind.LT_VERDICT,
        actor_agent_id="federation.F6",
        payload=LtVerdictPayload(verdict="allow", request_id=str(event.event_id)),
    )


def budget_exhausted_event() -> AuditEvent:
    return AuditEvent(
        sender_agent_id="bank_beta.A3",
        sender_role=AgentRole.A3,
        sender_bank_id=BankId.BANK_BETA,
        recipient_agent_id="audit",
        created_at=BASE_TIME,
        kind=AuditEventKind.BUDGET_EXHAUSTED,
        actor_agent_id="bank_beta.A3",
        payload=BudgetExhaustedPayload(
            requester_key="bank_alpha.A2:bank_beta",
            bank_id=BankId.BANK_BETA,
            rho_requested=0.25,
            rho_remaining=0.0,
        ),
    )


def rho_debited_event(*, rho_remaining: float = 5.0) -> AuditEvent:
    return AuditEvent(
        sender_agent_id="bank_beta.A3",
        sender_role=AgentRole.A3,
        sender_bank_id=BankId.BANK_BETA,
        recipient_agent_id="audit",
        created_at=BASE_TIME,
        kind=AuditEventKind.RHO_DEBITED,
        actor_agent_id="bank_beta.A3",
        payload=RhoDebitedPayload(
            requester_key="bank_alpha.A2:bank_beta",
            bank_id=BankId.BANK_BETA,
            rho_debited=0.1,
            rho_remaining=rho_remaining,
        ),
    )


def constraint_event(violation: str) -> AuditEvent:
    return AuditEvent(
        sender_agent_id="bank_beta.A3",
        sender_role=AgentRole.A3,
        sender_bank_id=BankId.BANK_BETA,
        recipient_agent_id="audit",
        created_at=BASE_TIME,
        kind=AuditEventKind.CONSTRAINT_VIOLATION,
        actor_agent_id="bank_beta.A3",
        payload=ConstraintViolationPayload(violation=violation),
    )


def test_f5_rate_limit_triggers_on_sixth_query_by_default() -> None:
    f5, audit = agent()
    query_events = [
        message_event(created_at=BASE_TIME + timedelta(seconds=offset * 5))
        for offset in range(6)
    ]
    events = [item for event in query_events for item in (event, lt_allow_event(event))]

    result = f5.run(request(events, review_scope=AuditReviewScope.RATE_LIMIT))

    rate_findings = [
        finding for finding in result.findings if finding.kind == RATE_LIMIT_FINDING
    ]
    assert result.rate_limit_triggered is True
    assert result.human_review_required is True
    assert len(rate_findings) == 1
    assert rate_findings[0].related_event_ids == [event.event_id for event in query_events]
    assert any(event.kind == AuditEventKind.RATE_LIMIT for event in audit.events)


def test_f5_sustained_rate_limit_burst_emits_one_actionable_finding() -> None:
    f5, _ = agent()
    query_events = [
        message_event(created_at=BASE_TIME + timedelta(seconds=offset * 5))
        for offset in range(7)
    ]
    events = [item for event in query_events for item in (event, lt_allow_event(event))]

    result = f5.run(request(events, review_scope=AuditReviewScope.RATE_LIMIT))

    rate_findings = [
        finding for finding in result.findings if finding.kind == RATE_LIMIT_FINDING
    ]
    assert len(rate_findings) == 1
    assert rate_findings[0].related_event_ids == [
        event.event_id for event in query_events
    ]


def test_f5_rate_limit_threshold_is_configurable() -> None:
    f5, _ = agent(config=F5AuditConfig(max_queries=2, window_seconds=30))
    query_events = [
        message_event(created_at=BASE_TIME + timedelta(seconds=offset * 10))
        for offset in range(3)
    ]
    events = [item for event in query_events for item in (event, lt_allow_event(event))]

    result = f5.run(request(events, review_scope=AuditReviewScope.RATE_LIMIT))

    assert result.rate_limit_triggered is True
    assert result.findings[0].kind == RATE_LIMIT_FINDING
    assert len(result.findings[0].related_event_ids) == 3


def test_f5_reports_multiple_distinct_rate_limit_bursts() -> None:
    f5, _ = agent()
    first_burst = [
        message_event(created_at=BASE_TIME + timedelta(seconds=offset * 5))
        for offset in range(6)
    ]
    second_burst = [
        message_event(created_at=BASE_TIME + timedelta(seconds=120 + offset * 5))
        for offset in range(6)
    ]
    query_events = [*first_burst, *second_burst]
    events = [item for event in query_events for item in (event, lt_allow_event(event))]

    result = f5.run(request(events, review_scope=AuditReviewScope.RATE_LIMIT))

    rate_findings = [
        finding for finding in result.findings if finding.kind == RATE_LIMIT_FINDING
    ]
    assert len(rate_findings) == 2
    assert rate_findings[0].related_event_ids == [event.event_id for event in first_burst]
    assert rate_findings[1].related_event_ids == [event.event_id for event in second_burst]


def test_f5_budget_exhaustion_flags_budget_pressure() -> None:
    f5, _ = agent()

    result = f5.run(request([budget_exhausted_event()]))

    assert result.human_review_required is True
    assert [finding.kind for finding in result.findings] == [BUDGET_PRESSURE_FINDING]


def test_f5_reports_budget_exhaustion_and_low_remaining_budget() -> None:
    f5, _ = agent()

    result = f5.run(request([budget_exhausted_event(), rho_debited_event(rho_remaining=0.01)]))

    assert [finding.kind for finding in result.findings] == [
        BUDGET_PRESSURE_FINDING,
        BUDGET_PRESSURE_FINDING,
    ]
    assert [finding.severity for finding in result.findings] == [
        PolicySeverity.HIGH,
        PolicySeverity.MEDIUM,
    ]


def test_f5_missing_lobster_trap_verdict_requires_review() -> None:
    f5, _ = agent()
    event = message_event()

    result = f5.run(request([event]))

    assert result.human_review_required is True
    assert [finding.kind for finding in result.findings] == [MISSING_LT_VERDICT_FINDING]
    assert result.findings[0].related_event_ids == [event.event_id]


def test_f5_route_and_purpose_anomalies_require_review() -> None:
    f5, _ = agent()

    result = f5.run(
        request(
            [
                constraint_event("route_violation: recipient does not match approval"),
                constraint_event("invalid_purpose: suspicion rationale is blank"),
            ]
        )
    )

    finding_kinds = {finding.kind for finding in result.findings}
    assert result.human_review_required is True
    assert ROUTE_ANOMALY_FINDING in finding_kinds
    assert PURPOSE_REVIEW_FINDING in finding_kinds


def test_f5_constraint_event_is_classified_once_by_primary_anomaly() -> None:
    f5, _ = agent()

    result = f5.run(
        request([constraint_event("unauthorized purpose route mismatch")])
    )

    assert [finding.kind for finding in result.findings] == [ROUTE_ANOMALY_FINDING]


def test_f5_clean_canonical_audit_window_has_no_findings() -> None:
    f5, audit = agent()
    query = message_event()
    response = message_event(
        message_type=MessageType.SEC314B_RESPONSE.value,
        source_agent_id="bank_beta.A3",
        destination_agent_id="federation.F1",
        created_at=BASE_TIME + timedelta(seconds=5),
    )
    federation_internal = message_event(
        message_type=MessageType.SAR_ASSEMBLY_REQUEST.value,
        source_agent_id="federation.F1",
        destination_agent_id="federation.F4",
        created_at=BASE_TIME + timedelta(seconds=10),
    )
    events = [
        query,
        lt_allow_event(query),
        response,
        lt_allow_event(response),
        federation_internal,
        rho_debited_event(rho_remaining=5.0),
    ]

    result = f5.run(request(events))

    assert result.findings == []
    assert result.human_review_required is False
    assert result.rate_limit_triggered is False
    assert [event.kind for event in audit.events] == [AuditEventKind.MESSAGE_SENT]


def test_f5_vague_dismissal_finding_links_to_dismissal_message() -> None:
    f5, _ = agent()
    dismissal = DismissalRationale(
        sender_agent_id="bank_alpha.A2",
        sender_role=AgentRole.A2,
        sender_bank_id=BankId.BANK_ALPHA,
        recipient_agent_id="federation.F5",
        alert_id=uuid4(),
        reason="ok",
    )

    result = f5.run(
        request([rho_debited_event(rho_remaining=5.0)], dismissals=[dismissal])
    )

    assert result.human_review_required is True
    assert result.findings[0].kind == DISMISSAL_REVIEW_FINDING
    assert result.findings[0].related_event_ids == [dismissal.message_id]
    assert str(dismissal.alert_id) in result.findings[0].detail


def test_f5_dismissal_word_threshold_is_configurable() -> None:
    f5, _ = agent(config=F5AuditConfig(min_dismissal_words=6))
    dismissal = DismissalRationale(
        sender_agent_id="bank_alpha.A2",
        sender_role=AgentRole.A2,
        sender_bank_id=BankId.BANK_ALPHA,
        recipient_agent_id="federation.F5",
        alert_id=uuid4(),
        reason="reviewed local alert evidence",
    )

    result = f5.run(
        request([rho_debited_event(rho_remaining=5.0)], dismissals=[dismissal])
    )

    assert result.human_review_required is True
    assert result.findings[0].kind == DISMISSAL_REVIEW_FINDING
