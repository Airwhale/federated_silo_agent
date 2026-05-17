"""Convert local orchestrator artifacts into F5 audit-review messages."""

from __future__ import annotations

from typing import Iterable
from uuid import UUID, uuid5

from pydantic import Field

from shared.enums import AgentRole, AuditEventKind, AuditReviewScope, BankId, MessageType
from shared.messages import (
    AuditEvent,
    AuditReviewRequest,
    DismissalRationale,
    LtVerdictPayload,
    MessageSentPayload,
    PolicyEvaluationResult,
    PrimitiveCallRecord,
    RhoDebitedPayload,
    Sec314bResponse,
    StrictModel,
)


_AUDIT_NAMESPACE = UUID("0d804f16-99ad-4e70-9983-32eaa2e746e6")


class PolicyEvaluationRecord(StrictModel):
    """Correlate one F6 verdict to the message that triggered it."""

    turn_id: str
    message_id: UUID
    evaluated_message_type: MessageType
    evaluated_sender_agent_id: str
    evaluated_recipient_agent_id: str
    policy_result: PolicyEvaluationResult
    audit_events: list[AuditEvent] = Field(default_factory=list)


class PrimitiveAuditRecord(StrictModel):
    """Attach a primitive provenance record to the bank that spent budget."""

    bank_id: BankId
    record: PrimitiveCallRecord


def build_audit_review_request(
    *,
    sender_agent_id: str,
    policy_records: Iterable[PolicyEvaluationRecord],
    a3_responses: Iterable[Sec314bResponse],
    primitive_records: Iterable[PrimitiveAuditRecord],
    dismissals: Iterable[DismissalRationale],
    related_query_ids: list[UUID],
) -> AuditReviewRequest:
    """Build the wire-level F5 audit window for a canonical run."""
    events = [
        *_events_for_policy_records(policy_records),
        *_events_for_a3_provenance(a3_responses),
        *_events_for_primitive_records(primitive_records),
    ]
    return AuditReviewRequest(
        sender_agent_id=sender_agent_id,
        sender_role=AgentRole.F1,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="federation.F5",
        review_scope=AuditReviewScope.FULL_RUN,
        audit_events=events,
        dismissals=list(dismissals),
        related_query_ids=related_query_ids,
    )


def _events_for_policy_records(
    policy_records: Iterable[PolicyEvaluationRecord],
) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    for record in policy_records:
        message_event = _audit_event(
            event_id=_event_id(record.message_id, "message"),
            kind=AuditEventKind.MESSAGE_SENT,
            actor_agent_id=record.evaluated_sender_agent_id,
            payload=MessageSentPayload(
                message_type=record.evaluated_message_type.value,
                source_agent_id=record.evaluated_sender_agent_id,
                destination_agent_id=record.evaluated_recipient_agent_id,
            ),
        )
        events.append(message_event)
        events.append(
            _audit_event(
                event_id=_event_id(record.policy_result.message_id, "lt"),
                kind=AuditEventKind.LT_VERDICT,
                actor_agent_id=record.policy_result.sender_agent_id,
                payload=LtVerdictPayload(
                    verdict=record.policy_result.decision.value,
                    request_id=str(message_event.event_id),
                ),
            )
        )
        events.extend(record.audit_events)
    return events


def _events_for_a3_provenance(responses: Iterable[Sec314bResponse]) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    for response in responses:
        for index, record in enumerate(response.provenance):
            if record.rho_debited <= 0.0:
                continue
            events.append(
                _rho_event(
                    event_id=_event_id(response.message_id, f"a3-rho-{index}"),
                    actor_agent_id=response.sender_agent_id,
                    bank_id=response.sender_bank_id,
                    record=record,
                )
            )
    return events


def _events_for_primitive_records(
    primitive_records: Iterable[PrimitiveAuditRecord],
) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    for index, item in enumerate(primitive_records):
        if item.record.rho_debited <= 0.0:
            continue
        events.append(
            _rho_event(
                event_id=_event_id(
                    item.record.args_hash,
                    f"pattern-rho-{index}",
                ),
                actor_agent_id=f"{item.bank_id.value}.A3",
                bank_id=item.bank_id,
                record=item.record,
            )
        )
    return events


def _rho_event(
    *,
    event_id: UUID,
    actor_agent_id: str,
    bank_id: BankId,
    record: PrimitiveCallRecord,
) -> AuditEvent:
    return _audit_event(
        event_id=event_id,
        kind=AuditEventKind.RHO_DEBITED,
        actor_agent_id=actor_agent_id,
        payload=RhoDebitedPayload(
            requester_key=record.args_hash,
            bank_id=bank_id,
            rho_debited=record.rho_debited,
            rho_remaining=1.0,
        ),
    )


def _audit_event(
    *,
    event_id: UUID,
    kind: AuditEventKind,
    actor_agent_id: str,
    payload: object,
) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        sender_agent_id="federation.audit",
        sender_role=AgentRole.ORCHESTRATOR,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="federation.F5",
        kind=kind,
        actor_agent_id=actor_agent_id,
        payload=payload,
    )


def _event_id(seed: UUID | str, label: str) -> UUID:
    return uuid5(_AUDIT_NAMESPACE, f"{seed}:{label}")
