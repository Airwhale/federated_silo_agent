from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.security import (
    PrincipalAllowlist,
    PrincipalAllowlistEntry,
    PrincipalNotAllowed,
    ReplayCache,
    ReplayDetected,
    SecurityEnvelopeError,
    SignatureInvalid,
    approved_body_hash,
    generate_key_pair,
    sign_message,
    sign_model_signature,
)
from shared.enums import AgentRole, BankId, MessageType, QueryShape, RouteKind, TypologyCode
from shared.messages import (
    AggregateActivityPayload,
    PurposeDeclaration,
    RouteApproval,
    Sec314bQuery,
)


HASH_A = "a" * 16


def expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=5)


def f1_entry(public_key: str, signing_key_id: str = "f1-key") -> PrincipalAllowlistEntry:
    return PrincipalAllowlistEntry(
        agent_id="federation.F1",
        role=AgentRole.F1,
        bank_id=BankId.FEDERATION,
        signing_key_id=signing_key_id,
        public_key=public_key,
        allowed_message_types=[
            MessageType.SEC314B_QUERY.value,
            MessageType.LOCAL_SILO_CONTRIBUTION_REQUEST.value,
        ],
        allowed_recipients=["bank_beta.A3", "bank_alpha.A3"],
        allowed_routes=[RouteKind.PEER_314B, RouteKind.LOCAL_CONTRIBUTION],
    )


def a2_entry(public_key: str, signing_key_id: str = "a2-key") -> PrincipalAllowlistEntry:
    return PrincipalAllowlistEntry(
        agent_id="bank_alpha.A2",
        role=AgentRole.A2,
        bank_id=BankId.BANK_ALPHA,
        signing_key_id=signing_key_id,
        public_key=public_key,
        allowed_message_types=[MessageType.SEC314B_QUERY.value],
        allowed_recipients=["federation.F1", "bank_beta.A3"],
        allowed_routes=[RouteKind.PEER_314B],
    )


def bank_scoped_f1_entry(
    public_key: str,
    signing_key_id: str = "bank-f1-key",
) -> PrincipalAllowlistEntry:
    return PrincipalAllowlistEntry(
        agent_id="bank_alpha.F1",
        role=AgentRole.F1,
        bank_id=BankId.BANK_ALPHA,
        signing_key_id=signing_key_id,
        public_key=public_key,
        allowed_message_types=[],
        allowed_recipients=[],
        allowed_routes=[RouteKind.PEER_314B],
    )


def query_for_beta() -> Sec314bQuery:
    return Sec314bQuery(
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
            name_hashes=[HASH_A],
            window_start=datetime(2026, 5, 1, tzinfo=UTC).date(),
            window_end=datetime(2026, 5, 13, tzinfo=UTC).date(),
            metrics=["alert_count"],
        ),
        purpose_declaration=PurposeDeclaration(
            typology_code=TypologyCode.STRUCTURING,
            suspicion_rationale="Repeated hash activity suggests structuring.",
        ),
        requested_rho_per_primitive=0.02,
    )


def signed_query_for_beta() -> tuple[Sec314bQuery, PrincipalAllowlist, str]:
    key_pair = generate_key_pair("f1-key")
    query = query_for_beta()
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
        private_key=key_pair.private_key,
        signing_key_id=key_pair.signing_key_id,
    )
    routed_query = query.model_copy(update={"route_approval": signed_route})
    signed = sign_message(
        routed_query,
        private_key=key_pair.private_key,
        signing_key_id=key_pair.signing_key_id,
    )
    return signed, PrincipalAllowlist([f1_entry(key_pair.public_key)]), key_pair.public_key


def test_signed_message_verifies_identity_route_and_replay_once() -> None:
    signed, allowlist, _public_key = signed_query_for_beta()
    replay = ReplayCache()

    verified = allowlist.verify_message(signed, replay_cache=replay)
    snapshot = replay.to_snapshot()

    assert verified.principal.agent_id == "federation.F1"
    assert verified.principal.role == AgentRole.F1
    assert verified.body_hash == signed.body_hash
    assert len(snapshot.entries) == 1
    assert snapshot.entries[0].principal_id == "federation.F1"
    assert snapshot.entries[0].nonce_hash != signed.nonce
    assert len(snapshot.entries[0].nonce_hash) == 16
    assert snapshot.entries[0].first_seen_at < snapshot.entries[0].expires_at

    with pytest.raises(ReplayDetected):
        allowlist.verify_message(signed, replay_cache=replay)


