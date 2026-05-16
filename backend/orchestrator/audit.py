"""In-memory audit channel for local P15 orchestration."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from backend.agents.base import AuditEmitter, RuntimeAuditEvent
from shared.enums import AgentRole, AuditEventKind


@dataclass(frozen=True)
class AuditChainEntry:
    """One runtime audit event plus its hash-chain metadata."""

    event: RuntimeAuditEvent
    previous_hash: str | None
    event_hash: str


@dataclass
class OrchestratorAuditRecorder(AuditEmitter):
    """Thread-safe runtime audit sink with tamper-evident hashes."""

    _entries: list[AuditChainEntry] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def emit(self, event: RuntimeAuditEvent) -> None:
        with self._lock:
            previous_hash = self._entries[-1].event_hash if self._entries else None
            event_hash = _event_hash(event, previous_hash)
            self._entries.append(
                AuditChainEntry(
                    event=event,
                    previous_hash=previous_hash,
                    event_hash=event_hash,
                )
            )

    def emit_orchestrator_event(
        self,
        *,
        run_id: str,
        phase: str,
        status: str,
        detail: str,
    ) -> None:
        self.emit(
            RuntimeAuditEvent(
                event_id=str(uuid4()),
                kind=AuditEventKind.MESSAGE_SENT,
                run_id=run_id,
                node_id="local-orchestrator",
                agent_id="orchestrator",
                role=AgentRole.ORCHESTRATOR,
                phase=phase,
                status=status,
                detail=detail,
                model_name="deterministic_orchestrator",
                # The hash-chain list order is the authoritative sequence;
                # timestamps are wall-clock observability fields only.
                created_at=datetime.now(UTC),
            )
        )

    def snapshot(self) -> list[AuditChainEntry]:
        with self._lock:
            return list(self._entries)

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def latest_hash(self) -> str | None:
        with self._lock:
            if not self._entries:
                return None
            return self._entries[-1].event_hash


def _event_hash(event: RuntimeAuditEvent, previous_hash: str | None) -> str:
    payload = {
        "event": event.model_dump(mode="json"),
        "previous_hash": previous_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
