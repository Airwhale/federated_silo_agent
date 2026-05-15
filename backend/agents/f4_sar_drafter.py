"""F4 SAR drafting agent."""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Hashable
from functools import lru_cache
from pathlib import Path
from typing import Annotated, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from backend import BACKEND_ROOT
from backend.agents.base import (
    Agent,
    AuditEmitter,
    ConstraintViolation,
    InvalidAgentInput,
)
from backend.agents.llm_client import LLMClient
from backend.runtime.context import AgentRuntimeContext, TrustDomain
from shared.enums import (
    AgentRole,
    AuditEventKind,
    BankId,
    PatternClass,
    SARPriority,
    TypologyCode,
)
from shared.messages import (
    ContributorAttribution,
    CrossBankHashToken,
    SARAssemblyRequest,
    SARContribution,
    SARContributionRequest,
    SARDraft,
)


PROMPT_PATH = BACKEND_ROOT / "agents" / "prompts" / "f4_system.md"
F4_AGENT_ID = "federation.F4"
NarrativeText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
ValueT = TypeVar("ValueT", bound=Hashable)


class F4NarrativeContributor(BaseModel):
    """Safe per-contributor facts passed to the narrative LLM."""

    bank_id: BankId
    investigator_id: str
    evidence_item_ids: list[UUID]
    entity_hashes: list[CrossBankHashToken]
    contribution_summary: str

    model_config = ConfigDict(extra="forbid", strict=True)


class F4SanctionsHit(BaseModel):
    """Hash-only sanctions or PEP fact passed to the narrative LLM."""

    entity_hash: CrossBankHashToken
    sdn_match: bool
    pep_relation: bool

    model_config = ConfigDict(extra="forbid", strict=True)


class F4NarrativeFacts(BaseModel):
    """Strict narrative input assembled from deterministic SAR fields."""

    case_id: UUID
    filing_institution: str
    suspicious_amount_range: tuple[int, int]
    typology_code: TypologyCode
    graph_pattern_class: PatternClass
    graph_confidence: float
    suspect_entity_hashes: list[CrossBankHashToken]
    contributors: list[F4NarrativeContributor]
    sanctions_hits: list[F4SanctionsHit]
    related_query_ids: list[UUID]

    model_config = ConfigDict(extra="forbid", strict=True)


class F4NarrativeDraft(BaseModel):
    """LLM-authored narrative only. Structured fields are Python-derived."""

    narrative: NarrativeText

    model_config = ConfigDict(extra="forbid", strict=True)


class ComputedSARFields(BaseModel):
    """Internal deterministic SAR field bundle."""

    filing_institution: str
    suspicious_amount_range: tuple[int, int]
    typology_code: TypologyCode
    contributors: list[ContributorAttribution]
    sar_priority: SARPriority
    related_query_ids: list[UUID]
    narrative_facts: F4NarrativeFacts

    model_config = ConfigDict(extra="forbid", strict=True)


@lru_cache(maxsize=8)
def load_prompt(path: Path = PROMPT_PATH) -> str:
    """Load the versioned F4 prompt."""
    return path.read_text(encoding="utf-8")


