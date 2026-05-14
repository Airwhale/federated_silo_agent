from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from backend.agents import A3SiloResponderAgent, InMemoryAuditEmitter, LLMClient
from backend.agents.a3_states import A3PrimitiveBundle, A3TurnInput
from backend.runtime import AgentRuntimeContext, LLMClientConfig, TrustDomain
from backend.security import (
    PrincipalAllowlist,
    PrincipalAllowlistEntry,
    ReplayCache,
    approved_body_hash,
    generate_key_pair,
    sign_message,
    sign_model_signature,
)
from backend.silos.budget import RequesterKey
from backend.silos.stats_primitives import PrimitiveResult
from shared.enums import (
    AgentRole,
    AuditEventKind,
    BankId,
    MessageType,
    PrivacyUnit,
    QueryShape,
    ResponseValueKind,
    RouteKind,
    TypologyCode,
)
from shared.messages import (
    AggregateActivityPayload,
    BankAggregate,
    CounterpartyLinkagePayload,
    EntityPresencePayload,
    HistogramResponseValue,
    IntResponseValue,
    LocalSiloContributionRequest,
    PrimitiveCallRecord,
    PurposeDeclaration,
    RouteApproval,
    Sec314bQuery,
)


HASH_A = "a" * 16
HASH_B = "b" * 16
ARGS_HASH = "c" * 64


class FakePrimitives:
    def __init__(self, bank_id: BankId) -> None:
        self.bank_id = bank_id
        self.calls: list[str] = []
        self.entity_result = PrimitiveResult(
            value=2,
            records=[primitive_record(field_name="entity_count")],
        )
        self.alert_result = PrimitiveResult(
            value=3,
            records=[primitive_record(field_name="alert_count", rho_debited=0.02)],
        )
        self.pattern_result = PrimitiveResult(
            value=BankAggregate(
                bank_id=bank_id,
                edge_count_distribution=[1, 0, 2, 0],
                bucketed_flow_histogram=[0, 4, 1, 0, 0],
                rho_debited=0.04,
            ),
            records=[
                primitive_record(
                    field_name="edge_count_distribution",
                    returned_value_kind=ResponseValueKind.HISTOGRAM,
                    rho_debited=0.02,
                ),
                primitive_record(
                    field_name="bucketed_flow_histogram",
                    returned_value_kind=ResponseValueKind.HISTOGRAM,
                    rho_debited=0.02,
                ),
            ],
        )

    def count_entities_by_name_hash(
        self,
        *,
        name_hashes: list[str],
        requester: RequesterKey,
        rho: float = 0.0,
    ) -> PrimitiveResult:
        self.calls.append(f"count:{','.join(name_hashes)}:{requester.stable_key}:{rho}")
        return self.entity_result

    def alert_count_for_entity(
        self,
        *,
        name_hash: str,
        window: tuple[date, date],
        requester: RequesterKey,
        rho: float = 0.02,
    ) -> PrimitiveResult:
        self.calls.append(f"alert:{name_hash}:{window[0]}:{window[1]}:{rho}")
        return self.alert_result

    def flow_histogram(
        self,
        *,
        name_hashes: list[str],
        window: tuple[date, date],
        requester: RequesterKey,
        rho: float = 0.03,
    ) -> PrimitiveResult:
        self.calls.append(f"flow:{','.join(name_hashes)}:{window[0]}:{window[1]}:{rho}")
        return PrimitiveResult(
            value=[0, 1, 2, 0, 0],
            records=[
                primitive_record(
                    field_name="flow_histogram",
                    returned_value_kind=ResponseValueKind.HISTOGRAM,
                    rho_debited=rho,
                )
            ],
        )

    def pattern_aggregate_for_f2(
        self,
        *,
        window: tuple[date, date],
        requester: RequesterKey,
        rho: float = 0.04,
    ) -> PrimitiveResult:
        self.calls.append(f"pattern:{window[0]}:{window[1]}:{rho}")
        return self.pattern_result


def primitive_record(
    *,
    field_name: str,
    returned_value_kind: ResponseValueKind = ResponseValueKind.INT,
    rho_debited: float = 0.0,
) -> PrimitiveCallRecord:
    return PrimitiveCallRecord(
        field_name=field_name,
        primitive_name="fake_primitive",
        args_hash=ARGS_HASH,
        privacy_unit=PrivacyUnit.TRANSACTION,
        rho_debited=rho_debited,
        eps_delta_display=None,
        sigma_applied=None,
        sensitivity=1.0,
        returned_value_kind=returned_value_kind,
    )


