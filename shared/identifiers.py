"""Shared identifier transformation helpers."""

from __future__ import annotations

import hashlib


def hash_identifier(value: str) -> str:
    """Return a deterministic SHA-256 hex hash for a local identifier."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_cross_bank_hash_token(value: str) -> bool:
    """Return whether a value matches the demo cross-bank token shape."""
    return len(value) == 16 and all(char in "0123456789abcdef" for char in value)