class F4SARDrafterAgent(Agent[SARAssemblyRequest, SARDraft]):
    """LLM-driven SAR drafter with deterministic mandatory-field gates.

    F4 does not fetch bank data. It receives a validated SAR assembly package,
    deterministically derives structured SAR fields, and uses the LLM only for
    bounded narrative synthesis over supplied hash-only facts.
    """

    agent_id = F4_AGENT_ID
    role = AgentRole.F4
    bank_id = BankId.FEDERATION
    input_schema = SARAssemblyRequest
    output_schema = SARDraft
    declared_intent = "federation_sar_drafting"

    def __init__(
        self,
        *,
        runtime: AgentRuntimeContext,
        llm: LLMClient | None = None,
        audit: AuditEmitter | None = None,
    ) -> None:
        if runtime.trust_domain != TrustDomain.FEDERATION:
            raise ValueError("F4 must run in the federation trust domain")
        self.system_prompt = load_prompt()
        super().__init__(runtime=runtime, llm=llm, audit=audit)

    def run(
        self,
        input_data: SARAssemblyRequest | object,
    ) -> SARDraft | SARContributionRequest:
        """Draft a SAR or request missing mandatory input from F1."""
        request = self._validate_input(input_data)
        self._validate_sender(request)

        missing_fields = missing_mandatory_fields(request)
        if missing_fields:
            result = self._missing_input_request(request, missing_fields)
            self._emit_message_sent(
                detail="F4 requested missing SAR inputs.",
                model_name="deterministic_mandatory_gate",
            )
            return result

        fields = compute_sar_fields(request)
        narrative = self._draft_narrative(request, fields)
        result = self._build_sar_draft(request, fields, narrative)
        self._emit_message_sent(
            detail="F4 emitted SAR draft.",
            model_name=self.llm.config.default_model,
        )
        return result

    def _validate_sender(self, request: SARAssemblyRequest) -> None:
        if request.sender_role not in {AgentRole.F1, AgentRole.ORCHESTRATOR}:
            detail = "F4 only accepts SARAssemblyRequest from F1 or orchestrator"
            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="input_validation",
                status="blocked",
                detail=detail,
            )
            raise InvalidAgentInput(detail)

    def _missing_input_request(
        self,
        request: SARAssemblyRequest,
        missing_fields: list[str],
    ) -> SARContributionRequest:
        return SARContributionRequest(
            sender_agent_id=self.agent_id,
            sender_role=self.role,
            sender_bank_id=self.bank_id,
            recipient_agent_id="federation.F1",
            in_reply_to=request.case_id,
            requested_bank_id=request.filing_bank_id,
            missing_fields=missing_fields,
            request_reason=missing_request_reason(missing_fields),
            related_query_ids=aggregate_related_query_ids(request),
        )

    def _draft_narrative(
        self,
        request: SARAssemblyRequest,
        fields: ComputedSARFields,
    ) -> str:
        draft = self._call_structured(
            system_prompt=self.system_prompt,
            input_model=fields.narrative_facts,
            output_schema=F4NarrativeDraft,
            phase="narrative",
        )
        violation = narrative_violation(request, fields, draft.narrative)
        if violation is None:
            return draft.narrative

        self._emit(
            kind=AuditEventKind.CONSTRAINT_VIOLATION,
            phase="narrative",
            status="retry",
            detail=violation,
            rule_name="F4-C1",
        )
        repaired = self._call_structured(
            system_prompt=self.system_prompt,
            input_model=fields.narrative_facts,
            output_schema=F4NarrativeDraft,
            phase="narrative",
            repair_instruction=(
                "Repair the SAR narrative. Use only supplied facts, include "
                "Section 314(b), include every contributing bank_id, include "
                f"required hash references, and fix this violation: {violation}"
            ),
        )
        retry_violation = narrative_violation(request, fields, repaired.narrative)
        if retry_violation is None:
            return repaired.narrative

        self._emit(
            kind=AuditEventKind.CONSTRAINT_VIOLATION,
            phase="narrative",
            status="blocked",
            detail=retry_violation,
            rule_name="F4-C1",
            retry_count=1,
        )
        raise ConstraintViolation(retry_violation)

    def _build_sar_draft(
        self,
        request: SARAssemblyRequest,
        fields: ComputedSARFields,
        narrative: str,
    ) -> SARDraft:
        return SARDraft(
            sender_agent_id=self.agent_id,
            sender_role=self.role,
            sender_bank_id=self.bank_id,
            recipient_agent_id=request.sender_agent_id,
            filing_institution=fields.filing_institution,
            suspicious_amount_range=fields.suspicious_amount_range,
            typology_code=fields.typology_code,
            narrative=narrative,
            contributors=fields.contributors,
            sar_priority=fields.sar_priority,
            mandatory_fields_complete=True,
            related_query_ids=fields.related_query_ids,
        )

    def _emit_message_sent(self, *, detail: str, model_name: str) -> None:
        self._emit(
            kind=AuditEventKind.MESSAGE_SENT,
            phase="return",
            status="ok",
            detail=detail,
            model_name=model_name,
        )


def missing_mandatory_fields(request: SARAssemblyRequest) -> list[str]:
    """Return missing F4 inputs before any narrative LLM call."""
    missing: list[str] = []
    if not any(
        contribution.suspicious_amount_range is not None
        for contribution in request.contributions
    ):
        missing.append("suspicious_amount_range")
    if request.graph_pattern is None:
        missing.append("graph_pattern")
    elif request.graph_pattern.pattern_class == PatternClass.NONE:
        missing.append("graph_pattern.pattern_class")
    return missing