def runtime() -> AgentRuntimeContext:
    return AgentRuntimeContext(
        run_id="run-p8a-test",
        node_id="bank-beta-node",
        trust_domain=TrustDomain.BANK_SILO,
        llm=LLMClientConfig(stub_mode=True, default_model="stub-model"),
    )


def f1_allowlist(public_key: str) -> PrincipalAllowlist:
    return PrincipalAllowlist(
        [
            PrincipalAllowlistEntry(
                agent_id="federation.F1",
                role=AgentRole.F1,
                bank_id=BankId.FEDERATION,
                signing_key_id="f1-key",
                public_key=public_key,
                allowed_message_types=[
                    MessageType.SEC314B_QUERY.value,
                    MessageType.LOCAL_SILO_CONTRIBUTION_REQUEST.value,
                ],
                allowed_recipients=["bank_alpha.A3", "bank_beta.A3"],
                allowed_routes=[RouteKind.PEER_314B, RouteKind.LOCAL_CONTRIBUTION],
            )
        ]
    )


def purpose() -> PurposeDeclaration:
    return PurposeDeclaration(
        typology_code=TypologyCode.STRUCTURING,
        suspicion_rationale="Repeated hash activity suggests structuring.",
    )


def expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=5)


def signed_peer_query(
    *,
    private_key: str,
    requested_rho: float = 0.02,
    stale_route_hash: bool = False,
    entity_window: tuple[date, date] | None = None,
) -> Sec314bQuery:
    entity_payload = EntityPresencePayload(
        name_hashes=[HASH_A, HASH_B],
        window_start=entity_window[0] if entity_window is not None else None,
        window_end=entity_window[1] if entity_window is not None else None,
    )
    query = Sec314bQuery(
        sender_agent_id="federation.F1",
        sender_role=AgentRole.F1,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="bank_beta.A3",
        expires_at=expires_at(),
        nonce=f"nonce-{uuid4()}",
        requesting_investigator_id="investigator-alpha-1",
        requesting_bank_id=BankId.BANK_ALPHA,
        target_bank_ids=[BankId.BANK_BETA],
        query_shape=QueryShape.ENTITY_PRESENCE,
        query_payload=entity_payload,
        purpose_declaration=purpose(),
        requested_rho_per_primitive=requested_rho,
    )
    route_hash_source = (
        query.model_copy(update={"requested_rho_per_primitive": 0.0})
        if stale_route_hash
        else query
    )
    route = RouteApproval(
        query_id=query.query_id,
        route_kind=RouteKind.PEER_314B,
        approved_query_body_hash=approved_body_hash(route_hash_source),
        requesting_bank_id=BankId.BANK_ALPHA,
        responding_bank_id=BankId.BANK_BETA,
        approved_by_agent_id="federation.F1",
        expires_at=query.expires_at,
    )
    signed_route = sign_model_signature(
        route,
        private_key=private_key,
        signing_key_id="f1-key",
    )
    routed = query.model_copy(update={"route_approval": signed_route})
    return sign_message(routed, private_key=private_key, signing_key_id="f1-key")


def signed_counterparty_query(
    *,
    private_key: str,
    max_hops: int = 1,
) -> Sec314bQuery:
    query = Sec314bQuery(
        sender_agent_id="federation.F1",
        sender_role=AgentRole.F1,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="bank_beta.A3",
        expires_at=expires_at(),
        nonce=f"nonce-{uuid4()}",
        requesting_investigator_id="investigator-alpha-1",
        requesting_bank_id=BankId.BANK_ALPHA,
        target_bank_ids=[BankId.BANK_BETA],
        query_shape=QueryShape.COUNTERPARTY_LINKAGE,
        query_payload=CounterpartyLinkagePayload(
            counterparty_hashes=[HASH_A],
            window_start=date(2026, 5, 1),
            window_end=date(2026, 5, 13),
            max_hops=max_hops,
        ),
        purpose_declaration=purpose(),
    )
    route = RouteApproval(
        query_id=query.query_id,
        route_kind=RouteKind.PEER_314B,
        approved_query_body_hash=approved_body_hash(query),
        requesting_bank_id=BankId.BANK_ALPHA,
        responding_bank_id=BankId.BANK_BETA,
        approved_by_agent_id="federation.F1",
        expires_at=query.expires_at,
    )
    signed_route = sign_model_signature(
        route,
        private_key=private_key,
        signing_key_id="f1-key",
    )
    routed = query.model_copy(update={"route_approval": signed_route})
    return sign_message(routed, private_key=private_key, signing_key_id="f1-key")


