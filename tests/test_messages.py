from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from shared.enums import (
    AgentRole,
    AuditEventKind,
    BankId,
    PatternClass,
    PrivacyUnit,
    QueryShape,
    ResponseValueKind,
    SARPriority,
    SignalType,
    TypologyCode,
)
from shared.messages import (
    AggregateActivityPayload,
    Alert,
    AuditEvent,
    BankAggregate,
    ContributorAttribution,
    DismissalRationale,
    EntityPresencePayload,
    EvidenceItem,
    GraphPatternRequest,
    GraphPatternResponse,
    IntResponseValue,
    LtVerdictPayload,
    MessageSentPayload,
    PrimitiveCallRecord,
    PUBLIC_MESSAGE_MODELS,
    PurposeDeclaration,
    RhoDebitedPayload,
    SARContribution,
    SARDraft,
    SanctionsCheckRequest,
    SanctionsCheckResponse,
    SanctionsResult,
    Sec314bQuery,
    Sec314bResponse,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
ARGS_HASH = "c" * 64


def message_header(
    *,
    sender_agent_id: str = "bank_alpha.A2",
    sender_role: AgentRole = AgentRole.A2,
    sender_bank_id: BankId = BankId.BANK_ALPHA,
    recipient_agent_id: str = "federation.F1",
) -> dict:
    return {
        "sender_agent_id": sender_agent_id,
        "sender_role": sender_role,
        "sender_bank_id": sender_bank_id,
        "recipient_agent_id": recipient_agent_id,
    }


def purpose(alert_id: UUID | None = None) -> PurposeDeclaration:
    return PurposeDeclaration(
        typology_code=TypologyCode.STRUCTURING,
        suspicion_rationale="Repeated sub-threshold activity suggests structuring.",
        supporting_alert_ids=[alert_id or uuid4()],
    )


def primitive_record(
    *,
    field_name: str = "alert_count",
    rho_debited: float = 0.02,
    returned_value_kind: ResponseValueKind = ResponseValueKind.INT,
) -> PrimitiveCallRecord:
    return PrimitiveCallRecord(
        field_name=field_name,
        primitive_name="alert_count_for_entity",
        args_hash=ARGS_HASH,
        privacy_unit=PrivacyUnit.TRANSACTION,
        rho_debited=rho_debited,
        eps_delta_display=(0.5, 0.000001),
        sigma_applied=5.0,
        sensitivity=1.0,
        returned_value_kind=returned_value_kind,
    )


def valid_query(query_id: UUID | None = None) -> Sec314bQuery:
    return Sec314bQuery(
        **message_header(),
        query_id=query_id or uuid4(),
        requesting_investigator_id="investigator-alpha-1",
        requesting_bank_id=BankId.BANK_ALPHA,
        target_bank_ids=[BankId.BANK_BETA, BankId.BANK_GAMMA],
        query_shape=QueryShape.AGGREGATE_ACTIVITY,
        query_payload=AggregateActivityPayload(
            name_hashes=[HASH_A],
            window_start=date(2026, 5, 1),
            window_end=date(2026, 5, 13),
            metrics=["alert_count"],
        ),
        purpose_declaration=purpose(),
        requested_rho_per_primitive=0.02,
    )


def valid_models() -> list[BaseModel]:
    alert_id = uuid4()
    query = valid_query()
    evidence = EvidenceItem(
        summary="Near-threshold cash activity tied to hashed entity.",
        entity_hashes=[HASH_A],
        account_hashes=[HASH_B],
    )
    contribution = ContributorAttribution(
        bank_id=BankId.BANK_ALPHA,
        investigator_id="investigator-alpha-1",
        evidence_item_ids=[evidence.evidence_id],
        contribution_summary="Bank Alpha observed sub-threshold activity.",
    )
    aggregate = BankAggregate(
        bank_id=BankId.BANK_BETA,
        edge_count_distribution=[1, 3, 5],
        bucketed_flow_histogram=[0, 4, 9],
        rho_debited=0.04,
    )

    return [
        Alert(
            **message_header(
                sender_agent_id="bank_alpha.A1",
                sender_role=AgentRole.A1,
                recipient_agent_id="bank_alpha.A2",
            ),
            alert_id=alert_id,
            transaction_id="txn-alpha-1",
            account_id="acct-alpha-1",
            signal_type=SignalType.STRUCTURING,
            severity=0.82,
            rationale="Repeated sub-threshold cash activity.",
            evidence=[evidence],
        ),
        query,
        Sec314bResponse(
            **message_header(
                sender_agent_id="bank_beta.A2",
                sender_bank_id=BankId.BANK_BETA,
                recipient_agent_id="federation.F1",
            ),
            in_reply_to=query.query_id,
            responding_bank_id=BankId.BANK_BETA,
            fields={"alert_count": IntResponseValue(int=3)},
            provenance=[primitive_record()],
            rho_debited_total=0.02,
        ),
        SanctionsCheckRequest(
            **message_header(recipient_agent_id="federation.F3"),
            entity_hashes=[HASH_A],
            requesting_context="Screen hashed entity for sanctions or PEP exposure.",
        ),
        SanctionsCheckResponse(
            **message_header(
                sender_agent_id="federation.F3",
                sender_role=AgentRole.F3,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="federation.F1",
            ),
            in_reply_to=query.query_id,
            results={HASH_A: SanctionsResult(sdn_match=False, pep_relation=True)},
        ),
        GraphPatternRequest(
            **message_header(
                sender_agent_id="federation.F1",
                sender_role=AgentRole.F1,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="federation.F2",
            ),
            pattern_aggregates=[aggregate],
            window_start=date(2026, 5, 1),
            window_end=date(2026, 5, 13),
        ),
        GraphPatternResponse(
            **message_header(
                sender_agent_id="federation.F2",
                sender_role=AgentRole.F2,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="federation.F1",
            ),
            pattern_class=PatternClass.STRUCTURING_RING,
            confidence=0.91,
            suspect_entity_hashes=[HASH_A, HASH_B],
            narrative="Three-bank aggregate pattern is consistent with structuring.",
        ),
        SARContribution(
            **message_header(recipient_agent_id="federation.F4"),
            contributing_bank_id=BankId.BANK_ALPHA,
            contributing_investigator_id="investigator-alpha-1",
            contributed_evidence=[evidence],
            local_rationale="Peer-bank corroboration supports escalation.",
        ),
        SARDraft(
            **message_header(
                sender_agent_id="federation.F4",
                sender_role=AgentRole.F4,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="orchestrator",
            ),
            filing_institution="bank_alpha",
            suspicious_amount_range=(100_000, 795_000),
            typology_code=TypologyCode.STRUCTURING,
            narrative="Federated evidence supports a structuring SAR draft.",
            contributors=[contribution],
            sar_priority=SARPriority.HIGH,
            mandatory_fields_complete=True,
            related_query_ids=[query.query_id],
        ),
        AuditEvent(
            **message_header(
                sender_agent_id="federation.orchestrator",
                sender_role=AgentRole.ORCHESTRATOR,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="audit",
            ),
            kind=AuditEventKind.MESSAGE_SENT,
            actor_agent_id="federation.F1",
            payload=MessageSentPayload(
                message_type="Sec314bQuery",
                source_agent_id="bank_alpha.A2",
                destination_agent_id="federation.F1",
            ),
        ),
        DismissalRationale(
            **message_header(recipient_agent_id="federation.F5"),
            alert_id=alert_id,
            reason="Peer-bank signals did not corroborate the local alert.",
            evidence_considered=[evidence.evidence_id],
        ),
    ]


@pytest.mark.parametrize("model", valid_models(), ids=lambda model: type(model).__name__)
def test_message_models_round_trip_json(model: BaseModel) -> None:
    parsed = type(model).model_validate_json(model.model_dump_json())

    assert parsed == model


@pytest.mark.parametrize("model_cls", PUBLIC_MESSAGE_MODELS, ids=lambda cls: cls.__name__)
def test_public_message_models_export_json_schema(model_cls: type[BaseModel]) -> None:
    schema = model_cls.model_json_schema()

    assert schema["type"] == "object"
    assert "properties" in schema


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        Alert(
            **message_header(sender_agent_id="bank_alpha.A1", sender_role=AgentRole.A1),
            transaction_id="txn-alpha-1",
            account_id="acct-alpha-1",
            signal_type=SignalType.STRUCTURING,
            severity=0.2,
            rationale="Valid rationale.",
            unknown_field="not allowed",
        )


def test_alert_severity_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Alert(
            **message_header(sender_agent_id="bank_alpha.A1", sender_role=AgentRole.A1),
            transaction_id="txn-alpha-1",
            account_id="acct-alpha-1",
            signal_type=SignalType.STRUCTURING,
            severity=1.5,
            rationale="Valid rationale.",
        )


def test_missing_purpose_rationale_fails() -> None:
    with pytest.raises(ValidationError):
        PurposeDeclaration(
            typology_code=TypologyCode.STRUCTURING,
            suspicion_rationale=" ",
        )


def test_query_shape_must_match_payload_shape() -> None:
    with pytest.raises(ValidationError):
        Sec314bQuery(
            **message_header(),
            requesting_investigator_id="investigator-alpha-1",
            requesting_bank_id=BankId.BANK_ALPHA,
            target_bank_ids=[BankId.BANK_BETA],
            query_shape=QueryShape.COUNTERPARTY_LINKAGE,
            query_payload=EntityPresencePayload(name_hashes=[HASH_A]),
            purpose_declaration=purpose(),
            requested_rho_per_primitive=0.02,
        )


def test_sec314b_response_requires_matching_provenance() -> None:
    with pytest.raises(ValidationError):
        Sec314bResponse(
            **message_header(
                sender_agent_id="bank_beta.A2",
                sender_bank_id=BankId.BANK_BETA,
            ),
            in_reply_to=uuid4(),
            responding_bank_id=BankId.BANK_BETA,
            fields={"alert_count": IntResponseValue(int=3)},
            provenance=[],
            rho_debited_total=0.0,
        )


def test_sec314b_response_requires_matching_value_kind() -> None:
    with pytest.raises(ValidationError):
        Sec314bResponse(
            **message_header(
                sender_agent_id="bank_beta.A2",
                sender_bank_id=BankId.BANK_BETA,
            ),
            in_reply_to=uuid4(),
            responding_bank_id=BankId.BANK_BETA,
            fields={"alert_count": IntResponseValue(int=3)},
            provenance=[
                primitive_record(returned_value_kind=ResponseValueKind.FLOAT)
            ],
            rho_debited_total=0.02,
        )


def test_sec314b_response_requires_rho_total_to_match_provenance() -> None:
    with pytest.raises(ValidationError):
        Sec314bResponse(
            **message_header(
                sender_agent_id="bank_beta.A2",
                sender_bank_id=BankId.BANK_BETA,
            ),
            in_reply_to=uuid4(),
            responding_bank_id=BankId.BANK_BETA,
            fields={"alert_count": IntResponseValue(int=3)},
            provenance=[primitive_record(rho_debited=0.02)],
            rho_debited_total=0.03,
        )


def test_refusal_response_cannot_include_fields() -> None:
    with pytest.raises(ValidationError):
        Sec314bResponse(
            **message_header(
                sender_agent_id="bank_beta.A2",
                sender_bank_id=BankId.BANK_BETA,
            ),
            in_reply_to=uuid4(),
            responding_bank_id=BankId.BANK_BETA,
            fields={"alert_count": IntResponseValue(int=3)},
            provenance=[primitive_record()],
            rho_debited_total=0.02,
            refusal_reason="budget_exhausted",
        )


def test_customer_name_strings_are_rejected_in_evidence() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            summary="Jane Doe is associated with the suspicious pattern.",
            entity_hashes=[HASH_A],
        )


