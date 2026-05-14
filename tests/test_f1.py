from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.agents import F1CoordinatorAgent, InMemoryAuditEmitter, LLMClient
from backend.agents.f1_coordinator import _validated_model_copy
from backend.agents.f1_states import F1AggregationInput, F1InboundQueryInput, F1TurnInput
from backend.runtime import AgentRuntimeContext, LLMClientConfig, TrustDomain
from backend.security import (
    PrincipalAllowlist,
    PrincipalAllowlistEntry,
    ReplayCache,
    approved_body_hash,
    generate_key_pair,
    sign_message,
    verify_message_signature,
    verify_model_signature,
)
from shared.enums import (
    AgentRole,
    BankId,
    MessageType,
    PrivacyUnit,
    QueryShape,
    ResponseValueKind,
    RouteKind,
    TypologyCode,
)
from shared.messages import (
    A3_RESPONSE_NONCE_SUFFIX,
    AggregateActivityPayload,
    CounterpartyLinkagePayload,
    IntResponseValue,
    PrimitiveCallRecord,
    PurposeDeclaration,
    Sec314bQuery,
    Sec314bResponse,
)


HASH_A = "a" * 16
HASH_B = "b" * 16
ARGS_HASH = "c" * 64


def runtime() -> AgentRuntimeContext:
    return AgentRuntimeContext(
        run_id="run-f1-test",
        node_id="federation-node",
        trust_domain=TrustDomain.FEDERATION,
        llm=LLMClientConfig(
            base_url="http://federation.local:8080/v1/chat/completions",
            default_model="stub-model",
            stub_mode=True,
            node_id="federation-node",
        ),
    )


def principal(
    *,
    agent_id: str,
    role: AgentRole,
    bank_id: BankId,
    signing_key_id: str,
    public_key: str,
    allowed_message_types: list[str],
    allowed_recipients: list[str],
    allowed_routes: list[RouteKind] | None = None,
) -> PrincipalAllowlistEntry:
    return PrincipalAllowlistEntry(
        agent_id=agent_id,
        role=role,
        bank_id=bank_id,
        signing_key_id=signing_key_id,
        public_key=public_key,
        allowed_message_types=allowed_message_types,
        allowed_recipients=allowed_recipients,
        allowed_routes=allowed_routes or [],
    )


class F1Fixture:
    def __init__(self) -> None:
        self.a2_key = generate_key_pair("a2-alpha-key")
        self.f1_key = generate_key_pair("f1-key")
        self.a3_alpha_key = generate_key_pair("a3-alpha-key")
        self.a3_beta_key = generate_key_pair("a3-beta-key")
        self.a3_gamma_key = generate_key_pair("a3-gamma-key")
        self.allowlist = PrincipalAllowlist(
            [
                principal(
                    agent_id="bank_alpha.A2",
                    role=AgentRole.A2,
                    bank_id=BankId.BANK_ALPHA,
                    signing_key_id=self.a2_key.signing_key_id,
                    public_key=self.a2_key.public_key,
                    allowed_message_types=[MessageType.SEC314B_QUERY.value],
                    allowed_recipients=["federation.F1"],
                ),
                principal(
                    agent_id="federation.F1",
                    role=AgentRole.F1,
                    bank_id=BankId.FEDERATION,
                    signing_key_id=self.f1_key.signing_key_id,
                    public_key=self.f1_key.public_key,
                    allowed_message_types=[
                        MessageType.SEC314B_QUERY.value,
                        MessageType.LOCAL_SILO_CONTRIBUTION_REQUEST.value,
                        MessageType.SEC314B_RESPONSE.value,
                        MessageType.SANCTIONS_CHECK_REQUEST.value,
                    ],
                    allowed_recipients=[
                        "bank_alpha.A2",
                        "bank_alpha.A3",
                        "bank_beta.A3",
                        "bank_gamma.A3",
                        "federation.F3",
                    ],
                    allowed_routes=[RouteKind.PEER_314B, RouteKind.LOCAL_CONTRIBUTION],
                ),
                principal(
                    agent_id="bank_alpha.A3",
                    role=AgentRole.A3,
                    bank_id=BankId.BANK_ALPHA,
                    signing_key_id=self.a3_alpha_key.signing_key_id,
                    public_key=self.a3_alpha_key.public_key,
                    allowed_message_types=[MessageType.SEC314B_RESPONSE.value],
                    allowed_recipients=["federation.F1"],
                ),
                principal(
                    agent_id="bank_beta.A3",
                    role=AgentRole.A3,
                    bank_id=BankId.BANK_BETA,
                    signing_key_id=self.a3_beta_key.signing_key_id,
                    public_key=self.a3_beta_key.public_key,
                    allowed_message_types=[MessageType.SEC314B_RESPONSE.value],
                    allowed_recipients=["federation.F1"],
                ),
                principal(
                    agent_id="bank_gamma.A3",
                    role=AgentRole.A3,
                    bank_id=BankId.BANK_GAMMA,
                    signing_key_id=self.a3_gamma_key.signing_key_id,
                    public_key=self.a3_gamma_key.public_key,
                    allowed_message_types=[MessageType.SEC314B_RESPONSE.value],
                    allowed_recipients=["federation.F1"],
                ),
            ]
        )
        self.audit = InMemoryAuditEmitter()
        self.agent = F1CoordinatorAgent(
            runtime=runtime(),
            principal_allowlist=self.allowlist,
            replay_cache=ReplayCache(),
            private_key=self.f1_key.private_key,
            signing_key_id=self.f1_key.signing_key_id,
            llm=LLMClient(runtime().llm, stub_responses=[]),
            audit=self.audit,
        )