def signed_aggregate_peer_query(
    *,
    private_key: str,
    name_hashes: list[str],
    metrics: list[str],
    requested_rho: float,
) -> Sec314bQuery:
    query = Sec314bQuery(
        sender_agent_id="federation.F1",
        sender_role=AgentRole.F1,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="bank_beta.A3",
        expires_at=expires_at(),
        nonce=f"nonce-{uuid4()}",
        requesting_investigator_id="investigator-alpha-1",
        requesting_bank_id=BankId.BANK_ALPHA,
        target_bank_ids=[BankId.BANK_BETA],
        query_shape=QueryShape.AGGREGATE_ACTIVITY,
        query_payload=AggregateActivityPayload(
            name_hashes=name_hashes,
            window_start=date(2026, 5, 1),
            window_end=date(2026, 5, 13),
            metrics=metrics,
        ),
        purpose_declaration=purpose(),
        requested_rho_per_primitive=requested_rho,
    )
    route = RouteApproval(
        query_id=query.query_id,
        route_kind=RouteKind.PEER_314B,
        approved_query_body_hash=approved_body_hash(query),
        requesting_bank_id=BankId.BANK_ALPHA,
        responding_bank_id=BankId.BANK_BETA,
        approved_by_agent_id="federation.F1",
        expires_at=query.expires_at,
    )
    signed_route = sign_model_signature(
        route,
        private_key=private_key,
        signing_key_id="f1-key",
    )
    routed = query.model_copy(update={"route_approval": signed_route})
    return sign_message(routed, private_key=private_key, signing_key_id="f1-key")


def signed_local_request(*, private_key: str) -> LocalSiloContributionRequest:
    source_query_id = uuid4()
    request = LocalSiloContributionRequest(
        sender_agent_id="federation.F1",
        sender_role=AgentRole.F1,
        sender_bank_id=BankId.FEDERATION,
        recipient_agent_id="bank_alpha.A3",
        expires_at=expires_at(),
        nonce=f"nonce-{uuid4()}",
        source_query_id=source_query_id,
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
        route_approval=RouteApproval(
            query_id=source_query_id,
            route_kind=RouteKind.LOCAL_CONTRIBUTION,
            approved_query_body_hash="d" * 64,
            requesting_bank_id=BankId.BANK_ALPHA,
            responding_bank_id=BankId.BANK_ALPHA,
            approved_by_agent_id="federation.F1",
            expires_at=expires_at(),
        ),
    )
    route = request.route_approval.model_copy(
        update={"approved_query_body_hash": approved_body_hash(request)}
    )
    signed_route = sign_model_signature(
        route,
        private_key=private_key,
        signing_key_id="f1-key",
    )
    routed = request.model_copy(update={"route_approval": signed_route})
    return sign_message(routed, private_key=private_key, signing_key_id="f1-key")


def make_agent(
    *,
    bank_id: BankId = BankId.BANK_BETA,
    primitives: FakePrimitives | None = None,
    compose_with_llm: bool = False,
    stub_responses: list[object] | None = None,
    sign_responses: bool = False,
) -> tuple[A3SiloResponderAgent, FakePrimitives, InMemoryAuditEmitter, str]:
    key_pair = generate_key_pair("f1-key")
    response_key_pair = generate_key_pair("a3-key") if sign_responses else None
    fake = primitives or FakePrimitives(bank_id)
    audit = InMemoryAuditEmitter()
    llm = LLMClient(runtime().llm, stub_responses=stub_responses or [])
    agent = A3SiloResponderAgent(
        bank_id=bank_id,
        runtime=runtime(),
        primitives=fake,
        principal_allowlist=f1_allowlist(key_pair.public_key),
        replay_cache=ReplayCache(),
        audit=audit,
        llm=llm,
        compose_with_llm=compose_with_llm,
        response_private_key=(
            response_key_pair.private_key if response_key_pair is not None else None
        ),
        response_signing_key_id=(
            response_key_pair.signing_key_id if response_key_pair is not None else None
        ),
    )
    return agent, fake, audit, key_pair.private_key


def test_a3_accepts_signed_peer_query_and_invokes_entity_presence() -> None:
    agent, primitives, audit, private_key = make_agent()
    query = signed_peer_query(private_key=private_key)

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason is None
    assert response.responding_bank_id == BankId.BANK_BETA
    assert response.fields == {"entity_count": IntResponseValue(int=2)}
    assert response.rho_debited_total == 0.0
    assert len(primitives.calls) == 1
    assert audit.events[-1].kind == AuditEventKind.MESSAGE_SENT