def test_tampered_signed_message_fails_body_hash_check() -> None:
    signed, allowlist, _public_key = signed_query_for_beta()
    tampered = signed.model_copy(update={"requested_rho_per_primitive": 0.03})

    with pytest.raises(SignatureInvalid):
        allowlist.verify_message(tampered)


def test_unknown_signing_key_is_not_allowed() -> None:
    signed, _allowlist, _public_key = signed_query_for_beta()
    empty_allowlist = PrincipalAllowlist([])

    with pytest.raises(PrincipalNotAllowed):
        empty_allowlist.verify_message(signed)


def test_tampered_declared_sender_fails_body_hash_before_identity_check() -> None:
    signed, allowlist, _public_key = signed_query_for_beta()
    wrong_sender = signed.model_copy(update={"sender_agent_id": "federation.other"})

    with pytest.raises(SignatureInvalid):
        allowlist.verify_message(wrong_sender)


def test_message_created_at_must_be_recent() -> None:
    now = datetime.now(UTC)
    key_pair = generate_key_pair("f1-key")
    allowlist = PrincipalAllowlist([f1_entry(key_pair.public_key)])
    old_query = query_for_beta().model_copy(
        update={
            "created_at": now - timedelta(minutes=10),
            "expires_at": now + timedelta(minutes=5),
        }
    )
    future_query = query_for_beta().model_copy(
        update={
            "created_at": now + timedelta(minutes=10),
            "expires_at": now + timedelta(minutes=15),
        }
    )

    for query in (old_query, future_query):
        signed = sign_message(
            query,
            private_key=key_pair.private_key,
            signing_key_id=key_pair.signing_key_id,
        )
        with pytest.raises(SecurityEnvelopeError, match="outside allowed clock skew"):
            allowlist.verify_message(signed, now=now)


def test_route_approval_signature_verifies_with_allowlisted_f1() -> None:
    signed, allowlist, _public_key = signed_query_for_beta()

    verified = allowlist.verify_route_approval(signed.route_approval)

    assert verified.agent_id == "federation.F1"
    assert verified.bank_id == BankId.FEDERATION


def test_route_approval_signed_by_non_f1_key_is_rejected() -> None:
    signed, _allowlist, _public_key = signed_query_for_beta()
    a2_key = generate_key_pair("a2-key")
    allowlist = PrincipalAllowlist(
        [
            f1_entry(generate_key_pair("unused-f1").public_key, "unused-f1"),
            a2_entry(a2_key.public_key),
        ]
    )
    wrong_role_route = sign_model_signature(
        signed.route_approval,
        private_key=a2_key.private_key,
        signing_key_id=a2_key.signing_key_id,
    )

    with pytest.raises(PrincipalNotAllowed):
        allowlist.verify_route_approval(wrong_role_route)


def test_route_approval_signed_by_bank_scoped_f1_is_rejected() -> None:
    signed, _allowlist, _public_key = signed_query_for_beta()
    bank_f1_key = generate_key_pair("bank-f1-key")
    allowlist = PrincipalAllowlist([bank_scoped_f1_entry(bank_f1_key.public_key)])
    bank_scoped_route = signed.route_approval.model_copy(
        update={"approved_by_agent_id": "bank_alpha.F1"}
    )
    signed_route = sign_model_signature(
        bank_scoped_route,
        private_key=bank_f1_key.private_key,
        signing_key_id=bank_f1_key.signing_key_id,
    )

    with pytest.raises(PrincipalNotAllowed, match="wrong bank scope"):
        allowlist.verify_route_approval(signed_route)


def test_replay_cache_uses_tuple_keys_not_delimiter_joined_keys() -> None:
    replay = ReplayCache()
    expiry = expires_at()

    replay.check_and_store(
        principal_id="bank_alpha.A2:federation.F1",
        nonce="abc",
        expires_at=expiry,
    )
    replay.check_and_store(
        principal_id="bank_alpha.A2",
        nonce="federation.F1:abc",
        expires_at=expiry,
    )

    assert len(replay.to_snapshot().entries) == 2


def test_replay_cache_snapshot_prunes_expired_entries() -> None:
    replay = ReplayCache()
    replay.check_and_store(
        principal_id="federation.F1",
        nonce="expired",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    assert replay.to_snapshot().entries == []


def test_signing_key_pair_repr_does_not_expose_private_key() -> None:
    key_pair = generate_key_pair("demo-key")

    assert key_pair.private_key not in repr(key_pair)
