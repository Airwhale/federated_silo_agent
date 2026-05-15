"""F2 federation graph analysis over DP-noised aggregate patterns."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend import BACKEND_ROOT
from backend.agents.base import (
    Agent,
    AuditEmitter,
    ConstraintViolation,
    InvalidAgentInput,
)
from backend.agents.f2_typologies import (
    TypologySignals,
    deterministic_match,
    extract_signals,
)
from backend.agents.llm_client import LLMClient
from backend.runtime.context import AgentRuntimeContext, TrustDomain
from shared.enums import AgentRole, AuditEventKind, BankId, PatternClass
from shared.messages import (
    CrossBankHashToken,
    GraphPatternRequest,
    GraphPatternResponse,
    MediumText,
    reject_demo_customer_names,
)


PROMPT_PATH = BACKEND_ROOT / "agents" / "prompts" / "f2_system.md"
F2_AGENT_ID = "federation.F2"


class F2LlmInput(BaseModel):
    """LLM input containing only the request and derived aggregate signals."""

    request: GraphPatternRequest
    signals: TypologySignals

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class F2ClassificationDraft(BaseModel):
    """LLM-authored classification fields before F2 attaches message metadata."""

    pattern_class: PatternClass
    confidence: float = Field(ge=0.0, le=1.0)
    suspect_entity_hashes: list[CrossBankHashToken] = Field(default_factory=list)
    narrative: MediumText

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    @field_validator("narrative")
    @classmethod
    def narrative_must_not_contain_customer_names(cls, value: str) -> str:
        return reject_demo_customer_names(value, "narrative")


@lru_cache(maxsize=8)
def load_prompt(path: Path = PROMPT_PATH) -> str:
    """Load the versioned F2 prompt for ambiguous graph classification."""
    return path.read_text(encoding="utf-8")


class F2GraphAnalysisAgent(Agent[GraphPatternRequest, GraphPatternResponse]):
    """Hybrid federation-layer graph analyst.

    Deterministic gates identify clear structuring-ring and layering-chain
    patterns over DP-noised aggregate histograms. Ambiguous cases fall back to
    an LLM classifier that receives the same aggregate-only request plus
    derived signals. F2 never receives raw transactions, account rows, database
    handles, or customer names.
    """

    agent_id = F2_AGENT_ID
    role = AgentRole.F2
    bank_id = BankId.FEDERATION
    input_schema = GraphPatternRequest
    output_schema = GraphPatternResponse
    declared_intent = "federation_graph_pattern_analysis"

    def __init__(
        self,
        *,
        runtime: AgentRuntimeContext,
        llm: LLMClient | None = None,
        audit: AuditEmitter | None = None,
    ) -> None:
        if runtime.trust_domain != TrustDomain.FEDERATION:
            raise ValueError("F2 must run in the federation trust domain")
        self.system_prompt = load_prompt()
        super().__init__(runtime=runtime, llm=llm, audit=audit)

    def run(self, input_data: GraphPatternRequest | object) -> GraphPatternResponse:
        request = self._validate_input(input_data)
        self._validate_route(request)

        signals = extract_signals(request.pattern_aggregates)
        deterministic = deterministic_match(signals)
        if deterministic is not None:
            response = self._response_from_fields(
                request=request,
                pattern_class=deterministic.pattern_class,
                confidence=deterministic.confidence,
                suspect_entity_hashes=deterministic.suspect_entity_hashes,
                narrative=deterministic.narrative,
            )
            self._emit(
                kind=AuditEventKind.BYPASS_TRIGGERED,
                phase="classify",
                status="ok",
                rule_name=deterministic.bypass_name,
                bypass_name=deterministic.bypass_name,
                detail=deterministic.narrative,
                model_name="deterministic_graph_typology",
            )
            self._emit(
                kind=AuditEventKind.MESSAGE_SENT,
                phase="return",
                status="ok",
                bypass_name=deterministic.bypass_name,
                model_name="deterministic_graph_typology",
                detail=(
                    f"F2 emitted {response.pattern_class.value} with "
                    f"{len(response.suspect_entity_hashes)} hash token(s)."
                ),
            )
            return response

        draft = self._call_llm_classifier(request=request, signals=signals)
        response = self._response_from_fields(
            request=request,
            pattern_class=draft.pattern_class,
            confidence=draft.confidence,
            suspect_entity_hashes=draft.suspect_entity_hashes,
            narrative=draft.narrative,
        )
        self._emit(
            kind=AuditEventKind.MESSAGE_SENT,
            phase="return",
            status="ok",
            model_name=self.llm.config.default_model,
            detail=(
                f"F2 emitted {response.pattern_class.value} with "
                f"{len(response.suspect_entity_hashes)} hash token(s)."
            ),
        )
        return response

    def _validate_route(self, request: GraphPatternRequest) -> None:
        if request.recipient_agent_id != self.agent_id:
            detail = "GraphPatternRequest must be addressed to federation.F2"
            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="input_validation",
                status="blocked",
                detail=detail,
            )
            raise InvalidAgentInput(detail)
        if request.sender_role != AgentRole.F1:
            detail = "F2 only accepts graph pattern requests from F1"
            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="input_validation",
                status="blocked",
                detail=detail,
            )
            raise InvalidAgentInput(detail)

    def _call_llm_classifier(
        self,
        *,
        request: GraphPatternRequest,
        signals: TypologySignals,
    ) -> F2ClassificationDraft:
        llm_input = F2LlmInput(request=request, signals=signals)
        draft = self._call_structured(
            system_prompt=self.system_prompt,
            input_model=llm_input,
            output_schema=F2ClassificationDraft,
            phase="llm_parse",
        )
        violation = self._draft_violation(signals, draft)
        if violation is None:
            return draft

        self._emit(
            kind=AuditEventKind.CONSTRAINT_VIOLATION,
            phase="constraint",
            status="retry",
            detail=violation,
            rule_name="F2-C1",
            retry_count=1,
        )
        repaired = self._call_structured(
            system_prompt=self.system_prompt,
            input_model=llm_input,
            output_schema=F2ClassificationDraft,
            phase="llm_repair",
            repair_instruction=(
                "Your previous output violated a deterministic F2 constraint. "
                f"Repair it and return only valid JSON. Constraint: {violation}"
            ),
        )
        repaired_violation = self._draft_violation(signals, repaired)
        if repaired_violation is not None:
            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="constraint",
                status="blocked",
                detail=repaired_violation,
                rule_name="F2-C1",
                retry_count=1,
            )
            raise ConstraintViolation(repaired_violation)
        return repaired

    def _draft_violation(
        self,
        signals: TypologySignals,
        draft: F2ClassificationDraft,
    ) -> str | None:
        allowed_hashes = set(signals.candidate_entity_hashes)
        unexpected = [
            entity_hash
            for entity_hash in draft.suspect_entity_hashes
            if entity_hash not in allowed_hashes
        ]
        if unexpected:
            return "suspect_entity_hashes must be drawn from candidate_entity_hashes"
        if draft.pattern_class == PatternClass.NONE and draft.confidence >= 0.4:
            return "pattern_class none must have confidence below 0.4"
        if draft.pattern_class == PatternClass.NONE and draft.suspect_entity_hashes:
            return "pattern_class none must not include suspect hashes"
        if draft.pattern_class != PatternClass.NONE and draft.confidence < 0.4:
            return "detected patterns must have confidence at least 0.4"
        return None

    def _response_from_fields(
        self,
        *,
        request: GraphPatternRequest,
        pattern_class: PatternClass,
        confidence: float,
        suspect_entity_hashes: list[CrossBankHashToken],
        narrative: str,
    ) -> GraphPatternResponse:
        return GraphPatternResponse(
            sender_agent_id=self.agent_id,
            sender_role=self.role,
            sender_bank_id=self.bank_id,
            recipient_agent_id=request.sender_agent_id,
            pattern_class=pattern_class,
            confidence=confidence,
            suspect_entity_hashes=list(dict.fromkeys(suspect_entity_hashes)),
            narrative=narrative,
        )