def test_a3_rejects_replayed_peer_query_before_primitive_call() -> None:
    agent, primitives, _audit, private_key = make_agent()
    query = signed_peer_query(private_key=private_key)

    first = agent.run(A3TurnInput(request=query))
    second = agent.run(A3TurnInput(request=query))

    assert first.refusal_reason is None
    assert second.refusal_reason == "replay_detected"
    assert len(primitives.calls) == 1


def test_a3_rejects_tampered_signed_query_before_primitive_call() -> None:
    agent, primitives, _audit, private_key = make_agent(sign_responses=True)
    query = signed_peer_query(private_key=private_key)
    tampered = query.model_copy(update={"requested_rho_per_primitive": 0.5})

    response = agent.run(A3TurnInput(request=tampered))

    assert response.refusal_reason == "signature_invalid"
    assert response.signature is None
    assert primitives.calls == []


def test_a3_budget_exhaustion_returns_structural_refusal_without_llm() -> None:
    primitives = FakePrimitives(BankId.BANK_BETA)
    primitives.entity_result = PrimitiveResult(refusal_reason="budget_exhausted")
    agent, _primitives, audit, private_key = make_agent(primitives=primitives)
    query = signed_peer_query(private_key=private_key)

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason == "budget_exhausted"
    assert response.fields == {}
    assert response.provenance == []
    assert primitives.calls
    assert audit.events[-1].kind == AuditEventKind.MESSAGE_SENT
    assert audit.events[-1].status == "blocked"


def test_a3_rejects_zero_rho_for_dp_metric_without_primitive_call() -> None:
    agent, primitives, _audit, private_key = make_agent()
    query = signed_aggregate_peer_query(
        private_key=private_key,
        name_hashes=[HASH_A],
        metrics=["alert_count"],
        requested_rho=0.0,
    )

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason == "invalid_rho"
    assert primitives.calls == []


def test_a3_rejects_windowed_entity_presence_before_primitive_call() -> None:
    agent, primitives, _audit, private_key = make_agent()
    query = signed_peer_query(
        private_key=private_key,
        entity_window=(date(2026, 5, 1), date(2026, 5, 13)),
    )

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason == "unsupported_query_shape"
    assert primitives.calls == []


def test_a3_rejects_multi_hop_counterparty_query_before_primitive_call() -> None:
    agent, primitives, _audit, private_key = make_agent()
    query = signed_counterparty_query(private_key=private_key, max_hops=2)

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason == "unsupported_query_shape"
    assert primitives.calls == []


def test_a3_rejects_mixed_pattern_and_alert_metrics_without_partial_drop() -> None:
    agent, primitives, _audit, private_key = make_agent()
    query = signed_aggregate_peer_query(
        private_key=private_key,
        name_hashes=[HASH_A],
        metrics=["pattern_aggregate_for_f2", "alert_count"],
        requested_rho=0.04,
    )

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason == "unsupported_metric_combination"
    assert primitives.calls == []


def test_a3_rejects_multi_hash_alert_count_to_avoid_budget_fanout() -> None:
    agent, primitives, _audit, private_key = make_agent()
    query = signed_aggregate_peer_query(
        private_key=private_key,
        name_hashes=[HASH_A, HASH_B],
        metrics=["alert_count"],
        requested_rho=0.02,
    )

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason == "unsupported_metric_combination"
    assert primitives.calls == []


def test_a3_rejects_flow_plus_alert_metrics_before_partial_dp_debit() -> None:
    agent, primitives, _audit, private_key = make_agent()
    query = signed_aggregate_peer_query(
        private_key=private_key,
        name_hashes=[HASH_A],
        metrics=["flow_histogram", "alert_count"],
        requested_rho=0.02,
    )

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason == "unsupported_metric_combination"
    assert primitives.calls == []


def test_a3_rejects_expired_envelope_before_primitive_call() -> None:
    # Keep created_at within MAX_MESSAGE_CLOCK_SKEW so this test exercises the
    # expires_at <= now branch rather than the clock-skew guard. The
    # `expires_after_created` Message validator requires created_at < expires_at,
    # so created_at must be set slightly further in the past than expires_at.
    agent, primitives, _audit, private_key = make_agent()
    query = signed_peer_query(private_key=private_key)
    now = datetime.now(UTC)
    expired_query = query.model_copy(
        update={
            "created_at": now - timedelta(seconds=2),
            "expires_at": now - timedelta(seconds=1),
        }
    )
    signed_expired = sign_message(
        expired_query,
        private_key=private_key,
        signing_key_id="f1-key",
    )

    response = agent.run(A3TurnInput(request=signed_expired))

    assert response.refusal_reason == "envelope_invalid"
    assert primitives.calls == []