@pytest.fixture
def fixture() -> F1Fixture:
    return F1Fixture()


def unsigned_query(
    *,
    target_bank_ids: list[BankId] | None = None,
    metrics: list[str] | None = None,
    name_hashes: list[str] | None = None,
    typology_code: TypologyCode = TypologyCode.STRUCTURING,
    requested_rho: float = 0.02,
) -> Sec314bQuery:
    return Sec314bQuery(
        sender_agent_id="bank_alpha.A2",
        sender_role=AgentRole.A2,
        sender_bank_id=BankId.BANK_ALPHA,
        recipient_agent_id="federation.F1",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        nonce="a2-query-nonce",
        requesting_investigator_id="investigator-alpha-1",
        requesting_bank_id=BankId.BANK_ALPHA,
        target_bank_ids=target_bank_ids or [BankId.BANK_BETA, BankId.BANK_GAMMA],
        query_shape=QueryShape.AGGREGATE_ACTIVITY,
        query_payload=AggregateActivityPayload(
            name_hashes=name_hashes or [HASH_A],
            window_start=datetime(2026, 5, 1, tzinfo=UTC).date(),
            window_end=datetime(2026, 5, 13, tzinfo=UTC).date(),
            metrics=metrics or ["alert_count"],
        ),
        purpose_declaration=PurposeDeclaration(
            typology_code=typology_code,
            suspicion_rationale="Repeated local alerts justify peer-bank corroboration.",
        ),
        requested_rho_per_primitive=requested_rho,
    )


def signed_query(fixture: F1Fixture, **kwargs: object) -> Sec314bQuery:
    query = unsigned_query(**kwargs)
    return sign_message(
        query,
        private_key=fixture.a2_key.private_key,
        signing_key_id=fixture.a2_key.signing_key_id,
    )


def f1_input(query: Sec314bQuery) -> F1TurnInput:
    return F1TurnInput(payload=F1InboundQueryInput(query=query))


def primitive_record(
    *,
    field_name: str = "alert_count",
    rho: float = 0.02,
) -> PrimitiveCallRecord:
    return PrimitiveCallRecord(
        field_name=field_name,
        primitive_name="alert_count_for_entity",
        args_hash=ARGS_HASH,
        privacy_unit=PrivacyUnit.TRANSACTION,
        rho_debited=rho,
        eps_delta_display=(0.5, 0.000001),
        sigma_applied=5.0,
        sensitivity=1.0,
        returned_value_kind=ResponseValueKind.INT,
    )


