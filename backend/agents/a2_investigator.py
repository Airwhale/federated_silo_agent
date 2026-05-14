"""A2 investigator agent state machine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from backend import BACKEND_ROOT
from backend.agents.a2_states import (
    A2AlertInput,
    A2InboundQueryInput,
    A2PeerResponseInput,
    A2TurnInput,
    A2TurnResult,
    CorrelatedAlertSummary,
    QueryDraft,
    SynthesisDecision,
    TriageDecision,
)
from backend.agents.base import (
    Agent,
    AuditEmitter,
    ConstraintViolation,
    InvalidAgentInput,
)
from backend.agents.llm_client import LLMClient
from backend.runtime.context import AgentRuntimeContext
from shared.enums import (
    AgentRole,
    AuditEventKind,
    BankId,
    QueryShape,
    SignalType,
    TypologyCode,
)
from shared.messages import (
    AggregateActivityPayload,
    Alert,
    BoolResponseValue,
    CounterpartyLinkagePayload,
    CrossBankHashToken,
    DismissalRationale,
    EntityPresencePayload,
    EvidenceItem,
    FloatResponseValue,
    HashListResponseValue,
    HistogramResponseValue,
    IntResponseValue,
    PurposeDeclaration,
    SARContribution,
    Sec314bQuery,
    Sec314bResponse,
)


TRIAGE_PROMPT_PATH = BACKEND_ROOT / "agents" / "prompts" / "a2_triage.md"
QUERY_PROMPT_PATH = BACKEND_ROOT / "agents" / "prompts" / "a2_query.md"
SYNTHESIS_PROMPT_PATH = BACKEND_ROOT / "agents" / "prompts" / "a2_synthesis.md"
CORRELATION_WINDOW_DAYS = 30
CORRELATED_ALERT_THRESHOLD = 3

StateOutT = TypeVar("StateOutT", bound=BaseModel)


def load_prompt(path: Path) -> str:
    """Load one versioned A2 prompt."""
    return path.read_text(encoding="utf-8")


class A2InvestigatorAgent(Agent[A2TurnInput, A2TurnResult]):
    """Human-facing investigator agent outside bank data-plane boundaries."""

    role = AgentRole.A2
    input_schema = A2TurnInput
    output_schema = A2TurnResult
    declared_intent = "local_investigation_and_cross_bank_escalation"

    def __init__(
        self,
        *,
        bank_id: BankId,
        runtime: AgentRuntimeContext,
        investigator_id: str | None = None,
        llm: LLMClient | None = None,
        audit: AuditEmitter | None = None,
    ) -> None:
        if bank_id == BankId.FEDERATION:
            raise ValueError("A2 must belong to a bank, not the federation")
        self.bank_id = bank_id
        self.agent_id = f"{bank_id.value}.A2"
        self.investigator_id = investigator_id or f"{bank_id.value}.investigator"
        self.system_prompt = load_prompt(TRIAGE_PROMPT_PATH)
        self.triage_prompt = self.system_prompt
        self.query_prompt = load_prompt(QUERY_PROMPT_PATH)
        self.synthesis_prompt = load_prompt(SYNTHESIS_PROMPT_PATH)
        super().__init__(runtime=runtime, llm=llm, audit=audit)

    def build_alert_input(
        self,
        alert: Alert,
        *,
        correlated_alerts: list[CorrelatedAlertSummary] | None = None,
    ) -> A2TurnInput:
        """Build one alert turn for this investigator."""
        return A2TurnInput(
            payload=A2AlertInput(
                alert=alert,
                investigator_id=self.investigator_id,
                correlated_alerts=correlated_alerts or [],
            )
        )

    def build_peer_response_input(
        self,
        *,
        alert: Alert,
        original_query: Sec314bQuery,
        response: Sec314bResponse,
    ) -> A2TurnInput:
        """Build one peer-response synthesis turn."""
        return A2TurnInput(
            payload=A2PeerResponseInput(
                alert=alert,
                original_query=original_query,
                response=response,
                investigator_id=self.investigator_id,
            )
        )

    def run(self, input_data: A2TurnInput | object) -> A2TurnResult:
        """Run one A2 state-machine turn."""
        validated_input = self._validate_input(input_data)
        payload = validated_input.payload

        if isinstance(payload, A2InboundQueryInput):
            return self._reject_inbound_query(payload)
        if isinstance(payload, A2AlertInput):
            return self._run_alert_turn(payload)
        if isinstance(payload, A2PeerResponseInput):
            return self._run_peer_response_turn(payload)

        raise InvalidAgentInput(f"unsupported A2 payload: {type(payload)!r}")

    def _run_alert_turn(self, payload: A2AlertInput) -> A2TurnResult:
        if payload.alert.recipient_agent_id != self.agent_id:
            raise InvalidAgentInput("A2 alert input must be addressed to this A2")

        if payload.alert.signal_type == SignalType.SANCTIONS_MATCH:
            result = self._sar_result_from_alert(
                payload,
                rationale=(
                    "A2-B2 forced escalation: local A1 alert is tied to a known "
                    "sanctions match."
                ),
                bypass_rule_id="A2-B2",
            )
            self._emit_bypass("A2-B2", "sanctions-match alert requires hard escalation")
            self._emit_message_sent(result, "A2-B2")
            return result

        if self._has_correlated_alert_bypass(payload):
            draft = self._default_query_draft(payload.alert, rule_id="A2-B1")
            result = self._query_result(payload, draft, bypass_rule_id="A2-B1")
            self._emit_bypass(
                "A2-B1",
                "three correlated entity alerts in the 30 day window require query",
            )
            self._emit_message_sent(result, "A2-B1")
            return result

        triage = self._call_structured(
            system_prompt=self.triage_prompt,
            input_model=payload,
            output_schema=TriageDecision,
            phase="triage",
        )
        if triage.action == "dismiss":
            result = self._dismiss_alert(payload.alert, triage.reason)
            self._emit_message_sent(result, None)
            return result

        draft = self._call_state_with_constraint(
            prompt=self.query_prompt,
            input_model=payload,
            output_schema=QueryDraft,
            phase="cross_bank_query",
            constraint=lambda d: validate_query_draft_against_alert(d, payload.alert),
        )
        result = self._query_result(payload, draft, bypass_rule_id=None)
        self._emit_message_sent(result, None)
        return result

    def _run_peer_response_turn(self, payload: A2PeerResponseInput) -> A2TurnResult:
        self._validate_peer_response_lineage(payload)

        if not response_has_corroboration(payload.response):
            result = self._dismiss_alert(
                payload.alert,
                "Peer responses did not corroborate the local alert.",
                evidence_ids=[payload.response.message_id],
            )
            self._emit_message_sent(result, None)
            return result

        synthesis = self._call_structured(
            system_prompt=self.synthesis_prompt,
            input_model=payload,
            output_schema=SynthesisDecision,
            phase="synthesize",
        )
        if synthesis.action == "dismiss":
            result = self._dismiss_alert(
                payload.alert,
                synthesis.rationale,
                evidence_ids=[payload.response.message_id],
            )
            self._emit_message_sent(result, None)
            return result

        result = self._sar_result_from_response(payload, synthesis.rationale)
        self._emit_message_sent(result, None)
        return result

    def _reject_inbound_query(self, payload: A2InboundQueryInput) -> A2TurnResult:
        reason = (
            "A2 cannot answer incoming peer Sec314bQuery messages; route peer "
            f"queries to this bank's A3 responder. query_id={payload.query.query_id}"
        )
        self._emit(
            kind=AuditEventKind.CONSTRAINT_VIOLATION,
            phase="routing",
            status="blocked",
            detail=reason,
            rule_name="a2_cannot_answer_peer_queries",
        )
        return A2TurnResult(action="rejected", rejection_reason=reason)

    def _query_result(
        self,
        payload: A2AlertInput,
        draft: QueryDraft,
        *,
        bypass_rule_id: str | None,
    ) -> A2TurnResult:
        query = build_sec314b_query(
            agent_id=self.agent_id,
            bank_id=self.bank_id,
            investigator_id=payload.investigator_id,
            alert=payload.alert,
            draft=draft,
        )
        return A2TurnResult(
            action="query",
            query=query,
            bypass_rule_id=bypass_rule_id,
        )

    def _sar_result_from_alert(
        self,
        payload: A2AlertInput,
        *,
        rationale: str,
        bypass_rule_id: str | None,
    ) -> A2TurnResult:
        contribution = build_sar_contribution(
            agent_id=self.agent_id,
            bank_id=self.bank_id,
            investigator_id=payload.investigator_id,
            recipient_agent_id="federation.F4",
            alert=payload.alert,
            rationale=rationale,
            related_query_ids=[],
        )
        return A2TurnResult(
            action="sar_contribution",
            sar_contribution=contribution,
            bypass_rule_id=bypass_rule_id,
        )

    def _sar_result_from_response(
        self,
        payload: A2PeerResponseInput,
        rationale: str,
    ) -> A2TurnResult:
        contribution = build_sar_contribution(
            agent_id=self.agent_id,
            bank_id=self.bank_id,
            investigator_id=payload.investigator_id,
            recipient_agent_id="federation.F4",
            alert=payload.alert,
            rationale=rationale,
            related_query_ids=[payload.original_query.query_id],
        )
        return A2TurnResult(action="sar_contribution", sar_contribution=contribution)

    def _dismiss_alert(
        self,
        alert: Alert,
        reason: str,
        *,
        evidence_ids: list[UUID] | None = None,
    ) -> A2TurnResult:
        considered = [item.evidence_id for item in alert.evidence]
        if evidence_ids:
            considered.extend(evidence_ids)
        dismissal = DismissalRationale(
            sender_agent_id=self.agent_id,
            sender_role=AgentRole.A2,
            sender_bank_id=self.bank_id,
            recipient_agent_id="federation.F5",
            alert_id=alert.alert_id,
            reason=reason,
            evidence_considered=considered,
        )
        return A2TurnResult(action="dismiss", dismissal=dismissal)

    def _default_query_draft(self, alert: Alert, *, rule_id: str) -> QueryDraft:
        entity_hashes = alert_entity_hashes(alert)
        if not entity_hashes:
            raise ConstraintViolation(f"{rule_id} requires at least one entity hash")
        return QueryDraft(
            query_shape=QueryShape.AGGREGATE_ACTIVITY,
            typology_code=typology_for_signal(alert.signal_type),
            suspicion_rationale=(
                f"{rule_id} triggered by repeated local alerts for the same "
                "hashed entity within the investigation window."
            ),
            name_hashes=entity_hashes,
            metrics=["alert_count"],
            requested_rho_per_primitive=0.02,
        )

    def _has_correlated_alert_bypass(self, payload: A2AlertInput) -> bool:
        current_hashes = set(alert_entity_hashes(payload.alert))
        if not current_hashes:
            return False

        counts = {hash_value: 1 for hash_value in current_hashes}
        current_time = payload.alert.created_at
        for summary in payload.correlated_alerts:
            age = current_time - summary.created_at
            if age < timedelta(0) or age > timedelta(days=CORRELATION_WINDOW_DAYS):
                continue
            for hash_value in current_hashes & set(summary.entity_hashes):
                # `hash_value` is guaranteed in `counts` because the inner-loop
                # iterates over the intersection with `current_hashes`, and
                # `counts` is initialized from `current_hashes` at line 343.
                counts[hash_value] += 1
        return any(count >= CORRELATED_ALERT_THRESHOLD for count in counts.values())

    def _validate_peer_response_lineage(self, payload: A2PeerResponseInput) -> None:
        if payload.alert.recipient_agent_id != self.agent_id:
            raise InvalidAgentInput("peer response alert must be addressed to this A2")
        if payload.alert.sender_bank_id != self.bank_id:
            raise InvalidAgentInput("peer response alert must come from this bank")
        if payload.original_query.sender_agent_id != self.agent_id:
            raise InvalidAgentInput("original_query.sender_agent_id must match this A2")
        if payload.original_query.sender_role != AgentRole.A2:
            raise InvalidAgentInput("original_query.sender_role must be A2")
        if payload.original_query.sender_bank_id != self.bank_id:
            raise InvalidAgentInput("original_query.sender_bank_id must match this bank")
        if payload.original_query.requesting_bank_id != self.bank_id:
            raise InvalidAgentInput(
                "original_query.requesting_bank_id must match this bank"
            )
        if payload.original_query.requesting_investigator_id != payload.investigator_id:
            raise InvalidAgentInput(
                "original_query.requesting_investigator_id must match investigator_id"
            )
        if payload.alert.alert_id not in (
            payload.original_query.purpose_declaration.supporting_alert_ids
        ):
            raise InvalidAgentInput(
                "original_query must include the local alert_id in supporting_alert_ids"
            )
        if payload.response.recipient_agent_id != self.agent_id:
            raise InvalidAgentInput("A2 response input must be addressed to this A2")
        if payload.response.in_reply_to != payload.original_query.query_id:
            raise InvalidAgentInput(
                "Sec314bResponse.in_reply_to must match original_query.query_id "
                f"(got {payload.response.in_reply_to} vs "
                f"{payload.original_query.query_id})"
            )

    def _call_state_with_constraint(
        self,
        *,
        prompt: str,
        input_model: BaseModel,
        output_schema: type[StateOutT],
        phase: str,
        constraint: "Callable[[StateOutT], str | None]",
    ) -> StateOutT:
        """Call the LLM, then verify a domain constraint; retry once on violation.

        Used for `cross_bank_query` to enforce that drafted hashes come from
        the correct alert evidence field for the selected query shape. An LLM
        that invents a related hash gets one repair attempt with the violation
        message in the prompt. If the second draft still violates, the call
        raises ConstraintViolation rather than building a query.
        """
        draft = self._call_structured(
            system_prompt=prompt,
            input_model=input_model,
            output_schema=output_schema,
            phase=phase,
        )
        violation = constraint(draft)
        if violation is None:
            return draft

        self._emit(
            kind=AuditEventKind.CONSTRAINT_VIOLATION,
            phase=phase,
            status="retry",
            detail=violation,
            rule_name="query_draft_hashes_in_alert",
        )
        repair_prompt = (
            f"{prompt}\n\nYour previous draft violated a deterministic constraint: "
            f"{violation}. Use only hash tokens that already appear in the alert "
            "evidence field required by the query shape; do not invent or extend "
            "hash tokens."
        )
        retried = self._call_structured(
            system_prompt=repair_prompt,
            input_model=input_model,
            output_schema=output_schema,
            phase=phase,
        )
        retry_violation = constraint(retried)
        if retry_violation is None:
            return retried
        self._emit(
            kind=AuditEventKind.CONSTRAINT_VIOLATION,
            phase=phase,
            status="blocked",
            detail=retry_violation,
            rule_name="query_draft_hashes_in_alert",
            retry_count=1,
        )
        raise ConstraintViolation(retry_violation)

    def _emit_bypass(self, rule_name: str, reason: str) -> None:
        self._emit(
            kind=AuditEventKind.BYPASS_TRIGGERED,
            phase="bypass",
            status="ok",
            detail=reason,
            rule_name=rule_name,
            bypass_name=rule_name,
        )

    def _emit_message_sent(self, result: A2TurnResult, bypass_name: str | None) -> None:
        self._emit(
            kind=AuditEventKind.MESSAGE_SENT,
            phase="return",
            status="ok",
            model_name=self.llm.config.default_model,
            bypass_name=bypass_name,
            detail=f"A2 emitted {result.action}",
        )


def validate_query_draft_against_alert(draft: QueryDraft, alert: Alert) -> str | None:
    """Verify drafted hash targets come from matching alert evidence."""
    if draft.query_shape == QueryShape.COUNTERPARTY_LINKAGE:
        field_name = "counterparty_hashes"
        drafted_hashes = draft.counterparty_hashes
        allowed = set(alert_counterparty_hashes(alert))
    else:
        field_name = "name_hashes"
        drafted_hashes = draft.name_hashes
        allowed = set(alert_entity_hashes(alert))

    extra = [h for h in drafted_hashes if h not in allowed]
    if not extra:
        return None
    return (
        f"draft proposed {len(extra)} {field_name} value(s) not present in the "
        f"alert evidence ({extra[:3]}{'...' if len(extra) > 3 else ''}); A2 must "
        "only query peer banks about hashes the alert has evidence for"
    )


def alert_entity_hashes(alert: Alert) -> list[CrossBankHashToken]:
    """Return unique entity hashes from an A1 alert in stable order."""
    seen: set[str] = set()
    out: list[CrossBankHashToken] = []
    for evidence in alert.evidence:
        for hash_value in evidence.entity_hashes:
            if hash_value not in seen:
                out.append(hash_value)
                seen.add(hash_value)
    return out


def alert_counterparty_hashes(alert: Alert) -> list[CrossBankHashToken]:
    """Return unique cross-bank counterparty hashes from alert evidence."""
    seen: set[str] = set()
    out: list[CrossBankHashToken] = []
    for evidence in alert.evidence:
        for hash_value in evidence.counterparty_hashes:
            if hash_value in seen:
                continue
            out.append(hash_value)
            seen.add(hash_value)
    return out


def build_sec314b_query(
    *,
    agent_id: str,
    bank_id: BankId,
    investigator_id: str,
    alert: Alert,
    draft: QueryDraft,
) -> Sec314bQuery:
    """Build a strict Sec314bQuery from an LLM query draft."""
    start, end = alert_window(alert)
    if draft.query_shape == QueryShape.ENTITY_PRESENCE:
        payload = EntityPresencePayload(name_hashes=draft.name_hashes)
    elif draft.query_shape == QueryShape.AGGREGATE_ACTIVITY:
        payload = AggregateActivityPayload(
            name_hashes=draft.name_hashes,
            window_start=start,
            window_end=end,
            metrics=draft.metrics,
        )
    elif draft.query_shape == QueryShape.COUNTERPARTY_LINKAGE:
        payload = CounterpartyLinkagePayload(
            counterparty_hashes=draft.counterparty_hashes,
            window_start=start,
            window_end=end,
        )
    else:
        raise ValueError(f"unsupported query shape: {draft.query_shape}")

    return Sec314bQuery(
        sender_agent_id=agent_id,
        sender_role=AgentRole.A2,
        sender_bank_id=bank_id,
        recipient_agent_id="federation.F1",
        requesting_investigator_id=investigator_id,
        requesting_bank_id=bank_id,
        query_shape=draft.query_shape,
        query_payload=payload,
        purpose_declaration=PurposeDeclaration(
            typology_code=draft.typology_code,
            suspicion_rationale=draft.suspicion_rationale,
            supporting_alert_ids=[alert.alert_id],
        ),
        requested_rho_per_primitive=draft.requested_rho_per_primitive,
    )


def build_sar_contribution(
    *,
    agent_id: str,
    bank_id: BankId,
    investigator_id: str,
    recipient_agent_id: str,
    alert: Alert,
    rationale: str,
    related_query_ids: list[UUID],
) -> SARContribution:
    """Build an A2 contribution with hash-only evidence."""
    evidence = list(alert.evidence)
    if not evidence:
        evidence = [
            EvidenceItem(
                summary="A2 reviewed a local alert with no attached evidence items."
            )
        ]
    return SARContribution(
        sender_agent_id=agent_id,
        sender_role=AgentRole.A2,
        sender_bank_id=bank_id,
        recipient_agent_id=recipient_agent_id,
        contributing_bank_id=bank_id,
        contributing_investigator_id=investigator_id,
        contributed_evidence=evidence,
        local_rationale=rationale,
        related_query_ids=related_query_ids,
    )


def alert_window(alert: Alert) -> tuple[date, date]:
    """Return the default 30 day query window for an alert."""
    end = alert.created_at.date()
    start = (alert.created_at - timedelta(days=CORRELATION_WINDOW_DAYS)).date()
    return start, end


def typology_for_signal(signal_type: SignalType) -> TypologyCode:
    """Map local signal type to a Section 314(b) purpose typology."""
    if signal_type == SignalType.SANCTIONS_MATCH:
        return TypologyCode.SANCTIONS_EVASION
    if signal_type == SignalType.PEP_RELATION:
        return TypologyCode.PEP_EXPOSURE
    if signal_type == SignalType.LAYERING:
        return TypologyCode.LAYERING
    return TypologyCode.STRUCTURING


def response_has_corroboration(response: Sec314bResponse) -> bool:
    """Return whether a peer response has substantive corroborating signal.

    Uses direct `isinstance` checks against the typed ResponseValue union
    rather than a kind-name lookup; the previous version reimplemented
    `shared.messages.response_value_kind` via `hasattr` and was fragile
    against future field additions on the response models.
    """
    if response.refusal_reason is not None:
        return False
    for value in response.fields.values():
        if isinstance(value, IntResponseValue):
            if value.int > 0:
                return True
        elif isinstance(value, BoolResponseValue):
            if value.bool:
                return True
        elif isinstance(value, FloatResponseValue):
            if value.float > 0.0:
                return True
        elif isinstance(value, HistogramResponseValue):
            if sum(value.histogram) > 0:
                return True
        elif isinstance(value, HashListResponseValue):
            if value.hash_list:
                return True
        else:  # pragma: no cover - unreachable under the typed ResponseValue union
            return True
    return False
