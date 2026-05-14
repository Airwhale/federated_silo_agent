"""In-memory replay cache for signed demo envelopes."""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.security.exceptions import ReplayDetected


class ReplayCacheEntrySnapshot(BaseModel):
    """Redacted replay-cache entry for UI inspection."""

    principal_id: str
    nonce_hash: str
    first_seen_at: datetime
    expires_at: datetime

    model_config = ConfigDict(extra="forbid", strict=True)


class _ReplayCacheEntry(BaseModel):
    principal_id: str
    nonce: str
    first_seen_at: datetime
    expires_at: datetime

    model_config = ConfigDict(extra="forbid", strict=True)

    def to_snapshot(self) -> ReplayCacheEntrySnapshot:
        return ReplayCacheEntrySnapshot(
            principal_id=self.principal_id,
            nonce_hash=_nonce_hash(self.nonce),
            first_seen_at=self.first_seen_at,
            expires_at=self.expires_at,
        )


class ReplayCacheSnapshot(BaseModel):
    """Redacted replay-cache state for UI inspection."""

    entries: list[ReplayCacheEntrySnapshot] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", strict=True)


class ReplayCache:
    """Thread-safe nonce cache keyed by verified principal and nonce."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _ReplayCacheEntry] = {}
        self._lock = threading.Lock()

    def check_and_store(
        self,
        *,
        principal_id: str,
        nonce: str,
        expires_at: datetime,
        now: datetime | None = None,
    ) -> None:
        """Record one nonce or raise if it has already been accepted."""
        now = _normalize_now(now)
        key = (principal_id, nonce)
        with self._lock:
            self._drop_expired(now)
            if key in self._entries:
                raise ReplayDetected("nonce has already been accepted")
            self._entries[key] = _ReplayCacheEntry(
                principal_id=principal_id,
                nonce=nonce,
                first_seen_at=now,
                expires_at=expires_at,
            )

    def to_snapshot(self) -> ReplayCacheSnapshot:
        with self._lock:
            self._drop_expired(_normalize_now(None))
            return ReplayCacheSnapshot(
                entries=[entry.to_snapshot() for entry in self._entries.values()]
            )

    def _drop_expired(self, now: datetime) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for key in expired:
            del self._entries[key]


def _nonce_hash(nonce: str) -> str:
    return hashlib.sha256(nonce.encode("utf-8")).hexdigest()[:16]


def _normalize_now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)
