from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from shared.enums import (
    AgentRole,
    AuditEventKind,
    AuditReviewScope,
    BankId,
    MessageType,
    PolicyContentChannel,
    PolicyDecision,
    PolicySeverity,
)
from shared.messages import (
    AgentMessage,
    AuditEvent,
    AuditReviewRequest,
    AuditReviewResult,
    ComplianceFinding,
    EvidenceItem,
    MessageSentPayload,
    PolicyEvaluationRequest,
    PolicyEvaluationResult,
    PolicyRuleHit,
    SARAssemblyRequest,
    SARContribution,
    SARContributionRequest,
)


HASH_A = "a" * 16
ARGS_HASH = "b" * 64


def header(
    *,
    sender_agent_id: str,
    sender_role: AgentRole,
    sender_bank_id: BankId,
    recipient_agent_id: str,
) -> dict[str, object]:
    return {
        "sender_agent_id": sender_agent_id,
        "sender_role": sender_role,
        "sender_bank_id": sender_bank_id,
        "recipient_agent_id": recipient_agent_id,
    }


def policy_request() -> PolicyEvaluationRequest:
    return PolicyEvaluationRequest(
        **header(
            sender_agent_id="bank_alpha.A2",
            sender_role=AgentRole.A2,
            sender_bank_id=BankId.BANK_ALPHA,
            recipient_agent_id="bank_alpha.F6",
        ),
        evaluated_message_type=MessageType.SEC314B_QUERY,
        evaluated_sender_agent_id="bank_alpha.A2",
        evaluated_sender_role=AgentRole.A2,
        evaluated_sender_bank_id=BankId.BANK_ALPHA,
        content_channel=PolicyContentChannel.STRUCTURED_MESSAGE,
        content_hash=ARGS_HASH,
        content_summary="Hash-only Section 314(b) query for policy evaluation.",
        declared_purpose="Investigate suspected structuring activity.",
    )


def policy_result(*, decision: PolicyDecision = PolicyDecision.BLOCK) -> PolicyEvaluationResult:
    rule_hits = []
    if decision != PolicyDecision.ALLOW:
        rule_hits = [
            PolicyRuleHit(
                rule_id="F6-B1",
                decision=decision,
                severity=PolicySeverity.HIGH,
                detail="Policy detected an unsupported cross-boundary disclosure.",
                redacted_fields=["content_summary"] if decision == PolicyDecision.REDACT else [],
            )
        ]
    return PolicyEvaluationResult(
        **header(
            sender_agent_id="bank_alpha.F6",
            sender_role=AgentRole.F6,
            sender_bank_id=BankId.BANK_ALPHA,
            recipient_agent_id="bank_alpha.A2",
        ),
        in_reply_to=policy_request().message_id,
        decision=decision,
        rule_hits=rule_hits,
        safe_output_summary="Policy verdict contains no raw customer identifiers.",
        redacted_field_count=1 if decision == PolicyDecision.REDACT else 0,
    )


def sar_contribution() -> SARContribution:
    return SARContribution(
        **header(
            sender_agent_id="bank_alpha.A2",
            sender_role=AgentRole.A2,
            sender_bank_id=BankId.BANK_ALPHA,
            recipient_agent_id="federation.F4",
        ),
        contributing_bank_id=BankId.BANK_ALPHA,
        contributing_investigator_id="investigator-alpha-1",
        contributed_evidence=[
            EvidenceItem(
                summary="Hash-only local evidence supports escalation.",
                entity_hashes=[HASH_A],
            )
        ],
        local_rationale="Local alert and peer-bank corroboration support SAR drafting.",
        related_query_ids=[uuid4()],
    )


def audit_event() -> AuditEvent:
    return AuditEvent(
        **header(
            sender_agent_id="federation.orchestrator",
            sender_role=AgentRole.ORCHESTRATOR,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="audit",
        ),
        kind=AuditEventKind.MESSAGE_SENT,
        actor_agent_id="federation.F1",
        payload=MessageSentPayload(
            message_type=MessageType.SEC314B_QUERY.value,
            source_agent_id="bank_alpha.A2",
            destination_agent_id="federation.F1",
        ),
    )


def audit_review_request() -> AuditReviewRequest:
    return AuditReviewRequest(
        **header(
            sender_agent_id="federation.F1",
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="federation.F5",
        ),
        review_scope=AuditReviewScope.INVESTIGATION,
        audit_events=[audit_event()],
        related_query_ids=[uuid4()],
    )