# Every planted shell-entity cover-business name from
# data/scripts/plant_scenarios.py must be caught by the customer-name
# defense-in-depth regex. If a new scenario adds entities, this list and
# _DEMO_CUSTOMER_NAME_RE in shared/messages.py must be extended together.
_PLANTED_ENTITY_NAMES = (
    # S1 ring (S1-D is the PEP)
    "Acme Holdings LLC",
    "Beacon Logistics Inc",
    "Citadel Trading Co",
    "Delta Imports Ltd",
    "Eagle Consulting Group",
    # S2 ring (Alpha + Beta only)
    "Foxtrot Wholesale",
    "Gulf Stream Trading",
    "Horizon Ventures",
    # S3 layering chain
    "Iridium Capital Partners",
    "Juniper Asset Mgmt",
    "Kestrel Holdings",
    "Lattice Investments",
)


@pytest.mark.parametrize("entity_name", _PLANTED_ENTITY_NAMES)
def test_planted_entity_names_are_rejected_in_evidence(entity_name: str) -> None:
    """Defense-in-depth: each planted cover-business name is caught at the schema."""
    with pytest.raises(ValidationError):
        EvidenceItem(
            summary=f"{entity_name} appears in the suspect transaction flow.",
            entity_hashes=[HASH_A],
        )