def test_a3_rejects_stale_created_at_outside_clock_skew_window() -> None:
    # Lock in the MAX_MESSAGE_CLOCK_SKEW guard added in principals._check_freshness.
    # created_at is 10 minutes in the past (well outside the 5-minute window) and
    # expires_at is still in the future, so the only thing that should refuse
    # this envelope is the clock-skew check, not expires_at.
    agent, primitives, _audit, private_key = make_agent()
    query = signed_peer_query(private_key=private_key)
    now = datetime.now(UTC)
    skewed_query = query.model_copy(
        update={
            "created_at": now - timedelta(minutes=10),
            "expires_at": now + timedelta(minutes=5),
        }
    )
    signed_skewed = sign_message(
        skewed_query,
        private_key=private_key,
        signing_key_id="f1-key",
    )

    response = agent.run(A3TurnInput(request=signed_skewed))

    assert response.refusal_reason == "envelope_invalid"
    assert primitives.calls == []


def test_a3_rejects_future_created_at_outside_clock_skew_window() -> None:
    # Symmetric to the stale-created_at case: a producer with a clock running
    # far ahead of the verifier should also be refused via the clock-skew guard.
    agent, primitives, _audit, private_key = make_agent()
    query = signed_peer_query(private_key=private_key)
    now = datetime.now(UTC)
    skewed_query = query.model_copy(
        update={
            "created_at": now + timedelta(minutes=10),
            "expires_at": now + timedelta(minutes=15),
        }
    )
    signed_skewed = sign_message(
        skewed_query,
        private_key=private_key,
        signing_key_id="f1-key",
    )

    response = agent.run(A3TurnInput(request=signed_skewed))

    assert response.refusal_reason == "envelope_invalid"
    assert primitives.calls == []


def test_a3_rejects_route_approval_body_hash_mismatch() -> None:
    agent, primitives, _audit, private_key = make_agent()
    query = signed_peer_query(private_key=private_key, stale_route_hash=True)

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason == "route_violation"
    assert primitives.calls == []


def test_a3_accepts_local_contribution_request_for_pattern_aggregate() -> None:
    agent, primitives, _audit, private_key = make_agent(bank_id=BankId.BANK_ALPHA)
    request = signed_local_request(private_key=private_key)

    response = agent.run(A3TurnInput(request=request))

    assert response.refusal_reason is None
    assert response.fields == {
        "edge_count_distribution": HistogramResponseValue(histogram=[1, 0, 2, 0]),
        "bucketed_flow_histogram": HistogramResponseValue(histogram=[0, 4, 1, 0, 0]),
    }
    assert response.rho_debited_total == 0.04
    assert primitives.calls == ["pattern:2026-05-01:2026-05-13:0.04"]


def test_a3_llm_composition_wraps_matching_bundle_deterministically() -> None:
    primitives = FakePrimitives(BankId.BANK_BETA)
    good_bundle = A3PrimitiveBundle(
        route_kind=RouteKind.PEER_314B.value,
        field_values={"entity_count": IntResponseValue(int=2)},
        provenance=primitives.entity_result.records,
    )
    agent, _primitives, audit, private_key = make_agent(
        primitives=primitives,
        compose_with_llm=True,
        stub_responses=[good_bundle],
    )
    query = signed_peer_query(private_key=private_key)

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason is None
    assert response.fields == good_bundle.field_values
    assert response.provenance == good_bundle.provenance
    assert response.in_reply_to == query.query_id
    assert response.sender_agent_id == "bank_beta.A3"
    assert agent.llm.call_count == 1
    assert audit.events[-1].kind == AuditEventKind.MESSAGE_SENT
    assert audit.events[-1].status == "ok"


def test_a3_rejects_llm_composition_that_changes_primitive_values() -> None:
    bad_bundle = A3PrimitiveBundle(
        route_kind=RouteKind.PEER_314B.value,
        field_values={"entity_count": IntResponseValue(int=99)},
        provenance=[primitive_record(field_name="entity_count")],
    )
    agent, _primitives, audit, private_key = make_agent(
        compose_with_llm=True,
        stub_responses=[bad_bundle, bad_bundle],
    )
    query = signed_peer_query(private_key=private_key)

    response = agent.run(A3TurnInput(request=query))

    assert response.refusal_reason == "provenance_violation"
    assert [event.status for event in audit.events if event.phase == "compose_response"] == [
        "retry",
        "blocked",
    ]