def compute_sar_fields(request: SARAssemblyRequest) -> ComputedSARFields:
    """Derive structured SAR fields from validated assembly artifacts."""
    graph_pattern = request.graph_pattern
    if graph_pattern is None or graph_pattern.pattern_class == PatternClass.NONE:
        raise ValueError("graph_pattern must be present with a non-none pattern class")

    amount_range = aggregate_amount_range(request.contributions)
    typology_code = typology_from_pattern(graph_pattern.pattern_class)
    contributions_by_bank = group_contributions_by_bank(request.contributions)
    contributors = contributor_attributions(contributions_by_bank)
    related_query_ids = aggregate_related_query_ids(request)
    priority = (
        SARPriority.HIGH
        if has_sanctions_or_pep_evidence(request)
        else SARPriority.STANDARD
    )
    narrative_facts = F4NarrativeFacts(
        case_id=request.case_id,
        filing_institution=request.filing_bank_id.value,
        suspicious_amount_range=amount_range,
        typology_code=typology_code,
        graph_pattern_class=graph_pattern.pattern_class,
        graph_confidence=graph_pattern.confidence,
        suspect_entity_hashes=unique_values(graph_pattern.suspect_entity_hashes),
        contributors=narrative_contributors(contributions_by_bank, contributors),
        sanctions_hits=sanctions_hits(request),
        related_query_ids=related_query_ids,
    )
    return ComputedSARFields(
        filing_institution=request.filing_bank_id.value,
        suspicious_amount_range=amount_range,
        typology_code=typology_code,
        contributors=contributors,
        sar_priority=priority,
        related_query_ids=related_query_ids,
        narrative_facts=narrative_facts,
    )


def aggregate_amount_range(
    contributions: list[SARContribution],
) -> tuple[int, int]:
    """Combine contribution ranges without inferring from text."""
    ranges = [
        amount_range
        for contribution in contributions
        if (amount_range := contribution.suspicious_amount_range) is not None
    ]
    if not ranges:
        raise ValueError("at least one suspicious_amount_range is required")
    return min(low for low, _ in ranges), max(high for _, high in ranges)


def typology_from_pattern(pattern_class: PatternClass) -> TypologyCode:
    """Map F2 pattern classes to SAR typology codes."""
    if pattern_class == PatternClass.STRUCTURING_RING:
        return TypologyCode.STRUCTURING
    if pattern_class == PatternClass.LAYERING_CHAIN:
        return TypologyCode.LAYERING
    raise ValueError(f"unsupported SAR pattern_class: {pattern_class}")


def group_contributions_by_bank(
    contributions: list[SARContribution],
) -> OrderedDict[BankId, list[SARContribution]]:
    """Group contributions by bank in first-seen order."""
    by_bank: OrderedDict[BankId, list[SARContribution]] = OrderedDict()
    for contribution in contributions:
        by_bank.setdefault(contribution.contributing_bank_id, []).append(contribution)
    return by_bank


def contributor_attributions(
    by_bank: OrderedDict[BankId, list[SARContribution]],
) -> list[ContributorAttribution]:
    """Create one deterministic attribution block per contributing bank."""
    attributions: list[ContributorAttribution] = []
    for bank_id, bank_contributions in by_bank.items():
        evidence_ids = unique_values(
            [
                evidence.evidence_id
                for contribution in bank_contributions
                for evidence in contribution.contributed_evidence
            ]
        )
        attributions.append(
            ContributorAttribution(
                bank_id=bank_id,
                investigator_id=combined_investigator_ids(bank_contributions),
                evidence_item_ids=evidence_ids,
                contribution_summary=contribution_summary(
                    bank_id,
                    bank_contributions,
                ),
            )
        )
    return attributions


def narrative_contributors(
    by_bank: OrderedDict[BankId, list[SARContribution]],
    attributions: list[ContributorAttribution],
) -> list[F4NarrativeContributor]:
    """Build hash-only contributor facts for the LLM."""
    return [
        F4NarrativeContributor(
            bank_id=attribution.bank_id,
            investigator_id=attribution.investigator_id,
            evidence_item_ids=attribution.evidence_item_ids,
            entity_hashes=entity_hashes_for_contributions(
                by_bank[attribution.bank_id],
            ),
            contribution_summary=attribution.contribution_summary,
        )
        for attribution in attributions
    ]


def contribution_summary(
    bank_id: BankId,
    contributions: list[SARContribution],
) -> str:
    """Summarize hash-only evidence for one bank."""
    evidence_count = sum(len(item.contributed_evidence) for item in contributions)
    entity_count = len(entity_hashes_for_contributions(contributions))
    amount_ranges = [
        contribution.suspicious_amount_range
        for contribution in contributions
        if contribution.suspicious_amount_range is not None
    ]
    amount_text = "no amount range provided"
    if amount_ranges:
        low = min(low for low, _ in amount_ranges)
        high = max(high for _, high in amount_ranges)
        amount_text = f"amount range {low}-{high} cents"
    combined_rationale = " ".join(
        sorted(
            unique_values(
                [
                    contribution.local_rationale
                    for contribution in contributions
                    if contribution.local_rationale
                ]
            )
        )
    )
    rationale = truncate_text(combined_rationale, 220)
    return truncate_text(
        f"{bank_id.value} contributed {evidence_count} evidence item(s), "
        f"{entity_count} entity hash(es), and {amount_text}. "
        f"Rationale: {rationale}",
        500,
    )


