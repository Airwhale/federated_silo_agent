"""Shared identifier transformation helpers."""

from __future__ import annotations

import hashlib


def hash_identifier(value: str) -> str:
    """Return a deterministic SHA-256 hex hash for a local identifier."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
