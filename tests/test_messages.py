from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from shared.enums import (
    AgentRole,
    AuditEventKind,
    BankId,
    MessageType,
    PatternClass,
    PrivacyUnit,
    QueryShape,
    RouteKind,
    ResponseValueKind,
    SARPriority,
    SignalType,
    TypologyCode,
)
from shared.messages import (
    AggregateActivityPayload,
    AgentMessage,
    Alert,
    AuditEvent,
    BankAggregate,
    ContributorAttribution,
    CounterpartyLinkagePayload,
    DismissalRationale,
    EntityPresencePayload,
    EvidenceItem,
    GraphPatternRequest,
    GraphPatternResponse,
    HashListResponseValue,
    IntResponseValue,
    LtVerdictPayload,
    LocalSiloContributionRequest,
    MessageSentPayload,
    PrimitiveCallRecord,
    PUBLIC_MESSAGE_MODELS,
    PurposeDeclaration,
    ResponseRefusalNote,
    RhoDebitedPayload,
    RouteApproval,
    SARContribution,
    SARDraft,
    SanctionsCheckRequest,
    SanctionsCheckResponse,
    SanctionsResult,
    Sec314bQuery,
    Sec314bResponse,
)


HASH_A = "a" * 16
HASH_B = "b" * 16
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