def signed_a3_response(
    fixture: F1Fixture,
    *,
    bank_id: BankId,
    query: Sec314bQuery,
    value: int | None = 3,
    refusal_reason: str | None = None,
    nonce: str | None = None,
    created_at: datetime | None = None,
) -> Sec314bResponse:
    key = {
        BankId.BANK_ALPHA: fixture.a3_alpha_key,
        BankId.BANK_BETA: fixture.a3_beta_key,
        BankId.BANK_GAMMA: fixture.a3_gamma_key,
    }[bank_id]
    response_created_at = created_at or datetime.now(UTC)
    fields = {} if refusal_reason is not None else {"alert_count": IntResponseValue(int=value or 0)}
    provenance = [] if refusal_reason is not None else [primitive_record()]
    response = Sec314bResponse(
        sender_agent_id=f"{bank_id.value}.A3",
        sender_role=AgentRole.A3,
        sender_bank_id=bank_id,
        recipient_agent_id="federation.F1",
        created_at=response_created_at,
        expires_at=response_created_at + timedelta(minutes=5),
        nonce=(
            nonce
            if nonce is not None
            else (
                f"{query.nonce}:f1:{RouteKind.PEER_314B.value}:"
                f"{bank_id.value}{A3_RESPONSE_NONCE_SUFFIX}"
            )
        ),
        in_reply_to=query.query_id,
        responding_bank_id=bank_id,
        fields=fields,
        provenance=provenance,
        rho_debited_total=sum(record.rho_debited for record in provenance),
        refusal_reason=refusal_reason,
    )
    return sign_message(
        response,
        private_key=key.private_key,
        signing_key_id=key.signing_key_id,
    )


def test_f1_routes_signed_a2_query_to_requested_peer_a3s(fixture: F1Fixture) -> None:
    query = signed_query(fixture)

    result = fixture.agent.run(f1_input(query))

    assert result.action == "route_plan"
    assert result.route_plan is not None
    routed = result.route_plan.peer_requests
    assert [request.target_bank_ids for request in routed] == [
        [BankId.BANK_BETA],
        [BankId.BANK_GAMMA],
    ]
    for request in routed:
        assert request.message_id != query.message_id
        assert request.sender_agent_id == "federation.F1"
        assert request.sender_role == AgentRole.F1
        assert request.route_approval is not None
        assert request.route_approval.approved_query_body_hash == approved_body_hash(request)
        verify_message_signature(request, public_key=fixture.f1_key.public_key)
        verify_model_signature(request.route_approval, public_key=fixture.f1_key.public_key)


def test_f1_never_expands_targets_beyond_a2_request(fixture: F1Fixture) -> None:
    query = signed_query(fixture, target_bank_ids=[BankId.BANK_BETA])

    result = fixture.agent.run(f1_input(query))

    assert result.route_plan is not None
    assert len(result.route_plan.peer_requests) == 1
    assert result.route_plan.peer_requests[0].target_bank_ids == [BankId.BANK_BETA]


def test_f1_adds_local_contribution_for_pattern_aggregate(fixture: F1Fixture) -> None:
    query = signed_query(
        fixture,
        metrics=["pattern_aggregate_for_f2"],
        requested_rho=0.04,
    )

    result = fixture.agent.run(f1_input(query))

    assert result.route_plan is not None
    assert result.route_plan.local_request is not None
    local = result.route_plan.local_request
    assert local.responding_bank_id == BankId.BANK_ALPHA
    assert local.route_approval.route_kind == RouteKind.LOCAL_CONTRIBUTION
    assert all(
        request.target_bank_ids != [BankId.BANK_ALPHA]
        for request in result.route_plan.peer_requests
    )


def test_blank_purpose_cannot_be_signed_for_f1_routing(fixture: F1Fixture) -> None:
    query = signed_query(fixture)
    blank_purpose = query.purpose_declaration.model_copy(
        update={"suspicion_rationale": " "}
    )
    blank_query = query.model_copy(update={"purpose_declaration": blank_purpose})

    with pytest.raises(ValidationError, match="suspicion_rationale"):
        sign_message(
            blank_query,
            private_key=fixture.a2_key.private_key,
            signing_key_id=fixture.a2_key.signing_key_id,
        )


