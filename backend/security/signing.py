"""Ed25519 signing helpers for demo message envelopes."""

from __future__ import annotations

import base64
from typing import TypeVar

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from pydantic import BaseModel, ConfigDict, Field

from backend.security.canonical_json import canonical_json_bytes, canonical_json_hash
from backend.security.exceptions import SignatureInvalid


SignedModelT = TypeVar("SignedModelT", bound=BaseModel)

ENVELOPE_HASH_EXCLUDES = {"body_hash", "signature"}
APPROVED_BODY_HASH_EXCLUDES = ENVELOPE_HASH_EXCLUDES | {
    "route_approval",
    "signing_key_id",
}
SIGNATURE_EXCLUDES = {"signature"}


class SigningKeyPair(BaseModel):
    """Base64-encoded raw Ed25519 key material for demo fixtures."""

    signing_key_id: str
    private_key: str = Field(repr=False)
    public_key: str

    model_config = ConfigDict(extra="forbid", strict=True)


def generate_key_pair(signing_key_id: str) -> SigningKeyPair:
    """Generate one Ed25519 key pair for tests or local demo setup."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )
    return SigningKeyPair(
        signing_key_id=signing_key_id,
        private_key=_b64(private_bytes),
        public_key=_b64(public_bytes),
    )


def load_private_key(value: str) -> Ed25519PrivateKey:
    """Load a raw base64 Ed25519 private key."""
    return Ed25519PrivateKey.from_private_bytes(_unb64(value))


def load_public_key(value: str) -> Ed25519PublicKey:
    """Load a raw base64 Ed25519 public key."""
    return Ed25519PublicKey.from_public_bytes(_unb64(value))


def body_hash(model: BaseModel) -> str:
    """Hash a message body with envelope hash/signature fields excluded."""
    return canonical_json_hash(model, exclude_fields=ENVELOPE_HASH_EXCLUDES)


def approved_body_hash(model: BaseModel) -> str:
    """Hash an approved query body with route approval and envelope fields excluded."""
    return canonical_json_hash(
        model,
        exclude_fields=APPROVED_BODY_HASH_EXCLUDES,
    )


def sign_message(
    model: SignedModelT,
    *,
    private_key: str | Ed25519PrivateKey,
    signing_key_id: str,
) -> SignedModelT:
    """Return a copy of `model` with body hash, key id, and signature set."""
    key = (
        load_private_key(private_key)
        if isinstance(private_key, str)
        else private_key
    )
    with_key = model.model_copy(
        update={
            "body_hash": None,
            "signing_key_id": signing_key_id,
            "signature": None,
        }
    )
    with_hash = model.model_copy(
        update={
            "body_hash": body_hash(with_key),
            "signing_key_id": signing_key_id,
            "signature": None,
        }
    )
    signature = key.sign(
        canonical_json_bytes(with_hash, exclude_fields=SIGNATURE_EXCLUDES)
    )
    return with_hash.model_copy(update={"signature": _b64(signature)})


def verify_message_signature(
    model: BaseModel,
    *,
    public_key: str | Ed25519PublicKey,
) -> None:
    """Validate body hash and Ed25519 signature for a signed message."""
    expected_hash = getattr(model, "body_hash", None)
    actual_hash = body_hash(model)
    if expected_hash != actual_hash:
        raise SignatureInvalid("message body_hash does not match canonical body")
    verify_model_signature(model, public_key=public_key)


def sign_model_signature(
    model: SignedModelT,
    *,
    private_key: str | Ed25519PrivateKey,
    signing_key_id: str,
) -> SignedModelT:
    """Return a copy of a non-envelope model with signing metadata set."""
    key = (
        load_private_key(private_key)
        if isinstance(private_key, str)
        else private_key
    )
    with_key = model.model_copy(
        update={
            "signing_key_id": signing_key_id,
            "signature": None,
        }
    )
    signature = key.sign(
        canonical_json_bytes(with_key, exclude_fields=SIGNATURE_EXCLUDES)
    )
    return with_key.model_copy(update={"signature": _b64(signature)})


def verify_model_signature(
    model: BaseModel,
    *,
    public_key: str | Ed25519PublicKey,
) -> None:
    """Validate Ed25519 signature over a model with a signature field."""
    signature = getattr(model, "signature", None)
    if not signature:
        raise SignatureInvalid("missing signature")
    key = load_public_key(public_key) if isinstance(public_key, str) else public_key
    try:
        key.verify(
            _unb64(signature),
            canonical_json_bytes(model, exclude_fields=SIGNATURE_EXCLUDES),
        )
    except InvalidSignature as exc:
        raise SignatureInvalid("signature verification failed") from exc


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except ValueError as exc:
        raise SignatureInvalid("key or signature is not valid base64") from exc