def audit_review_result(*, flagged: bool = True) -> AuditReviewResult:
    findings = []
    if flagged:
        findings = [
            ComplianceFinding(
                kind="purpose_review",
                severity=PolicySeverity.MEDIUM,
                detail="Purpose declaration should receive human review.",
                related_event_ids=[audit_event().event_id],
            )
        ]
    return AuditReviewResult(
        **header(
            sender_agent_id="federation.F5",
            sender_role=AgentRole.F5,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="federation.F1",
        ),
        in_reply_to=audit_review_request().message_id,
        review_scope=AuditReviewScope.INVESTIGATION,
        findings=findings,
        human_review_required=flagged,
    )


def contract_models() -> list[BaseModel]:
    assembly = SARAssemblyRequest(
        **header(
            sender_agent_id="federation.F1",
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="federation.F4",
        ),
        filing_bank_id=BankId.BANK_ALPHA,
        contributions=[sar_contribution()],
        policy_evaluations=[policy_result(decision=PolicyDecision.ALLOW)],
        related_query_ids=[uuid4()],
    )
    contribution_request = SARContributionRequest(
        **header(
            sender_agent_id="federation.F4",
            sender_role=AgentRole.F4,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="federation.F1",
        ),
        in_reply_to=assembly.case_id,
        requested_bank_id=BankId.BANK_ALPHA,
        missing_fields=["filing_institution"],
        request_reason="F4 needs the filing institution before completing the draft.",
        related_query_ids=assembly.related_query_ids,
    )
    return [
        policy_request(),
        policy_result(),
        sar_contribution(),
        assembly,
        contribution_request,
        audit_review_request(),
        audit_review_result(),
    ]


@pytest.mark.parametrize("model", contract_models(), ids=lambda model: type(model).__name__)
def test_short_contract_models_round_trip_and_parse_as_agent_message(model: BaseModel) -> None:
    parsed = type(model).model_validate_json(model.model_dump_json())
    union_parsed = TypeAdapter(AgentMessage).validate_json(model.model_dump_json())

    assert parsed == model
    assert type(union_parsed) is type(model)


def test_policy_request_must_target_policy_instance() -> None:
    with pytest.raises(ValidationError, match="F6"):
        PolicyEvaluationRequest(
            **header(
                sender_agent_id="bank_alpha.A2",
                sender_role=AgentRole.A2,
                sender_bank_id=BankId.BANK_ALPHA,
                recipient_agent_id="bank_alpha.A2",
            ),
            evaluated_sender_agent_id="bank_alpha.A2",
            evaluated_sender_role=AgentRole.A2,
            evaluated_sender_bank_id=BankId.BANK_ALPHA,
            content_channel=PolicyContentChannel.STRUCTURED_MESSAGE,
            content_hash=ARGS_HASH,
            content_summary="Mismatched policy target.",
        )


def test_policy_result_non_allow_requires_rule_hit() -> None:
    with pytest.raises(ValidationError, match="rule_hit"):
        PolicyEvaluationResult(
            **header(
                sender_agent_id="bank_alpha.F6",
                sender_role=AgentRole.F6,
                sender_bank_id=BankId.BANK_ALPHA,
                recipient_agent_id="bank_alpha.A2",
            ),
            in_reply_to=uuid4(),
            decision=PolicyDecision.BLOCK,
        )


def test_policy_result_non_redact_cannot_report_redacted_fields() -> None:
    with pytest.raises(ValidationError, match="redacted_field_count"):
        PolicyEvaluationResult(
            **header(
                sender_agent_id="bank_alpha.F6",
                sender_role=AgentRole.F6,
                sender_bank_id=BankId.BANK_ALPHA,
                recipient_agent_id="bank_alpha.A2",
            ),
            in_reply_to=uuid4(),
            decision=PolicyDecision.BLOCK,
            rule_hits=[
                PolicyRuleHit(
                    rule_id="F6-B1",
                    decision=PolicyDecision.BLOCK,
                    severity=PolicySeverity.HIGH,
                    detail="Policy blocked unsafe content.",
                )
            ],
            redacted_field_count=1,
        )