def test_f1_rejects_tampered_a2_query_without_signing_refusal(
    fixture: F1Fixture,
) -> None:
    query = signed_query(fixture)
    tampered = query.model_copy(update={"requested_rho_per_primitive": 0.5})

    result = fixture.agent.run(f1_input(tampered))

    assert result.action == "refusal"
    assert result.response is not None
    assert result.response.refusal_reason == "signature_invalid"
    assert result.response.signature is None


def test_f1_labels_disallowed_principal_separately_from_bad_signature(
    fixture: F1Fixture,
) -> None:
    query = unsigned_query(target_bank_ids=[BankId.BANK_BETA]).model_copy(
        update={"recipient_agent_id": "bank_beta.A3"}
    )
    signed = sign_message(
        query,
        private_key=fixture.a2_key.private_key,
        signing_key_id=fixture.a2_key.signing_key_id,
    )

    result = fixture.agent.run(f1_input(signed))

    assert result.action == "refusal"
    assert result.response is not None
    assert result.response.refusal_reason == "principal_not_allowed"
    assert result.response.signature is None


def test_f1_emits_sanctions_side_request_for_sanctions_typology(
    fixture: F1Fixture,
) -> None:
    query = signed_query(fixture, typology_code=TypologyCode.SANCTIONS_EVASION)

    result = fixture.agent.run(f1_input(query))

    assert result.route_plan is not None
    assert result.route_plan.sanctions_request is not None
    assert result.route_plan.sanctions_request.recipient_agent_id == "federation.F3"
    assert result.route_plan.sanctions_request.entity_hashes == [HASH_A]
    verify_message_signature(
        result.route_plan.sanctions_request,
        public_key=fixture.f1_key.public_key,
    )


def test_f1_aggregates_signed_a3_responses_with_namespaced_provenance(
    fixture: F1Fixture,
) -> None:
    query = signed_query(fixture)
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None
    beta = signed_a3_response(fixture, bank_id=BankId.BANK_BETA, query=query, value=3)
    gamma = signed_a3_response(fixture, bank_id=BankId.BANK_GAMMA, query=query, value=2)

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=route_result.route_plan.peer_requests,
                responses=[beta, gamma],
            )
        )
    )

    assert result.action == "aggregate"
    assert result.response is not None
    assert result.response.sender_agent_id == "federation.F1"
    assert result.response.recipient_agent_id == "bank_alpha.A2"
    assert result.response.fields == {
        "bank_beta.alert_count": IntResponseValue(int=3),
        "bank_gamma.alert_count": IntResponseValue(int=2),
    }
    assert [record.field_name for record in result.response.provenance] == [
        "bank_beta.alert_count",
        "bank_gamma.alert_count",
    ]
    assert result.response.rho_debited_total == 0.04
    verify_message_signature(result.response, public_key=fixture.f1_key.public_key)


def test_f1_route_and_aggregate_are_deterministic_without_llm(
    fixture: F1Fixture,
) -> None:
    query = signed_query(fixture, target_bank_ids=[BankId.BANK_BETA])
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None
    beta = signed_a3_response(fixture, bank_id=BankId.BANK_BETA, query=query, value=3)

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=route_result.route_plan.peer_requests,
                responses=[beta],
            )
        )
    )

    assert result.action == "aggregate"
    assert fixture.agent.llm.call_count == 0


def test_f1_converts_negotiable_silo_refusal_into_one_retry_request(
    fixture: F1Fixture,
) -> None:
    query = signed_query(
        fixture,
        target_bank_ids=[BankId.BANK_BETA],
        metrics=["alert_count"],
        name_hashes=[HASH_A, HASH_B],
    )
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None
    refusal = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_BETA,
        query=query,
        refusal_reason="unsupported_metric_combination",
    )

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=route_result.route_plan.peer_requests,
                responses=[refusal],
            )
        )
    )

    assert result.action == "retry_plan"
    assert result.route_plan is not None
    assert result.route_plan.negotiation_notes[0].decision == "retry_with_supported_metric"
    assert "metrics alert_count -> flow_histogram" in result.route_plan.negotiation_notes[0].detail
    retry = result.route_plan.peer_requests[0]
    assert isinstance(retry.query_payload, AggregateActivityPayload)
    assert retry.query_payload.metrics == ["flow_histogram"]
    assert retry.nonce is not None
    assert "retry-unsupported_metric_combination" in retry.nonce
    assert retry.route_approval.retry_count == 1
    assert retry.route_approval.approved_query_body_hash == approved_body_hash(retry)


