"""Security-envelope helpers for signed demo agent traffic."""

from backend.security.canonical_json import canonical_json_bytes, canonical_json_hash
from backend.security.exceptions import (
    PrincipalNotAllowed,
    ReplayDetected,
    SecurityEnvelopeError,
    SignatureInvalid,
)
from backend.security.principals import (
    PrincipalAllowlist,
    PrincipalAllowlistEntry,
    VerifiedMessage,
    VerifiedPrincipal,
)
from backend.security.replay import (
    ReplayCache,
    ReplayCacheEntrySnapshot,
    ReplayCacheSnapshot,
)
from backend.security.signing import (
    SigningKeyPair,
    approved_body_hash,
    body_hash,
    generate_key_pair,
    sign_message,
    sign_model_signature,
    verify_message_signature,
    verify_model_signature,
)

__all__ = [
    "PrincipalAllowlist",
    "PrincipalAllowlistEntry",
    "PrincipalNotAllowed",
    "ReplayCache",
    "ReplayCacheEntrySnapshot",
    "ReplayCacheSnapshot",
    "ReplayDetected",
    "SecurityEnvelopeError",
    "SignatureInvalid",
    "SigningKeyPair",
    "VerifiedMessage",
    "VerifiedPrincipal",
    "approved_body_hash",
    "body_hash",
    "canonical_json_bytes",
    "canonical_json_hash",
    "generate_key_pair",
    "sign_message",
    "sign_model_signature",
    "verify_message_signature",
    "verify_model_signature",
]