def test_policy_result_redact_count_must_match_rule_hit_fields() -> None:
    valid = policy_result(decision=PolicyDecision.REDACT)
    assert valid.redacted_field_count == 1
    assert valid.rule_hits[0].redacted_fields == ["content_summary"]

    with pytest.raises(ValidationError, match="redacted_field_count"):
        PolicyEvaluationResult(
            **header(
                sender_agent_id="bank_alpha.F6",
                sender_role=AgentRole.F6,
                sender_bank_id=BankId.BANK_ALPHA,
                recipient_agent_id="bank_alpha.A2",
            ),
            in_reply_to=uuid4(),
            decision=PolicyDecision.REDACT,
            rule_hits=[
                PolicyRuleHit(
                    rule_id="F6-B1",
                    decision=PolicyDecision.REDACT,
                    severity=PolicySeverity.HIGH,
                    detail="Policy redacted unsafe content.",
                    redacted_fields=["content_summary"],
                )
            ],
            redacted_field_count=2,
        )


def test_policy_result_decision_must_match_strongest_rule_hit() -> None:
    with pytest.raises(ValidationError, match="strongest"):
        PolicyEvaluationResult(
            **header(
                sender_agent_id="bank_alpha.F6",
                sender_role=AgentRole.F6,
                sender_bank_id=BankId.BANK_ALPHA,
                recipient_agent_id="bank_alpha.A2",
            ),
            in_reply_to=uuid4(),
            decision=PolicyDecision.ESCALATE,
            rule_hits=[
                PolicyRuleHit(
                    rule_id="F6-B1",
                    decision=PolicyDecision.BLOCK,
                    severity=PolicySeverity.HIGH,
                    detail="Policy must block this content.",
                )
            ],
        )


def test_sar_assembly_request_must_target_f4() -> None:
    with pytest.raises(ValidationError, match="federation.F4"):
        SARAssemblyRequest(
            **header(
                sender_agent_id="federation.F1",
                sender_role=AgentRole.F1,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="federation.F5",
            ),
            filing_bank_id=BankId.BANK_ALPHA,
            contributions=[sar_contribution()],
        )


def test_sar_contribution_request_must_return_through_f1() -> None:
    with pytest.raises(ValidationError, match="federation.F1"):
        SARContributionRequest(
            **header(
                sender_agent_id="federation.F4",
                sender_role=AgentRole.F4,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="bank_alpha.A2",
            ),
            in_reply_to=uuid4(),
            requested_bank_id=BankId.BANK_ALPHA,
            missing_fields=["filing_institution"],
            request_reason="F4 needs routing through F1 for missing SAR input.",
        )


def test_audit_review_result_flags_require_findings() -> None:
    with pytest.raises(ValidationError, match="finding"):
        AuditReviewResult(
            **header(
                sender_agent_id="federation.F5",
                sender_role=AgentRole.F5,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="federation.F1",
            ),
            in_reply_to=uuid4(),
            review_scope=AuditReviewScope.FULL_RUN,
            human_review_required=True,
        )


def test_audit_review_result_must_be_sent_by_f5() -> None:
    with pytest.raises(ValidationError, match="F5"):
        AuditReviewResult(
            **header(
                sender_agent_id="federation.F1",
                sender_role=AgentRole.F1,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="federation.F5",
            ),
            in_reply_to=uuid4(),
            review_scope=AuditReviewScope.FULL_RUN,
        )


def test_audit_review_result_high_severity_requires_human_review() -> None:
    with pytest.raises(ValidationError, match="human_review_required"):
        AuditReviewResult(
            **header(
                sender_agent_id="federation.F5",
                sender_role=AgentRole.F5,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="federation.F1",
            ),
            in_reply_to=uuid4(),
            review_scope=AuditReviewScope.INVESTIGATION,
            findings=[
                ComplianceFinding(
                    kind="critical_policy_gap",
                    severity=PolicySeverity.CRITICAL,
                    detail="Critical policy issue requires human review.",
                )
            ],
            human_review_required=False,
        )


def test_audit_review_rate_limit_flag_requires_rate_limit_finding() -> None:
    with pytest.raises(ValidationError, match="rate_limit"):
        AuditReviewResult(
            **header(
                sender_agent_id="federation.F5",
                sender_role=AgentRole.F5,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="federation.F1",
            ),
            in_reply_to=uuid4(),
            review_scope=AuditReviewScope.RATE_LIMIT,
            findings=[
                ComplianceFinding(
                    kind="purpose_review",
                    severity=PolicySeverity.MEDIUM,
                    detail="Finding exists but does not justify rate-limit flag.",
                )
            ],
            rate_limit_triggered=True,
        )