def test_f1_retry_count_uses_route_approval_not_nonce_text(
    fixture: F1Fixture,
) -> None:
    base_query = unsigned_query(
        target_bank_ids=[BankId.BANK_BETA],
        metrics=["alert_count"],
        name_hashes=[HASH_A, HASH_B],
    ).model_copy(update={"nonce": "a2-nonce:retry-:retry-"})
    query = sign_message(
        base_query,
        private_key=fixture.a2_key.private_key,
        signing_key_id=fixture.a2_key.signing_key_id,
    )
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None
    assert route_result.route_plan.peer_requests[0].route_approval.retry_count == 0
    refusal = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_BETA,
        query=query,
        refusal_reason="unsupported_metric_combination",
    )

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=route_result.route_plan.peer_requests,
                responses=[refusal],
            )
        )
    )

    assert result.action == "retry_plan"
    assert result.route_plan is not None
    assert result.route_plan.peer_requests[0].route_approval.retry_count == 1


def test_f1_returns_silo_error_after_retry_limit(
    fixture: F1Fixture,
) -> None:
    query = signed_query(
        fixture,
        target_bank_ids=[BankId.BANK_BETA],
        requested_rho=0.08,
    )
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None

    first_refusal = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_BETA,
        query=query,
        refusal_reason="budget_exhausted",
    )
    first_retry = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=route_result.route_plan.peer_requests,
                responses=[first_refusal],
            )
        )
    )
    assert first_retry.action == "retry_plan"
    assert first_retry.route_plan is not None
    retry_one = first_retry.route_plan.peer_requests[0]
    assert retry_one.requested_rho_per_primitive == 0.04

    second_refusal = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_BETA,
        query=query,
        refusal_reason="budget_exhausted",
        nonce=f"{retry_one.nonce}{A3_RESPONSE_NONCE_SUFFIX}",
    )
    second_retry = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=[retry_one],
                responses=[second_refusal],
            )
        )
    )
    assert second_retry.action == "retry_plan"
    assert second_retry.route_plan is not None
    retry_two = second_retry.route_plan.peer_requests[0]
    assert retry_two.requested_rho_per_primitive == 0.02

    terminal_refusal = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_BETA,
        query=query,
        refusal_reason="budget_exhausted",
        nonce=f"{retry_two.nonce}{A3_RESPONSE_NONCE_SUFFIX}",
    )
    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=[retry_two],
                responses=[terminal_refusal],
            )
        )
    )

    assert result.action == "refusal"
    assert result.response is not None
    assert result.response.refusal_reason == "budget_exhausted"
    assert result.response.partial_refusals[0].refusal_reason == "budget_exhausted"


def test_f1_revalidates_original_query_before_aggregation(
    fixture: F1Fixture,
) -> None:
    query = signed_query(fixture)
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None
    tampered_original = query.model_copy(update={"requested_rho_per_primitive": 0.5})

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=tampered_original,
                routed_requests=route_result.route_plan.peer_requests,
                responses=[],
            )
        )
    )

    assert result.action == "refusal"
    assert result.response is not None
    assert result.response.refusal_reason == "signature_invalid"
    assert result.response.signature is None


