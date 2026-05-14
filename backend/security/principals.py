"""Principal allowlist checks for signed agent messages."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from backend.security.exceptions import (
    PrincipalNotAllowed,
    SecurityEnvelopeError,
    SignatureInvalid,
)
from backend.security.replay import ReplayCache
from backend.security.signing import (
    load_public_key,
    verify_message_signature,
    verify_model_signature,
)
from shared.enums import AgentRole, BankId, RouteKind


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
MAX_MESSAGE_CLOCK_SKEW = timedelta(minutes=5)


class PrincipalAllowlistEntry(BaseModel):
    """One signed principal and the routes it may use."""

    agent_id: NonEmptyStr
    role: AgentRole
    bank_id: BankId
    signing_key_id: NonEmptyStr
    public_key: NonEmptyStr
    allowed_message_types: list[NonEmptyStr]
    allowed_recipients: list[NonEmptyStr]
    allowed_routes: list[RouteKind] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("public_key")
    @classmethod
    def public_key_must_load(cls, value: str) -> str:
        """Probe-load the key at construction so config errors fail at startup.

        Without this validator a malformed `public_key` (e.g. valid base64 but
        wrong byte length for Ed25519) would only surface mid-request when
        `Ed25519PublicKey.from_public_bytes` raises a bare `ValueError`, which
        escapes `A3.run`'s `SecurityEnvelopeError`/`InvalidAgentInput` exception
        chain and breaks the "A3 always returns a Sec314bResponse" contract.
        Probing the key once at allowlist-construction time keeps the request
        path clean: malformed envelopes still raise `SignatureInvalid` from
        per-request verification, while operator config errors raise
        `pydantic.ValidationError` at startup with a clear message.
        """
        try:
            load_public_key(value)
        except SignatureInvalid as exc:
            raise ValueError(
                f"public_key is not valid base64-encoded Ed25519 bytes: {exc}"
            ) from exc
        except ValueError as exc:
            # cryptography.hazmat raises ValueError for wrong-length raw keys.
            raise ValueError(f"public_key is not a valid Ed25519 raw key: {exc}") from exc
        return value


class VerifiedPrincipal(BaseModel):
    """Principal resolved from a verified signature."""

    agent_id: str
    role: AgentRole
    bank_id: BankId
    signing_key_id: str

    model_config = ConfigDict(extra="forbid", strict=True)


class VerifiedMessage(BaseModel):
    """Signed message plus the verified principal that produced it."""

    principal: VerifiedPrincipal
    body_hash: str

    model_config = ConfigDict(extra="forbid", strict=True)


class PrincipalAllowlist:
    """Versioned runtime allowlist for demo agent principals."""

    def __init__(self, entries: list[PrincipalAllowlistEntry]) -> None:
        by_key: dict[str, PrincipalAllowlistEntry] = {}
        for entry in entries:
            if entry.signing_key_id in by_key:
                raise ValueError(f"duplicate signing_key_id: {entry.signing_key_id}")
            by_key[entry.signing_key_id] = entry
        self._entries = by_key

    def resolve(self, signing_key_id: str | None) -> PrincipalAllowlistEntry:
        if not signing_key_id:
            raise PrincipalNotAllowed("missing signing_key_id")
        try:
            return self._entries[signing_key_id]
        except KeyError as exc:
            raise PrincipalNotAllowed("signing_key_id is not allowlisted") from exc

    def verify_message(
        self,
        message: Any,
        *,
        replay_cache: ReplayCache | None = None,
        now: datetime | None = None,
    ) -> VerifiedMessage:
        """Verify signature, declared identity, allowlist, expiry, and replay."""
        entry = self.resolve(getattr(message, "signing_key_id", None))
        verify_message_signature(message, public_key=entry.public_key)
        self._check_declared_identity(message, entry)
        self._check_message_allowance(message, entry)
        self._check_freshness(message, now=now)
        if replay_cache is not None:
            replay_cache.check_and_store(
                principal_id=entry.agent_id,
                nonce=message.nonce,
                expires_at=message.expires_at,
                now=now,
            )
        return VerifiedMessage(
            principal=VerifiedPrincipal(
                agent_id=entry.agent_id,
                role=entry.role,
                bank_id=entry.bank_id,
                signing_key_id=entry.signing_key_id,
            ),
            body_hash=message.body_hash,
        )

    def verify_route_approval(
        self,
        route_approval: Any,
        *,
        expected_role: AgentRole = AgentRole.F1,
        expected_bank_id: BankId = BankId.FEDERATION,
        now: datetime | None = None,
    ) -> VerifiedPrincipal:
        """Verify an F1-signed route approval object."""
        entry = self.resolve(getattr(route_approval, "signing_key_id", None))
        verify_model_signature(route_approval, public_key=entry.public_key)
        if entry.role != expected_role:
            raise PrincipalNotAllowed("route approval signer has wrong role")
        if entry.bank_id != expected_bank_id:
            raise PrincipalNotAllowed("route approval signer has wrong bank scope")
        if route_approval.approved_by_agent_id != entry.agent_id:
            raise PrincipalNotAllowed(
                "route approval signer does not match approved_by_agent_id"
            )
        if route_approval.route_kind not in entry.allowed_routes:
            raise PrincipalNotAllowed("route approval kind is not allowed")
        now_value = _normalize_now(now)
        if route_approval.expires_at <= now_value:
            raise SecurityEnvelopeError("route approval is expired")
        return VerifiedPrincipal(
            agent_id=entry.agent_id,
            role=entry.role,
            bank_id=entry.bank_id,
            signing_key_id=entry.signing_key_id,
        )

    def _check_declared_identity(
        self,
        message: Any,
        entry: PrincipalAllowlistEntry,
    ) -> None:
        if getattr(message, "sender_agent_id", None) != entry.agent_id:
            raise PrincipalNotAllowed("declared sender_agent_id does not match key")
        if getattr(message, "sender_role", None) != entry.role:
            raise PrincipalNotAllowed("declared sender_role does not match key")
        if getattr(message, "sender_bank_id", None) != entry.bank_id:
            raise PrincipalNotAllowed("declared sender_bank_id does not match key")

    def _check_message_allowance(
        self,
        message: Any,
        entry: PrincipalAllowlistEntry,
    ) -> None:
        message_type = getattr(message, "message_type", None)
        if message_type not in entry.allowed_message_types:
            raise PrincipalNotAllowed("message type is not allowed for principal")
        recipient = getattr(message, "recipient_agent_id", None)
        if "*" not in entry.allowed_recipients and recipient not in entry.allowed_recipients:
            raise PrincipalNotAllowed("recipient is not allowed for principal")
        route_kind = _route_kind(message)
        if route_kind is not None and route_kind not in entry.allowed_routes:
            raise PrincipalNotAllowed("route kind is not allowed for principal")

    def _check_freshness(self, message: Any, *, now: datetime | None) -> None:
        if not getattr(message, "nonce", None):
            raise SecurityEnvelopeError("missing nonce")
        if getattr(message, "expires_at", None) is None:
            raise SecurityEnvelopeError("missing expires_at")
        now_value = _normalize_now(now)
        created_at = getattr(message, "created_at", None)
        if created_at is None:
            raise SecurityEnvelopeError("missing created_at")
        created_at = _normalize_timestamp(created_at, field_name="created_at")
        expires_at = _normalize_timestamp(message.expires_at, field_name="expires_at")
        if abs(created_at - now_value) > MAX_MESSAGE_CLOCK_SKEW:
            raise SecurityEnvelopeError("message created_at outside allowed clock skew")
        if expires_at <= now_value:
            raise SecurityEnvelopeError("message is expired")


def _route_kind(message: Any) -> RouteKind | None:
    route_approval = getattr(message, "route_approval", None)
    if route_approval is None:
        return None
    return route_approval.route_kind


def _normalize_now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    return _normalize_timestamp(value, field_name="now")


def _normalize_timestamp(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise SecurityEnvelopeError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