def test_sar_draft_complete_requires_mandatory_fields() -> None:
    with pytest.raises(ValidationError):
        SARDraft(
            **message_header(
                sender_agent_id="federation.F4",
                sender_role=AgentRole.F4,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="orchestrator",
            ),
            mandatory_fields_complete=True,
        )


def test_audit_event_kind_must_match_payload_kind() -> None:
    with pytest.raises(ValidationError):
        AuditEvent(
            **message_header(
                sender_agent_id="federation.orchestrator",
                sender_role=AgentRole.ORCHESTRATOR,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="audit",
            ),
            kind=AuditEventKind.LT_VERDICT,
            actor_agent_id="federation.F1",
            payload=RhoDebitedPayload(
                requester_key="investigator-alpha-1",
                bank_id=BankId.BANK_BETA,
                rho_debited=0.02,
                rho_remaining=0.98,
            ),
        )


def test_lt_verdict_payload_round_trips_as_audit_event() -> None:
    event = AuditEvent(
        **message_header(
            sender_agent_id="federation.orchestrator",
            sender_role=AgentRole.ORCHESTRATOR,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="audit",
        ),
        kind=AuditEventKind.LT_VERDICT,
        actor_agent_id="lobstertrap",
        payload=LtVerdictPayload(
            verdict="ALLOW",
            request_id="req-1",
            rule_name=None,
        ),
    )

    parsed = AuditEvent.model_validate_json(event.model_dump_json())

    assert isinstance(parsed.payload, LtVerdictPayload)
    assert parsed.payload.verdict == "ALLOW"


def test_bank_aggregate_must_come_from_bank() -> None:
    with pytest.raises(ValidationError):
        BankAggregate(
            bank_id=BankId.FEDERATION,
            edge_count_distribution=[1],
            bucketed_flow_histogram=[2],
        )


def test_date_windows_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        AggregateActivityPayload(
            name_hashes=[HASH_A],
            window_start=date(2026, 5, 13),
            window_end=date(2026, 5, 1),
            metrics=["alert_count"],
        )
