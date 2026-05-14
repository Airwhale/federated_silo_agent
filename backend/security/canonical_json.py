"""Canonical JSON helpers for signed message envelopes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel


def canonical_json_bytes(
    value: BaseModel | Mapping[str, Any],
    *,
    exclude_fields: set[str] | None = None,
) -> bytes:
    """Serialize a Pydantic model or mapping to stable UTF-8 JSON bytes.

    Hackathon scope uses Python's stable JSON serializer and drops None
    values so optional envelope fields can be populated incrementally while
    signing. Production should move this boundary to RFC 8785 JCS so float
    and null/absent semantics are independently specified.
    """
    payload = _jsonable_payload(value, exclude_fields=exclude_fields or set())
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_json_hash(
    value: BaseModel | Mapping[str, Any],
    *,
    exclude_fields: set[str] | None = None,
) -> str:
    """Return a SHA-256 hex digest over canonical JSON bytes."""
    return hashlib.sha256(
        canonical_json_bytes(value, exclude_fields=exclude_fields)
    ).hexdigest()


def _jsonable_payload(
    value: BaseModel | Mapping[str, Any],
    *,
    exclude_fields: set[str],
) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(
            mode="json",
            exclude=exclude_fields,
            exclude_none=True,
        )
    return {
        key: item
        for key, item in value.items()
        if key not in exclude_fields and item is not None
    }
