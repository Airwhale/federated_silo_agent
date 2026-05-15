"""Deterministic F5 compliance audit over normalized audit artifacts."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend import BACKEND_ROOT
from backend.agents.base import Agent, AuditEmitter
from backend.agents.llm_client import LLMClient
from backend.runtime.context import AgentRuntimeContext, TrustDomain
from shared.enums import AgentRole, AuditEventKind, BankId, MessageType, PolicySeverity
from shared.messages import (
    AuditEvent,
    AuditReviewRequest,
    AuditReviewResult,
    BudgetExhaustedPayload,
    ComplianceFinding,
    ConstraintViolationPayload,
    DismissalRationale,
    LtVerdictPayload,
    MessageSentPayload,
    RhoDebitedPayload,
)


PROMPT_PATH = BACKEND_ROOT / "agents" / "prompts" / "f5_system.md"
F5_AGENT_ID = "federation.F5"

DEFAULT_MAX_QUERIES = 5
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_BUDGET_PRESSURE_RHO_REMAINING = 0.05

RATE_LIMIT_FINDING = "rate_limit"
BUDGET_PRESSURE_FINDING = "budget_pressure"
MISSING_LT_VERDICT_FINDING = "missing_lt_verdict"
LT_VERDICT_REVIEW_FINDING = "lt_verdict_review"
ROUTE_ANOMALY_FINDING = "route_anomaly"
PURPOSE_REVIEW_FINDING = "purpose_review"
DISMISSAL_REVIEW_FINDING = "dismissal_review"

_ROUTE_ANOMALY_TERMS = (
    "route",
    "unauthorized",
    "wrong_role",
    "wrong role",
    "principal",
    "allowlist",
    "signature",
    "replay",
)
_PURPOSE_ANOMALY_TERMS = (
    "purpose",
    "314",
    "suspicion",
    "suspicious",
    "ml/tf",
    "money laundering",
    "terrorist financing",
)
_VAGUE_DISMISSAL_REASONS = {
    "ok",
    "fine",
    "no issue",
    "not suspicious",
    "looks fine",
    "dismissed",
    "n/a",
}


class F5AuditConfig(BaseModel):
    """Configurable deterministic thresholds for F5 audit checks."""

    max_queries: int = Field(default=DEFAULT_MAX_QUERIES, ge=1)
    window_seconds: int = Field(default=DEFAULT_WINDOW_SECONDS, ge=1)
    budget_pressure_rho_remaining: float = Field(
        default=DEFAULT_BUDGET_PRESSURE_RHO_REMAINING,
        ge=0.0,
    )
    rate_limited_message_type: str = MessageType.SEC314B_QUERY.value
    governed_message_types: tuple[str, ...] = (
        MessageType.SEC314B_QUERY.value,
        MessageType.LOCAL_SILO_CONTRIBUTION_REQUEST.value,
        MessageType.SEC314B_RESPONSE.value,
        MessageType.SANCTIONS_CHECK_REQUEST.value,
        MessageType.GRAPH_PATTERN_REQUEST.value,
        MessageType.SAR_ASSEMBLY_REQUEST.value,
    )
    lt_allow_verdicts: tuple[str, ...] = ("allow", "allowed", "pass")

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


@lru_cache(maxsize=8)
def load_prompt(path: Path = PROMPT_PATH) -> str:
    """Load the versioned F5 prompt for future optional anomaly review."""
    return path.read_text(encoding="utf-8")


class F5ComplianceAuditorAgent(Agent[AuditReviewRequest, AuditReviewResult]):
    """Read-only deterministic compliance auditor.

    F5 is implemented as a deterministic audit engine in P13. It loads a prompt
    for a future optional explanation or anomaly-review path, but runtime
    compliance findings are decided only by typed audit inputs and Python rules.
    """

    agent_id = F5_AGENT_ID
    role = AgentRole.F5
    bank_id = BankId.FEDERATION
    input_schema = AuditReviewRequest
    output_schema = AuditReviewResult
    declared_intent = "federation_compliance_audit"

    def __init__(
        self,
        *,
        runtime: AgentRuntimeContext,
        config: F5AuditConfig | None = None,
        llm: LLMClient | None = None,
        audit: AuditEmitter | None = None,
    ) -> None:
        if runtime.trust_domain != TrustDomain.FEDERATION:
            raise ValueError("F5 must run in the federation trust domain")
        self.config = config or F5AuditConfig()
        self.system_prompt = load_prompt()
        super().__init__(runtime=runtime, llm=llm, audit=audit)

    def run(self, input_data: AuditReviewRequest | object) -> AuditReviewResult:
        """Return deterministic compliance findings for the supplied audit window."""
        request = self._validate_input(input_data)

        findings = [
            *self._rate_limit_findings(request.audit_events),
            *self._budget_pressure_findings(request.audit_events),
            *self._lt_verdict_findings(request.audit_events),
            *self._route_and_purpose_findings(request.audit_events),
            *self._dismissal_findings(request.dismissals),
        ]
        rate_limit_triggered = any(finding.kind == RATE_LIMIT_FINDING for finding in findings)
        # P13 treats every generated F5 finding as review-worthy. If later
        # informational findings are added, this should inspect kind/severity.
        human_review_required = bool(findings)

        result = AuditReviewResult(
            sender_agent_id=self.agent_id,
            sender_role=self.role,
            sender_bank_id=self.bank_id,
            recipient_agent_id=request.sender_agent_id,
            in_reply_to=request.message_id,
            review_scope=request.review_scope,
            findings=findings,
            human_review_required=human_review_required,
            rate_limit_triggered=rate_limit_triggered,
        )

        if rate_limit_triggered:
            self._emit(
                kind=AuditEventKind.RATE_LIMIT,
                phase="review",
                status="flagged",
                detail="One actor exceeded the configured query rate limit.",
                model_name="deterministic_f5",
            )
        if human_review_required:
            self._emit(
                kind=AuditEventKind.HUMAN_REVIEW,
                phase="review",
                status="flagged",
                detail="F5 emitted one or more compliance findings requiring review.",
                model_name="deterministic_f5",
            )
        self._emit(
            kind=AuditEventKind.MESSAGE_SENT,
            phase="return",
            status="ok",
            detail=f"Reviewed {len(request.audit_events)} audit event(s).",
            model_name="deterministic_f5",
        )
        return result

    def _rate_limit_findings(self, events: Iterable[AuditEvent]) -> list[ComplianceFinding]:
        events_by_actor: dict[str, list[AuditEvent]] = defaultdict(list)
        for event in events:
            if not isinstance(event.payload, MessageSentPayload):
                continue
            if event.payload.message_type != self.config.rate_limited_message_type:
                continue
            events_by_actor[event.payload.source_agent_id].append(event)

        findings: list[ComplianceFinding] = []
        for actor_id, actor_events in events_by_actor.items():
            sorted_events = sorted(actor_events, key=lambda event: event.created_at)
            window: deque[AuditEvent] = deque()
            for event in sorted_events:
                while (
                    window
                    and (event.created_at - window[0].created_at).total_seconds()
                    > self.config.window_seconds
                ):
                    window.popleft()
                window.append(event)
                if len(window) <= self.config.max_queries:
                    continue
                findings.append(
                    ComplianceFinding(
                        kind=RATE_LIMIT_FINDING,
                        severity=PolicySeverity.HIGH,
                        detail=(
                            f"{actor_id} sent {len(window)} query messages inside "
                            f"{self.config.window_seconds} seconds."
                        ),
                        related_event_ids=[item.event_id for item in window],
                    )
                )
                window.clear()
        return findings

    def _budget_pressure_findings(
        self,
        events: Iterable[AuditEvent],
    ) -> list[ComplianceFinding]:
        exhausted_events: list[AuditEvent] = []
        low_remaining_events: list[AuditEvent] = []
        for event in events:
            if isinstance(event.payload, BudgetExhaustedPayload):
                exhausted_events.append(event)
            elif (
                isinstance(event.payload, RhoDebitedPayload)
                and event.payload.rho_remaining <= self.config.budget_pressure_rho_remaining
            ):
                low_remaining_events.append(event)

        findings: list[ComplianceFinding] = []
        if exhausted_events:
            findings.append(
                ComplianceFinding(
                    kind=BUDGET_PRESSURE_FINDING,
                    severity=PolicySeverity.HIGH,
                    detail=(
                        "One or more privacy-budget requests were refused because "
                        "the configured budget was exhausted."
                    ),
                    related_event_ids=_event_ids(exhausted_events),
                )
            )

        if low_remaining_events:
            findings.append(
                ComplianceFinding(
                    kind=BUDGET_PRESSURE_FINDING,
                    severity=PolicySeverity.MEDIUM,
                    detail=(
                        "Privacy budget remaining is at or below the configured "
                        "pressure threshold."
                    ),
                    related_event_ids=_event_ids(low_remaining_events),
                )
            )

        return findings

    def _lt_verdict_findings(self, events: Iterable[AuditEvent]) -> list[ComplianceFinding]:
        event_list = list(events)
        covered_requests: set[str] = set()
        non_allow_verdicts: list[AuditEvent] = []
        allowed_verdicts = {verdict.lower() for verdict in self.config.lt_allow_verdicts}

        for event in event_list:
            if not isinstance(event.payload, LtVerdictPayload):
                continue
            verdict = event.payload.verdict.strip().lower()
            if event.payload.request_id is not None:
                covered_requests.add(event.payload.request_id)
            if verdict not in allowed_verdicts:
                non_allow_verdicts.append(event)

        findings: list[ComplianceFinding] = []
        governed_messages = [
            event
            for event in event_list
            if _is_cross_boundary_governed_message(event, self.config)
        ]
        missing = [
            event for event in governed_messages if str(event.event_id) not in covered_requests
        ]
        if missing:
            findings.append(
                ComplianceFinding(
                    kind=MISSING_LT_VERDICT_FINDING,
                    severity=PolicySeverity.HIGH,
                    detail=(
                        "One or more governed cross-boundary messages have no "
                        "matching allow verdict from Lobster Trap."
                    ),
                    related_event_ids=_event_ids(missing),
                )
            )
        if non_allow_verdicts:
            findings.append(
                ComplianceFinding(
                    kind=LT_VERDICT_REVIEW_FINDING,
                    severity=PolicySeverity.HIGH,
                    detail=(
                        "One or more Lobster Trap verdicts were not allow verdicts "
                        "and require compliance review."
                    ),
                    related_event_ids=_event_ids(non_allow_verdicts),
                )
            )
        return findings

    def _route_and_purpose_findings(
        self,
        events: Iterable[AuditEvent],
    ) -> list[ComplianceFinding]:
        route_events: list[AuditEvent] = []
        purpose_events: list[AuditEvent] = []
        for event in events:
            if not isinstance(event.payload, ConstraintViolationPayload):
                continue
            violation = event.payload.violation.lower()
            if any(term in violation for term in _ROUTE_ANOMALY_TERMS):
                route_events.append(event)
            if any(term in violation for term in _PURPOSE_ANOMALY_TERMS):
                purpose_events.append(event)

        findings: list[ComplianceFinding] = []
        if route_events:
            findings.append(
                ComplianceFinding(
                    kind=ROUTE_ANOMALY_FINDING,
                    severity=PolicySeverity.HIGH,
                    detail=(
                        "Route, identity, signature, or replay control anomalies "
                        "were recorded in the audit stream."
                    ),
                    related_event_ids=_event_ids(route_events),
                )
            )
        if purpose_events:
            findings.append(
                ComplianceFinding(
                    kind=PURPOSE_REVIEW_FINDING,
                    severity=PolicySeverity.HIGH,
                    detail=(
                        "Purpose-declaration anomalies were recorded in the audit "
                        "stream."
                    ),
                    related_event_ids=_event_ids(purpose_events),
                )
            )
        return findings

    @staticmethod
    def _dismissal_findings(
        dismissals: Iterable[DismissalRationale],
    ) -> list[ComplianceFinding]:
        return [
            _dismissal_finding(dismissal)
            for dismissal in dismissals
            if _dismissal_is_vague(dismissal)
        ]


def _dismissal_finding(dismissal: DismissalRationale) -> ComplianceFinding:
    return ComplianceFinding(
        kind=DISMISSAL_REVIEW_FINDING,
        severity=PolicySeverity.MEDIUM,
        detail=(
            "Dismissal rationale for alert "
            f"{dismissal.alert_id} is too thin for compliance review."
        ),
        related_event_ids=[dismissal.message_id],
    )


def _event_ids(events: Iterable[AuditEvent]) -> list[UUID]:
    return [event.event_id for event in events]


def _dismissal_is_vague(dismissal: DismissalRationale) -> bool:
    reason = dismissal.reason.strip().lower()
    word_count = len(reason.split())
    return (
        reason in _VAGUE_DISMISSAL_REASONS
        or (word_count < 4 and not dismissal.evidence_considered)
    )


def _is_cross_boundary_governed_message(
    event: AuditEvent,
    config: F5AuditConfig,
) -> bool:
    if not isinstance(event.payload, MessageSentPayload):
        return False
    if event.payload.message_type not in config.governed_message_types:
        return False
    return _agent_domain(event.payload.source_agent_id) != _agent_domain(
        event.payload.destination_agent_id
    )


def _agent_domain(agent_id: str) -> str:
    return agent_id.split(".", maxsplit=1)[0]