def combined_investigator_ids(contributions: list[SARContribution]) -> str:
    """Return stable attribution for all investigators at one bank."""
    return ", ".join(
        sorted(
            {
                contribution.contributing_investigator_id
                for contribution in contributions
            }
        )
    )


def entity_hashes_for_contributions(
    contributions: list[SARContribution],
) -> list[CrossBankHashToken]:
    hashes: list[CrossBankHashToken] = []
    for contribution in contributions:
        for evidence in contribution.contributed_evidence:
            hashes.extend(evidence.entity_hashes)
    return unique_values(hashes)


def has_sanctions_or_pep_evidence(request: SARAssemblyRequest) -> bool:
    """Return True when F3 supplied any sanctions or PEP hit."""
    if request.sanctions is None:
        return False
    return any(
        result.sdn_match or result.pep_relation
        for result in request.sanctions.results.values()
    )


def sanctions_hits(request: SARAssemblyRequest) -> list[F4SanctionsHit]:
    if request.sanctions is None:
        return []
    return [
        F4SanctionsHit(
            entity_hash=entity_hash,
            sdn_match=result.sdn_match,
            pep_relation=result.pep_relation,
        )
        for entity_hash, result in sorted(request.sanctions.results.items())
        if result.sdn_match or result.pep_relation
    ]


def aggregate_related_query_ids(request: SARAssemblyRequest) -> list[UUID]:
    """Return query IDs from assembly and contributions in stable order."""
    return unique_values(
        [
            *request.related_query_ids,
            *(
                query_id
                for contribution in request.contributions
                for query_id in contribution.related_query_ids
            ),
        ]
    )


def missing_request_reason(missing_fields: list[str]) -> str:
    field_text = ", ".join(missing_fields)
    return (
        "F4 cannot complete deterministic SAR fields until F1 supplies "
        f"the missing input(s): {field_text}."
    )


def narrative_violation(
    request: SARAssemblyRequest,
    fields: ComputedSARFields,
    narrative: str,
) -> str | None:
    """Validate narrative-only LLM output against deterministic facts."""
    if not contains_exact_token(narrative, "314(b)") and not contains_exact_token(
        narrative,
        "USA_PATRIOT_314b",
    ):
        return "SAR narrative must reference Section 314(b) authority"

    for contributor in fields.contributors:
        if not contains_exact_token(narrative, contributor.bank_id.value):
            return (
                "SAR narrative must reference contributing bank_id "
                f"{contributor.bank_id.value}"
            )

    required_hashes = narrative_required_hashes(fields.narrative_facts)
    if required_hashes:
        missing_hashes = [
            hash_value
            for hash_value in required_hashes
            if not contains_exact_token(narrative, hash_value)
        ]
        if missing_hashes:
            return (
                "SAR narrative must reference supplied suspect entity hashes. "
                f"Missing: {missing_hashes!r}"
            )

    try:
        SARDraft(
            sender_agent_id=F4_AGENT_ID,
            sender_role=AgentRole.F4,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id=request.sender_agent_id,
            filing_institution=fields.filing_institution,
            suspicious_amount_range=fields.suspicious_amount_range,
            typology_code=fields.typology_code,
            narrative=narrative,
            contributors=fields.contributors,
            sar_priority=fields.sar_priority,
            mandatory_fields_complete=True,
            related_query_ids=fields.related_query_ids,
        )
    except ValidationError as exc:
        return str(exc)
    return None


def narrative_required_hashes(facts: F4NarrativeFacts) -> list[CrossBankHashToken]:
    """Return hash tokens that must appear in narrative text."""
    sanctions_hashes = [hit.entity_hash for hit in facts.sanctions_hits]
    return unique_values([*sanctions_hashes, *facts.suspect_entity_hashes])


def contains_exact_token(text: str, token: str) -> bool:
    """Return whether token appears without being embedded in a larger token."""
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])"
    return re.search(pattern, text) is not None


def unique_values(values: list[ValueT]) -> list[ValueT]:
    """Deduplicate hashable values while preserving input order."""
    return list(dict.fromkeys(values))


def truncate_text(value: str, max_length: int) -> str:
    """Return a non-empty string capped to a schema-safe length."""
    stripped = value.strip()
    if len(stripped) <= max_length:
        return stripped
    return stripped[: max_length - 3].rstrip() + "..."