def test_f1_aggregation_revalidation_skips_original_query_clock_skew(
    fixture: F1Fixture,
) -> None:
    now = datetime.now(UTC)
    old_query = unsigned_query(target_bank_ids=[BankId.BANK_BETA]).model_copy(
        update={
            "created_at": now - timedelta(minutes=10),
            "expires_at": now + timedelta(minutes=5),
            "nonce": "old-but-in-flight-a2-query",
        }
    )
    signed_old_query = sign_message(
        old_query,
        private_key=fixture.a2_key.private_key,
        signing_key_id=fixture.a2_key.signing_key_id,
    )
    routed = fixture.agent._build_peer_request(
        signed_old_query,
        responding_bank_id=BankId.BANK_BETA,
        retry_suffix=None,
    )
    beta = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_BETA,
        query=signed_old_query,
        value=3,
    )

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=signed_old_query,
                routed_requests=[routed],
                responses=[beta],
            )
        )
    )

    assert result.action == "aggregate"
    assert result.response is not None
    assert result.response.refusal_reason is None
    assert result.response.fields == {
        "bank_beta.alert_count": IntResponseValue(int=3),
    }


def test_f1_revalidates_routed_requests_before_aggregation(
    fixture: F1Fixture,
) -> None:
    query = signed_query(fixture, target_bank_ids=[BankId.BANK_BETA])
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None
    tampered_route = route_result.route_plan.peer_requests[0].model_copy(
        update={"requested_rho_per_primitive": 0.5}
    )
    beta = signed_a3_response(fixture, bank_id=BankId.BANK_BETA, query=query, value=3)

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=[tampered_route],
                responses=[beta],
            )
        )
    )

    assert result.action == "refusal"
    assert result.response is not None
    assert result.response.refusal_reason == "signature_invalid"
    assert result.response.signature is None


def test_f1_validated_copy_rejects_invalid_schema_update(
    fixture: F1Fixture,
) -> None:
    query = signed_query(fixture, target_bank_ids=[BankId.BANK_BETA])

    with pytest.raises(ValidationError):
        _validated_model_copy(
            query,
            update={"target_bank_ids": [BankId.BANK_ALPHA]},
        )


def test_f1_rejects_a3_response_not_bound_to_routed_request_nonce(
    fixture: F1Fixture,
) -> None:
    query = signed_query(fixture, target_bank_ids=[BankId.BANK_BETA])
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None
    response_to_other_route = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_BETA,
        query=query,
        value=3,
        nonce=f"other-f1-request{A3_RESPONSE_NONCE_SUFFIX}",
    )

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=route_result.route_plan.peer_requests,
                responses=[response_to_other_route],
            )
        )
    )

    assert result.action == "refusal"
    assert result.response is not None
    assert result.response.refusal_reason == "route_violation"


def test_f1_aggregate_preserves_partial_refusal_notes(
    fixture: F1Fixture,
) -> None:
    query = signed_query(fixture)
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None
    beta = signed_a3_response(fixture, bank_id=BankId.BANK_BETA, query=query, value=3)
    gamma_refusal = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_GAMMA,
        query=query,
        refusal_reason="unsupported_metric",
    )

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=route_result.route_plan.peer_requests,
                responses=[beta, gamma_refusal],
            )
        )
    )

    assert result.action == "aggregate"
    assert result.response is not None
    assert result.response.refusal_reason is None
    assert result.response.fields == {"bank_beta.alert_count": IntResponseValue(int=3)}
    assert len(result.response.partial_refusals) == 1
    refusal = result.response.partial_refusals[0]
    assert refusal.responding_bank_id == BankId.BANK_GAMMA
    assert refusal.refusal_reason == "unsupported_metric"


def test_f1_all_refused_mixed_reasons_returns_mixed_refusals(
    fixture: F1Fixture,
) -> None:
    query = signed_query(fixture)
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None
    beta_refusal = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_BETA,
        query=query,
        refusal_reason="unsupported_metric",
    )
    gamma_refusal = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_GAMMA,
        query=query,
        refusal_reason="route_violation",
    )

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=route_result.route_plan.peer_requests,
                responses=[beta_refusal, gamma_refusal],
            )
        )
    )

    assert result.action == "refusal"
    assert result.response is not None
    assert result.response.refusal_reason == "mixed_refusals"
    assert {note.refusal_reason for note in result.response.partial_refusals} == {
        "unsupported_metric",
        "route_violation",
    }


