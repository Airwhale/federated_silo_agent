"""F3 sanctions and PEP screening over cross-bank hash tokens."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend import BACKEND_ROOT
from backend.agents.base import Agent, AuditEmitter, InvalidAgentInput
from backend.agents.llm_client import LLMClient
from backend.runtime.context import AgentRuntimeContext, TrustDomain
from shared.enums import AgentRole, AuditEventKind, BankId
from shared.messages import (
    CrossBankHashToken,
    SanctionsCheckRequest,
    SanctionsCheckResponse,
    SanctionsResult,
)


PROJECT_ROOT = BACKEND_ROOT.parent
PROMPT_PATH = BACKEND_ROOT / "agents" / "prompts" / "f3_system.md"
DEFAULT_WATCHLIST_PATH = PROJECT_ROOT / "data" / "mock_sdn_list.json"
F3_AGENT_ID = "federation.F3"


class WatchlistSource(StrEnum):
    """Sources supported by the demo mock watchlist."""

    SDN = "SDN"
    PEP = "PEP"


class WatchlistEntry(BaseModel):
    """One internal watchlist entry.

    `notes` is for local demo explainability only. F3 never returns it.
    """

    name_hash: CrossBankHashToken
    source: WatchlistSource
    notes: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class WatchlistDocument(BaseModel):
    """Validated mock sanctions/PEP list stored on disk."""

    entities: list[WatchlistEntry] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    @model_validator(mode="after")
    def no_duplicate_source_entries(self: WatchlistDocument) -> WatchlistDocument:
        seen: set[tuple[str, WatchlistSource]] = set()
        for entry in self.entities:
            key = (entry.name_hash, entry.source)
            if key in seen:
                raise ValueError(f"duplicate watchlist entry for {entry.name_hash}/{entry.source}")
            seen.add(key)
        return self


class WatchlistFlags(BaseModel):
    """Internal aggregate flags for one hash token."""

    sdn_match: bool = False
    pep_relation: bool = False

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class SanctionsWatchlist:
    """Read-only lookup table built from the mock watchlist document."""

    def __init__(self, document: WatchlistDocument) -> None:
        flags: dict[str, WatchlistFlags] = {}
        for entry in document.entities:
            current = flags.setdefault(entry.name_hash, WatchlistFlags())
            if entry.source == WatchlistSource.SDN:
                current.sdn_match = True
            if entry.source == WatchlistSource.PEP:
                current.pep_relation = True
        self._flags = flags

    @classmethod
    def from_path(cls, path: Path = DEFAULT_WATCHLIST_PATH) -> SanctionsWatchlist:
        try:
            document = WatchlistDocument.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise ValueError(f"invalid sanctions watchlist at {path}: {exc}") from exc
        return cls(document)

    def screen(self, entity_hash: CrossBankHashToken) -> SanctionsResult:
        flags = self._flags.get(entity_hash, WatchlistFlags())
        return SanctionsResult(
            sdn_match=flags.sdn_match,
            pep_relation=flags.pep_relation,
        )

    @property
    def size(self) -> int:
        """Total unique-hash entries in the loaded watchlist.

        Used by the UI snapshot to surface "screener loaded N hashes"
        without disclosing list contents. Intentionally not broken out
        by source (SDN vs PEP); the per-source counts would leak the
        shape of each list, which the F3 non-disclosure contract treats
        as part of "list contents".
        """
        return len(self._flags)


@lru_cache(maxsize=8)
def load_prompt(path: Path = PROMPT_PATH) -> str:
    """Load the versioned F3 prompt for future LLM adjudication."""
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=8)
def load_watchlist(path: Path = DEFAULT_WATCHLIST_PATH) -> SanctionsWatchlist:
    """Load the static watchlist once per process for agent instances."""
    return SanctionsWatchlist.from_path(path)


class F3SanctionsAgent(Agent[SanctionsCheckRequest, SanctionsCheckResponse]):
    """Federation-layer sanctions/PEP screener.

    F3 receives only cross-bank hash tokens. It does not receive raw names and
    therefore performs exact token screening against the local mock list.
    """

    agent_id = F3_AGENT_ID
    role = AgentRole.F3
    bank_id = BankId.FEDERATION
    input_schema = SanctionsCheckRequest
    output_schema = SanctionsCheckResponse
    declared_intent = "federation_sanctions_pep_screening"

    def __init__(
        self,
        *,
        runtime: AgentRuntimeContext,
        watchlist_path: Path = DEFAULT_WATCHLIST_PATH,
        watchlist: SanctionsWatchlist | None = None,
        llm: LLMClient | None = None,
        audit: AuditEmitter | None = None,
    ) -> None:
        if runtime.trust_domain != TrustDomain.FEDERATION:
            raise ValueError("F3 must run in the federation trust domain")
        self.system_prompt = load_prompt()
        self.watchlist = watchlist or load_watchlist(watchlist_path.resolve())
        super().__init__(runtime=runtime, llm=llm, audit=audit)

    def run(self, input_data: SanctionsCheckRequest | object) -> SanctionsCheckResponse:
        """Screen supplied hash tokens and return boolean-only match flags.

        This agent is intentionally **deterministic**. The override does not
        call ``self.llm`` and does not pass through the base class's
        ``_run_bypass`` / ``_run_llm`` flow; screening is exact hash lookup
        against the in-memory ``SanctionsWatchlist`` and nothing more. The
        ``self.system_prompt`` field is loaded for parity with the
        ``Agent`` base class interface and to give the future LLM-backed
        adjudication path (P14/P15) a single source of truth for prompt
        text, but it is unused at runtime today.

        Why deterministic: an LLM here would be both a hallucination risk
        (false positives or false negatives on a binary screening result)
        and a list-content leak risk (the model could be coerced into
        echoing watchlist entries it was shown). Schema separation between
        ``WatchlistEntry`` (internal, has ``notes`` / ``source``) and
        ``SanctionsResult`` (external, just two booleans) keeps the
        non-disclosure contract structural rather than policy-policed.

        Audit side-channel note (deferred to P14 LT policy): when at least
        one hash matches, a ``BYPASS_TRIGGERED`` event with ``rule_name``
        ``F3-B1`` or ``F3-B2`` lands in the audit trail. When no hash
        matches, only the generic ``MESSAGE_SENT`` event fires. The
        binary "any hit?" signal therefore appears twice -- once in the
        response payload (per-hash flags), once in the audit-event
        presence pattern. That is acceptable for the demo so long as the
        audit log is only readable by F5 (compliance auditor) and not
        echoed back to the requesting investigator. P14 LT policy needs
        to encode that read constraint.
        """
        request = self._validate_input(input_data)
        self._validate_route(request)

        unique_entity_hashes = dict.fromkeys(request.entity_hashes)
        results = {
            entity_hash: self.watchlist.screen(entity_hash)
            for entity_hash in unique_entity_hashes
        }
        response = SanctionsCheckResponse(
            sender_agent_id=self.agent_id,
            sender_role=self.role,
            sender_bank_id=self.bank_id,
            recipient_agent_id=request.sender_agent_id,
            in_reply_to=request.message_id,
            results=results,
        )

        # Two independent ``any(...)`` scans because SDN and PEP are
        # separately flagged events; a single hash can produce both, and
        # we want both audit entries to fire in that case so downstream
        # F5 / F4 see the full bypass picture.
        if any(result.sdn_match for result in results.values()):
            self._emit(
                kind=AuditEventKind.BYPASS_TRIGGERED,
                phase="screen",
                status="ok",
                rule_name="F3-B1",
                bypass_name="F3-B1",
                detail="Exact hash match against mock SDN list.",
                model_name="deterministic_watchlist",
            )
        if any(result.pep_relation for result in results.values()):
            self._emit(
                kind=AuditEventKind.BYPASS_TRIGGERED,
                phase="screen",
                status="ok",
                rule_name="F3-B2",
                bypass_name="F3-B2",
                detail="Exact hash match against mock PEP relation list.",
                model_name="deterministic_watchlist",
            )

        self._emit(
            kind=AuditEventKind.MESSAGE_SENT,
            phase="return",
            status="ok",
            model_name="deterministic_watchlist",
            detail=f"Screened {len(results)} unique hash token(s).",
        )
        return response

    def _validate_route(self, request: SanctionsCheckRequest) -> None:
        if request.recipient_agent_id != self.agent_id:
            detail = "SanctionsCheckRequest must be addressed to federation.F3"
            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="input_validation",
                status="blocked",
                detail=detail,
            )
            raise InvalidAgentInput(detail)
        if request.sender_role not in {AgentRole.A2, AgentRole.F1}:
            detail = "F3 only accepts requests from A2 or F1"
            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="input_validation",
                status="blocked",
                detail=detail,
            )
            raise InvalidAgentInput(detail)