def route_approval(
    *,
    query_id: UUID,
    route_kind: RouteKind = RouteKind.PEER_314B,
    requesting_bank_id: BankId = BankId.BANK_ALPHA,
    responding_bank_id: BankId = BankId.BANK_BETA,
) -> RouteApproval:
    return RouteApproval(
        query_id=query_id,
        route_kind=route_kind,
        approved_query_body_hash="d" * 64,
        requesting_bank_id=requesting_bank_id,
        responding_bank_id=responding_bank_id,
        approved_by_agent_id="federation.F1",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def valid_models() -> list[BaseModel]:
    alert_id = uuid4()
    query = valid_query()
    local_source_query_id = uuid4()
    evidence = EvidenceItem(
        summary="Near-threshold cash activity tied to hashed entity.",
        entity_hashes=[HASH_A],
        account_hashes=[ARGS_HASH],
        counterparty_hashes=[HASH_B],
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
        LocalSiloContributionRequest(
            **message_header(
                sender_agent_id="federation.F1",
                sender_role=AgentRole.F1,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="bank_alpha.A3",
            ),
            source_query_id=local_source_query_id,
            requesting_investigator_id="investigator-alpha-1",
            requesting_bank_id=BankId.BANK_ALPHA,
            responding_bank_id=BankId.BANK_ALPHA,
            query_shape=QueryShape.AGGREGATE_ACTIVITY,
            query_payload=AggregateActivityPayload(
                name_hashes=[HASH_A],
                window_start=date(2026, 5, 1),
                window_end=date(2026, 5, 13),
                metrics=["pattern_aggregate_for_f2"],
            ),
            purpose_declaration=purpose(),
            requested_rho_per_primitive=0.04,
            route_approval=route_approval(
                query_id=local_source_query_id,
                route_kind=RouteKind.LOCAL_CONTRIBUTION,
                requesting_bank_id=BankId.BANK_ALPHA,
                responding_bank_id=BankId.BANK_ALPHA,
            ),
        ),
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
            partial_refusals=[
                ResponseRefusalNote(
                    responding_bank_id=BankId.BANK_GAMMA,
                    refusal_reason="unsupported_metric",
                    decision="partial_result",
                    detail="Gamma could not answer this metric.",
                )
            ],
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
    assert "message_type" in schema["properties"]
    assert isinstance(schema["properties"]["message_type"]["const"], str)


@pytest.mark.parametrize("model", valid_models(), ids=lambda model: type(model).__name__)
def test_top_level_message_type_serializes_as_string(model: BaseModel) -> None:
    dumped = model.model_dump(mode="json")

    assert isinstance(dumped["message_type"], str)
    assert dumped["message_type"] == model.message_type


def test_agent_message_discriminated_union_uses_message_type() -> None:
    query = valid_query()
    adapter = TypeAdapter(AgentMessage)

    parsed = adapter.validate_json(query.model_dump_json())

    assert isinstance(parsed, Sec314bQuery)
    assert parsed.message_type == MessageType.SEC314B_QUERY.value


def test_agent_message_union_accepts_local_silo_contribution_request() -> None:
    source_query_id = uuid4()
    request = LocalSiloContributionRequest(
        **message_header(
            sender_agent_id="federation.F1",
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="bank_alpha.A3",
        ),
        source_query_id=source_query_id,
        requesting_investigator_id="investigator-alpha-1",
        requesting_bank_id=BankId.BANK_ALPHA,
        responding_bank_id=BankId.BANK_ALPHA,
        query_shape=QueryShape.ENTITY_PRESENCE,
        query_payload=EntityPresencePayload(name_hashes=[HASH_A]),
        purpose_declaration=purpose(),
        route_approval=route_approval(
            query_id=source_query_id,
            route_kind=RouteKind.LOCAL_CONTRIBUTION,
            requesting_bank_id=BankId.BANK_ALPHA,
            responding_bank_id=BankId.BANK_ALPHA,
        ),
    )
    adapter = TypeAdapter(AgentMessage)

    parsed = adapter.validate_json(request.model_dump_json())

    assert isinstance(parsed, LocalSiloContributionRequest)
    assert parsed.message_type == MessageType.LOCAL_SILO_CONTRIBUTION_REQUEST.value


def test_wrong_top_level_message_type_fails() -> None:
    payload = valid_query().model_dump(mode="json")
    payload["message_type"] = MessageType.ALERT.value

    with pytest.raises(ValidationError):
        Sec314bQuery.model_validate(payload)


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


def test_cross_bank_name_hashes_use_short_token_shape() -> None:
    with pytest.raises(ValidationError):
        EntityPresencePayload(name_hashes=["a" * 64])


def test_hash_list_payloads_capped_at_one_hundred_entries() -> None:
    """Schema-level cap on hash-list fields keeps SQL IN() clauses bounded.

    The P7 primitives layer mirrors this cap (MAX_HASH_LIST_LENGTH=100)
    to stay well under SQLite's SQLITE_LIMIT_VARIABLE_NUMBER (default 999).
    """
    too_many = [f"{i:016x}" for i in range(101)]
    just_under = [f"{i:016x}" for i in range(100)]

    # Boundary: exactly 100 hashes is fine.
    EntityPresencePayload(name_hashes=just_under)

    # Over the cap: each payload must reject.
    with pytest.raises(ValidationError):
        EvidenceItem(summary="Too many hashes.", entity_hashes=too_many)
    with pytest.raises(ValidationError):
        EvidenceItem(summary="Too many hashes.", counterparty_hashes=too_many)
    with pytest.raises(ValidationError):
        EntityPresencePayload(name_hashes=too_many)
    with pytest.raises(ValidationError):
        AggregateActivityPayload(
            name_hashes=too_many,
            window_start=date(2026, 5, 1),
            window_end=date(2026, 5, 13),
        )
    with pytest.raises(ValidationError):
        CounterpartyLinkagePayload(
            counterparty_hashes=too_many,
            window_start=date(2026, 5, 1),
            window_end=date(2026, 5, 13),
        )
    with pytest.raises(ValidationError):
        SanctionsCheckRequest(
            **message_header(recipient_agent_id="federation.F3"),
            entity_hashes=too_many,
            requesting_context="Screen hashed entities for sanctions or PEP exposure.",
        )
    with pytest.raises(ValidationError):
        HashListResponseValue(hash_list=too_many)


def test_query_defaults_to_peer_bank_targets() -> None:
    query = Sec314bQuery(
        **message_header(),
        requesting_investigator_id="investigator-alpha-1",
        requesting_bank_id=BankId.BANK_ALPHA,
        query_shape=QueryShape.ENTITY_PRESENCE,
        query_payload=EntityPresencePayload(name_hashes=[HASH_A]),
        purpose_declaration=purpose(),
        requested_rho_per_primitive=0.0,
    )

    assert query.target_bank_ids == [BankId.BANK_BETA, BankId.BANK_GAMMA]


def test_query_targets_must_not_include_requesting_bank() -> None:
    with pytest.raises(ValidationError):
        Sec314bQuery(
            **message_header(),
            requesting_investigator_id="investigator-alpha-1",
            requesting_bank_id=BankId.BANK_ALPHA,
            target_bank_ids=[BankId.BANK_ALPHA, BankId.BANK_BETA],
            query_shape=QueryShape.ENTITY_PRESENCE,
            query_payload=EntityPresencePayload(name_hashes=[HASH_A]),
            purpose_declaration=purpose(),
            requested_rho_per_primitive=0.0,
        )


def test_peer_route_approval_cannot_target_requesting_bank() -> None:
    with pytest.raises(ValidationError):
        route_approval(
            query_id=uuid4(),
            route_kind=RouteKind.PEER_314B,
            requesting_bank_id=BankId.BANK_ALPHA,
            responding_bank_id=BankId.BANK_ALPHA,
        )


def test_local_route_approval_must_target_requesting_bank() -> None:
    with pytest.raises(ValidationError):
        route_approval(
            query_id=uuid4(),
            route_kind=RouteKind.LOCAL_CONTRIBUTION,
            requesting_bank_id=BankId.BANK_ALPHA,
            responding_bank_id=BankId.BANK_BETA,
        )


def test_sec314b_query_route_approval_must_target_peer_in_query() -> None:
    query_id = uuid4()
    with pytest.raises(ValidationError):
        Sec314bQuery(
            **message_header(
                sender_agent_id="federation.F1",
                sender_role=AgentRole.F1,
                sender_bank_id=BankId.FEDERATION,
                recipient_agent_id="bank_gamma.A3",
            ),
            query_id=query_id,
            requesting_investigator_id="investigator-alpha-1",
            requesting_bank_id=BankId.BANK_ALPHA,
            target_bank_ids=[BankId.BANK_BETA],
            query_shape=QueryShape.ENTITY_PRESENCE,
            query_payload=EntityPresencePayload(name_hashes=[HASH_A]),
            purpose_declaration=purpose(),
            route_approval=route_approval(
                query_id=query_id,
                route_kind=RouteKind.PEER_314B,
                requesting_bank_id=BankId.BANK_ALPHA,
                responding_bank_id=BankId.BANK_GAMMA,
            ),
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


def test_primitive_record_preserves_histogram_accounting_mode() -> None:
    record = PrimitiveCallRecord(
        field_name="flow_histogram",
        primitive_name="flow_histogram",
        args_hash=ARGS_HASH,
        privacy_unit=PrivacyUnit.TRANSACTION,
        rho_debited=0.03,
        eps_delta_display=(0.5, 0.000001),
        sigma_applied=12.909944,
        sensitivity=1.0,
        dp_composition="serial",
        per_bucket_rho=0.006,
        returned_value_kind=ResponseValueKind.HISTOGRAM,
    )

    parsed = PrimitiveCallRecord.model_validate_json(record.model_dump_json())

    assert parsed.dp_composition == "serial"
    assert parsed.per_bucket_rho == 0.006


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


def test_response_refusal_notes_round_trip_on_partial_success() -> None:
    note = ResponseRefusalNote(
        responding_bank_id=BankId.BANK_GAMMA,
        refusal_reason="unsupported_metric",
        decision="partial_result",
        detail="Gamma could not answer this metric.",
    )
    response = Sec314bResponse(
        **message_header(
            sender_agent_id="federation.F1",
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id="bank_alpha.A2",
        ),
        in_reply_to=uuid4(),
        responding_bank_id=BankId.FEDERATION,
        fields={"bank_beta.alert_count": IntResponseValue(int=3)},
        provenance=[primitive_record(field_name="bank_beta.alert_count")],
        rho_debited_total=0.02,
        partial_refusals=[note],
    )

    parsed = Sec314bResponse.model_validate_json(response.model_dump_json())

    assert parsed.partial_refusals == [note]


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