def test_f1_rejects_a3_response_created_after_route_approval_expiry(
    fixture: F1Fixture,
) -> None:
    now = datetime.now(UTC)
    near_expiry = unsigned_query(target_bank_ids=[BankId.BANK_BETA]).model_copy(
        update={
            "created_at": now,
            "expires_at": now + timedelta(seconds=3),
            "nonce": "near-expiry-for-late-a3-response",
        }
    )
    query = sign_message(
        near_expiry,
        private_key=fixture.a2_key.private_key,
        signing_key_id=fixture.a2_key.signing_key_id,
    )
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None
    routed = route_result.route_plan.peer_requests[0]
    created_after_approval = routed.route_approval.expires_at + timedelta(seconds=1)
    late_response = signed_a3_response(
        fixture,
        bank_id=BankId.BANK_BETA,
        query=query,
        value=3,
        created_at=created_after_approval,
    )

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=[routed],
                responses=[late_response],
            )
        )
    )

    assert result.action == "refusal"
    assert result.response is not None
    assert result.response.refusal_reason == "route_violation"


def test_f1_sanctions_side_request_includes_counterparty_hashes(
    fixture: F1Fixture,
) -> None:
    query = Sec314bQuery(
        sender_agent_id="bank_alpha.A2",
        sender_role=AgentRole.A2,
        sender_bank_id=BankId.BANK_ALPHA,
        recipient_agent_id="federation.F1",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        nonce="counterparty-sanctions-query",
        requesting_investigator_id="investigator-alpha-1",
        requesting_bank_id=BankId.BANK_ALPHA,
        target_bank_ids=[BankId.BANK_BETA],
        query_shape=QueryShape.COUNTERPARTY_LINKAGE,
        query_payload=CounterpartyLinkagePayload(
            counterparty_hashes=[HASH_B],
            window_start=datetime(2026, 5, 1, tzinfo=UTC).date(),
            window_end=datetime(2026, 5, 13, tzinfo=UTC).date(),
        ),
        purpose_declaration=PurposeDeclaration(
            typology_code=TypologyCode.SANCTIONS_EVASION,
            suspicion_rationale="Counterparty token may indicate sanctions exposure.",
        ),
        requested_rho_per_primitive=0.0,
    )
    signed = sign_message(
        query,
        private_key=fixture.a2_key.private_key,
        signing_key_id=fixture.a2_key.signing_key_id,
    )

    result = fixture.agent.run(f1_input(signed))

    assert result.route_plan is not None
    assert result.route_plan.sanctions_request is not None
    assert result.route_plan.sanctions_request.entity_hashes == [HASH_B]


def test_f1_empty_aggregation_is_a_refusal(fixture: F1Fixture) -> None:
    query = signed_query(fixture, target_bank_ids=[BankId.BANK_BETA])
    route_result = fixture.agent.run(f1_input(query))
    assert route_result.route_plan is not None

    result = fixture.agent.run(
        F1TurnInput(
            payload=F1AggregationInput(
                original_query=query,
                routed_requests=route_result.route_plan.peer_requests,
                responses=[],
            )
        )
    )

    assert result.action == "refusal"
    assert result.response is not None
    assert result.response.refusal_reason == "no_silo_responses"
    assert result.response.signature is not None


def test_f1_adds_expiry_floor_to_near_expiry_routes(fixture: F1Fixture) -> None:
    now = datetime.now(UTC)
    query = unsigned_query()
    near_expiry = query.model_copy(
        update={
            "created_at": now,
            "expires_at": now + timedelta(seconds=3),
            "nonce": "near-expiry-a2-query",
        }
    )
    signed_near_expiry = sign_message(
        near_expiry,
        private_key=fixture.a2_key.private_key,
        signing_key_id=fixture.a2_key.signing_key_id,
    )

    result = fixture.agent.run(f1_input(signed_near_expiry))

    assert result.route_plan is not None
    routed = result.route_plan.peer_requests[0]
    assert routed.expires_at is not None
    assert routed.expires_at >= routed.created_at + timedelta(seconds=9)
    assert routed.route_approval.expires_at == routed.expires_at
