"""Security-envelope exceptions."""

from __future__ import annotations


class SecurityEnvelopeError(ValueError):
    """Base error for signed-envelope validation failures."""


class SignatureInvalid(SecurityEnvelopeError):
    """Raised when a message body hash or signature is invalid."""


class PrincipalNotAllowed(SecurityEnvelopeError):
    """Raised when a verified principal is not allowed for the action."""


class ReplayDetected(SecurityEnvelopeError):
    """Raised when a nonce has already been accepted for a principal."""
