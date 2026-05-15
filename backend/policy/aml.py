"""Deterministic AML policy adapter for the F6 policy actor."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from backend.policy.redaction import CustomerNameRedactor, load_customer_name_redactor
from backend.security import (
    PrincipalAllowlist,
    ReplayCache,
    SecurityEnvelopeError,
    approved_body_hash,
)
from backend.security.exceptions import PrincipalNotAllowed, ReplayDetected, SignatureInvalid
from shared.enums import (
    AgentRole,
    AuditEventKind,
    BankId,
    MessageType,
    PolicyContentChannel,
    PolicyDecision,
    PolicySeverity,
    RouteKind,
    TypologyCode,
)
from shared.messages import (
    AgentMessage,
    AuditEvent,
    ConstraintViolationPayload,
    LocalSiloContributionRequest,
    LtVerdictPayload,
    MessageSentPayload,
    PolicyEvaluationRequest,
    PolicyEvaluationResult,
    PolicyRuleHit,
    RateLimitPayload,
    Sec314bQuery,
    Sec314bResponse,
    utc_now,
)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
_DECISION_RANK: dict[PolicyDecision, int] = {
    PolicyDecision.ALLOW: 0,
    PolicyDecision.REDACT: 1,
    PolicyDecision.ESCALATE: 2,
    PolicyDecision.BLOCK: 3,
}
_PROMPT_INJECTION_RE = re.compile(
    r"("
    r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
    r"<\s*/?\s*system\s*>|"
    r"\bDAN\b|do\s+anything\s+now|"
    r"jailbreak|"
    r"reveal\s+(?:your\s+)?(?:system|developer)\s+(?:prompt|instructions)|"
    r"decode\s+this\s+base64|"
    r"base64\s+payload"
    r")",
    re.IGNORECASE,
)
_PRIVATE_DATA_RE = re.compile(
    r"("
    r"\bSSN\b|social\s+security|home\s+address|account\s+number|"
    r"raw\s+(?:customer|transaction|account)|"
    r"customer\s+name|private\s+key|api\s+key|"
    r"all\s+customer\s+records|upload\s+.*pastebin|"
    r"/etc/shadow|rm\s+-rf"
    r")",
    re.IGNORECASE,
)


class AmlPolicyConfig(BaseModel):
    """Runtime knobs for deterministic F6 policy evaluation."""

    policy_agent_id: NonEmptyStr = "federation.F6"
    policy_bank_id: BankId = BankId.FEDERATION
    audit_recipient_agent_id: NonEmptyStr = "federation.audit"
    sec314b_rate_limit_threshold: int = Field(default=20, ge=1)
    sec314b_rate_limit_window_seconds: int = Field(default=3600, ge=1)

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class RawPolicyContent(BaseModel):
    """Pre-boundary text submitted for policy scanning before shared validation."""

    evaluated_message_type: MessageType | None = None
    evaluated_sender_agent_id: NonEmptyStr
    evaluated_sender_role: AgentRole
    evaluated_sender_bank_id: BankId
    content_channel: PolicyContentChannel
    content_summary: str = Field(min_length=1, max_length=5000)
    declared_purpose: str | None = Field(default=None, max_length=5000)

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    @property
    def content_hash(self) -> str:
        payload = "\n".join(
            (
                self.evaluated_message_type.value
                if self.evaluated_message_type is not None
                else "",
                self.evaluated_sender_agent_id,
                self.evaluated_sender_role.value,
                self.evaluated_sender_bank_id.value,
                self.content_channel.value,
                self.content_summary,
                self.declared_purpose or "",
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AmlPolicyEvaluation(BaseModel):
    """Full deterministic adapter output around the shared policy result."""

    result: PolicyEvaluationResult
    audit_events: list[AuditEvent] = Field(default_factory=list)
    sanitized_content_summary: str
    sanitized_declared_purpose: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class LobsterTrapAuditRecord(BaseModel):
    """Supported subset of a Lobster Trap verdict or JSONL audit record."""

    request_id: NonEmptyStr | None = None
    verdict: NonEmptyStr
    action: NonEmptyStr
    rule_name: NonEmptyStr | None = None

    model_config = ConfigDict(extra="allow", strict=True, validate_assignment=True)

    @field_validator("verdict", "action", "rule_name")
    @classmethod
    def normalize_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip()


class NormalizedLobsterTrapAudit(BaseModel):
    """LT audit normalization preserving fields that P4 AuditEvent cannot hold."""

    request_id: str | None
    verdict: str
    action: str
    rule_name: str | None
    audit_event: AuditEvent

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class RateLimitTracker:
    """In-memory advisory counter for F6 policy evaluations."""

    def __init__(self, *, threshold: int, window: timedelta) -> None:
        self.threshold = threshold
        self.window = window
        self._events: dict[str, deque[datetime]] = defaultdict(deque)

    def record(self, requester_id: str, *, now: datetime) -> int:
        now = _normalize_now(now)
        entries = self._events[requester_id]
        cutoff = now - self.window
        while entries and entries[0] <= cutoff:
            entries.popleft()
        entries.append(now)
        return len(entries)

    def count(self, requester_id: str, *, now: datetime | None = None) -> int:
        now_value = _normalize_now(now)
        entries = self._events[requester_id]
        cutoff = now_value - self.window
        while entries and entries[0] <= cutoff:
            entries.popleft()
        return len(entries)


class AmlPolicyEvaluator:
    """Mostly deterministic F6 policy evaluator.

    The evaluator is deterministic by default. It does not call an LLM and it
    does not mutate signing, replay, route approvals, DP ledgers, or A3
    primitive decisions. Optional allowlist and replay-cache arguments let it
    observe the same signed-envelope checks as other runtime components.
    """

    def __init__(
        self,
        *,
        config: AmlPolicyConfig | None = None,
        redactor: CustomerNameRedactor | None = None,
        rate_limiter: RateLimitTracker | None = None,
    ) -> None:
        self.config = config or AmlPolicyConfig()
        self.redactor = redactor or load_customer_name_redactor()
        self.rate_limiter = rate_limiter or RateLimitTracker(
            threshold=self.config.sec314b_rate_limit_threshold,
            window=timedelta(seconds=self.config.sec314b_rate_limit_window_seconds),
        )

    def evaluate(
        self,
        request: PolicyEvaluationRequest,
        *,
        evaluated_message: AgentMessage | None = None,
        principal_allowlist: PrincipalAllowlist | None = None,
        replay_cache: ReplayCache | None = None,
        now: datetime | None = None,
    ) -> AmlPolicyEvaluation:
        """Evaluate one F6 request and optional typed message under policy."""
        now_value = _normalize_now(now)
        text = _PolicyText(
            content_summary=request.content_summary,
            declared_purpose=request.declared_purpose,
        )
        return self._evaluate_text_and_message(
            request=request,
            text=text,
            evaluated_message=evaluated_message,
            principal_allowlist=principal_allowlist,
            replay_cache=replay_cache,
            now=now_value,
        )

    def evaluate_raw_content(
        self,
        raw_content: RawPolicyContent,
        *,
        request_sender_agent_id: str = "policy.client",
        request_sender_role: AgentRole = AgentRole.ORCHESTRATOR,
        request_sender_bank_id: BankId = BankId.FEDERATION,
        now: datetime | None = None,
    ) -> AmlPolicyEvaluation:
        """Evaluate pre-boundary content that may still need redaction."""
        request = PolicyEvaluationRequest.model_construct(
            sender_agent_id=request_sender_agent_id,
            sender_role=request_sender_role,
            sender_bank_id=request_sender_bank_id,
            recipient_agent_id=self.config.policy_agent_id,
            evaluated_message_type=raw_content.evaluated_message_type,
            evaluated_sender_agent_id=raw_content.evaluated_sender_agent_id,
            evaluated_sender_role=raw_content.evaluated_sender_role,
            evaluated_sender_bank_id=raw_content.evaluated_sender_bank_id,
            content_channel=raw_content.content_channel,
            content_hash=raw_content.content_hash,
            content_summary=raw_content.content_summary,
            declared_purpose=raw_content.declared_purpose,
        )
        text = _PolicyText(
            content_summary=raw_content.content_summary,
            declared_purpose=raw_content.declared_purpose,
        )
        return self._evaluate_text_and_message(
            request=request,
            text=text,
            evaluated_message=None,
            principal_allowlist=None,
            replay_cache=None,
            now=_normalize_now(now),
        )

    def normalize_lobstertrap_audit(
        self,
        raw_record: Mapping[str, Any] | LobsterTrapAuditRecord,
        *,
        actor_agent_id: str | None = None,
    ) -> NormalizedLobsterTrapAudit:
        """Convert LT verdict metadata into a normalized audit event."""
        record = (
            raw_record
            if isinstance(raw_record, LobsterTrapAuditRecord)
            else LobsterTrapAuditRecord.model_validate(raw_record)
        )
        event = self._audit_event(
            kind=AuditEventKind.LT_VERDICT,
            actor_agent_id=actor_agent_id or self.config.policy_agent_id,
            payload=LtVerdictPayload(
                verdict=record.verdict,
                request_id=record.request_id,
                rule_name=record.rule_name,
            ),
        )
        return NormalizedLobsterTrapAudit(
            request_id=record.request_id,
            verdict=record.verdict,
            action=record.action,
            rule_name=record.rule_name,
            audit_event=event,
        )

    def _evaluate_text_and_message(
        self,
        *,
        request: PolicyEvaluationRequest,
        text: _PolicyText,
        evaluated_message: AgentMessage | None,
        principal_allowlist: PrincipalAllowlist | None,
        replay_cache: ReplayCache | None,
        now: datetime,
    ) -> AmlPolicyEvaluation:
        sanitized_text, redacted_fields = self._redact_policy_text(text)
        block_hits = self._blocking_hits(request, sanitized_text)
        audit_events: list[AuditEvent] = []

        if evaluated_message is not None:
            security_hit = self._verify_security(
                evaluated_message,
                principal_allowlist=principal_allowlist,
                replay_cache=replay_cache,
                now=now,
            )
            if security_hit is not None:
                block_hits.append(security_hit)
            route_hit = self._route_hit(evaluated_message)
            if route_hit is not None:
                block_hits.append(route_hit)
            purpose_hit = self._message_purpose_hit(evaluated_message)
            if purpose_hit is not None:
                block_hits.append(purpose_hit)

        request_purpose_hit = self._request_purpose_hit(request, sanitized_text)
        if request_purpose_hit is not None:
            block_hits.append(request_purpose_hit)

        if block_hits:
            audit_events.append(self._constraint_event(block_hits[0]))
            return self._evaluation(
                request=request,
                decision=PolicyDecision.BLOCK,
                rule_hits=block_hits,
                audit_events=audit_events,
                sanitized_text=sanitized_text,
                summary="AML policy blocked this content before release.",
            )

        if redacted_fields:
            hit = PolicyRuleHit(
                rule_id="F6-REDACT-CUSTOMER-NAME",
                decision=PolicyDecision.REDACT,
                severity=PolicySeverity.MEDIUM,
                detail="Policy redacted customer-identifying text before release.",
                redacted_fields=redacted_fields,
            )
            audit_events.append(self._constraint_event(hit, blocked=False))
            return self._evaluation(
                request=request,
                decision=PolicyDecision.REDACT,
                rule_hits=[hit],
                audit_events=audit_events,
                sanitized_text=sanitized_text,
                summary="AML policy redacted customer-identifying text before release.",
            )

        rate_hit = self._rate_limit_hit(evaluated_message, now=now)
        if rate_hit is not None:
            audit_events.append(self._rate_limit_event(evaluated_message))
            return self._evaluation(
                request=request,
                decision=PolicyDecision.ESCALATE,
                rule_hits=[rate_hit],
                audit_events=audit_events,
                sanitized_text=sanitized_text,
                summary="AML policy allowed the content with a rate-limit advisory.",
            )

        audit_events.append(
            self._audit_event(
                kind=AuditEventKind.MESSAGE_SENT,
                actor_agent_id=self.config.policy_agent_id,
                payload=MessageSentPayload(
                    message_type=MessageType.POLICY_EVALUATION_RESULT.value,
                    source_agent_id=self.config.policy_agent_id,
                    destination_agent_id=request.sender_agent_id,
                ),
            )
        )
        return self._evaluation(
            request=request,
            decision=PolicyDecision.ALLOW,
            rule_hits=[],
            audit_events=audit_events,
            sanitized_text=sanitized_text,
            summary="AML policy allowed hash-only content.",
        )

    def _redact_policy_text(
        self,
        text: _PolicyText,
    ) -> tuple[_PolicyText, list[str]]:
        fields: list[str] = []
        content = self.redactor.redact(text.content_summary)
        if content.redaction_count:
            fields.append("content_summary")

        declared_purpose = None
        if text.declared_purpose is not None:
            declared = self.redactor.redact(text.declared_purpose)
            declared_purpose = declared.text
            if declared.redaction_count:
                fields.append("declared_purpose")

        return (
            _PolicyText(
                content_summary=content.text,
                declared_purpose=declared_purpose,
            ),
            fields,
        )

    def _blocking_hits(
        self,
        request: PolicyEvaluationRequest,
        text: _PolicyText,
    ) -> list[PolicyRuleHit]:
        combined = f"{text.content_summary}\n{text.declared_purpose or ''}"
        hits: list[PolicyRuleHit] = []
        if _PROMPT_INJECTION_RE.search(combined):
            hits.append(
                _rule_hit(
                    rule_id="F6-B1-PROMPT-INJECTION",
                    detail="Policy detected prompt-injection or jailbreak content.",
                    severity=PolicySeverity.CRITICAL,
                )
            )
        if _PRIVATE_DATA_RE.search(combined):
            hits.append(
                _rule_hit(
                    rule_id="F6-B2-PRIVATE-DATA-EXTRACTION",
                    detail="Policy detected a private-data extraction request.",
                    severity=PolicySeverity.CRITICAL,
                )
            )
        if request.evaluated_sender_role == AgentRole.A1 and (
            request.evaluated_message_type != MessageType.ALERT
        ):
            hits.append(
                _rule_hit(
                    rule_id="F6-B3-ROLE-ROUTE",
                    detail="A1 may only emit local alert messages.",
                    severity=PolicySeverity.HIGH,
                )
            )
        return hits

    def _verify_security(
        self,
        message: AgentMessage,
        *,
        principal_allowlist: PrincipalAllowlist | None,
        replay_cache: ReplayCache | None,
        now: datetime,
    ) -> PolicyRuleHit | None:
        if principal_allowlist is None:
            return None
        try:
            principal_allowlist.verify_message(
                message,
                replay_cache=replay_cache,
                now=now,
            )
            route_approval = getattr(message, "route_approval", None)
            if route_approval is not None:
                principal_allowlist.verify_route_approval(
                    route_approval,
                    now=now,
                )
                if route_approval.approved_query_body_hash != approved_body_hash(
                    message
                ):
                    return _rule_hit(
                        rule_id="F6-B4-ROUTE-BINDING",
                        detail="Route approval body hash did not match the evaluated message.",
                        severity=PolicySeverity.CRITICAL,
                    )
        except ReplayDetected:
            return _rule_hit(
                rule_id="F6-B5-REPLAY",
                detail="Replay cache detected a previously accepted nonce.",
                severity=PolicySeverity.CRITICAL,
            )
        except SignatureInvalid:
            return _rule_hit(
                rule_id="F6-B6-SIGNATURE",
                detail="Signature or canonical body hash verification failed.",
                severity=PolicySeverity.CRITICAL,
            )
        except PrincipalNotAllowed:
            return _rule_hit(
                rule_id="F6-B7-PRINCIPAL",
                detail="Verified principal is not allowed for this policy action.",
                severity=PolicySeverity.HIGH,
            )
        except SecurityEnvelopeError:
            return _rule_hit(
                rule_id="F6-B8-ENVELOPE",
                detail="Security envelope validation failed.",
                severity=PolicySeverity.HIGH,
            )
        return None

    def _route_hit(self, message: AgentMessage) -> PolicyRuleHit | None:
        if isinstance(message, Sec314bQuery):
            if message.sender_role == AgentRole.A2:
                if message.recipient_agent_id != "federation.F1":
                    return _route_violation("A2 Sec314bQuery must route through F1.")
                if message.requesting_bank_id in message.target_bank_ids:
                    return _route_violation("Peer query cannot target requester bank.")
                return None
            if message.sender_role == AgentRole.F1:
                approval = message.route_approval
                if approval is None:
                    return _route_violation("F1-routed Sec314bQuery requires approval.")
                if approval.route_kind != RouteKind.PEER_314B:
                    return _route_violation("Sec314bQuery requires peer_314b route kind.")
                if approval.responding_bank_id == approval.requesting_bank_id:
                    return _route_violation("Peer route cannot target requester bank.")
                if message.recipient_agent_id != _a3_agent_id(approval.responding_bank_id):
                    return _route_violation("Peer route recipient must match A3 target.")
                return None
            return _route_violation("Sec314bQuery sender role is not allowed.")

        if isinstance(message, LocalSiloContributionRequest):
            if message.sender_role != AgentRole.F1:
                return _route_violation("Local contribution must be sent by F1.")
            if message.route_approval.route_kind != RouteKind.LOCAL_CONTRIBUTION:
                return _route_violation(
                    "Local contribution requires local_contribution route kind."
                )
            if message.requesting_bank_id != message.responding_bank_id:
                return _route_violation(
                    "Local contribution must target the requester bank."
                )
            if message.recipient_agent_id != _a3_agent_id(message.responding_bank_id):
                return _route_violation("Local contribution recipient must be A3.")
            return None

        if isinstance(message, Sec314bResponse):
            if message.sender_role == AgentRole.A3 and message.recipient_agent_id == "federation.F1":
                return None
            if message.sender_role == AgentRole.F1 and message.recipient_agent_id.endswith(".A2"):
                return None
            return _route_violation("Sec314bResponse route is not allowed.")

        return None

    def _message_purpose_hit(self, message: AgentMessage) -> PolicyRuleHit | None:
        if not isinstance(message, (Sec314bQuery, LocalSiloContributionRequest)):
            return None
        purpose = message.purpose_declaration
        if purpose.authority != "USA_PATRIOT_314b":
            return _purpose_violation("Section 314(b) authority is missing.")
        if purpose.typology_code not in set(TypologyCode):
            return _purpose_violation("Purpose typology is unsupported.")
        if not purpose.suspicion_rationale.strip():
            return _purpose_violation("Suspicion rationale is required.")
        return None

    def _request_purpose_hit(
        self,
        request: PolicyEvaluationRequest,
        text: _PolicyText,
    ) -> PolicyRuleHit | None:
        if request.evaluated_message_type not in {
            MessageType.SEC314B_QUERY,
            MessageType.LOCAL_SILO_CONTRIBUTION_REQUEST,
        }:
            return None
        if text.declared_purpose is None or not text.declared_purpose.strip():
            return _purpose_violation("Declared Section 314(b) purpose is required.")
        return None

    def _rate_limit_hit(
        self,
        message: AgentMessage | None,
        *,
        now: datetime,
    ) -> PolicyRuleHit | None:
        if not isinstance(message, Sec314bQuery):
            return None
        if message.sender_role != AgentRole.A2:
            return None
        count = self.rate_limiter.record(message.requesting_investigator_id, now=now)
        if count <= self.config.sec314b_rate_limit_threshold:
            return None
        return PolicyRuleHit(
            rule_id="F6-RATE-LIMIT-ADVISORY",
            decision=PolicyDecision.ESCALATE,
            severity=PolicySeverity.MEDIUM,
            detail="Investigator exceeded the F6 hourly Section 314(b) advisory threshold.",
        )

    def _rate_limit_event(self, message: AgentMessage | None) -> AuditEvent:
        requester_id = (
            message.requesting_investigator_id
            if isinstance(message, Sec314bQuery)
            else "unknown"
        )
        count = self.rate_limiter.count(requester_id)
        return self._audit_event(
            kind=AuditEventKind.RATE_LIMIT,
            actor_agent_id=self.config.policy_agent_id,
            payload=RateLimitPayload(
                requester_id=requester_id,
                window_seconds=self.config.sec314b_rate_limit_window_seconds,
                count=count,
                limit=self.config.sec314b_rate_limit_threshold,
            ),
        )

    def _constraint_event(
        self,
        hit: PolicyRuleHit,
        *,
        blocked: bool = True,
    ) -> AuditEvent:
        return self._audit_event(
            kind=AuditEventKind.CONSTRAINT_VIOLATION,
            actor_agent_id=self.config.policy_agent_id,
            payload=ConstraintViolationPayload(
                violation=hit.rule_id,
                blocked=blocked,
            ),
        )

    def _audit_event(
        self,
        *,
        kind: AuditEventKind,
        actor_agent_id: str,
        payload: Any,
    ) -> AuditEvent:
        return AuditEvent(
            sender_agent_id=self.config.policy_agent_id,
            sender_role=AgentRole.F6,
            sender_bank_id=self.config.policy_bank_id,
            recipient_agent_id=self.config.audit_recipient_agent_id,
            kind=kind,
            actor_agent_id=actor_agent_id,
            payload=payload,
        )

    def _evaluation(
        self,
        *,
        request: PolicyEvaluationRequest,
        decision: PolicyDecision,
        rule_hits: list[PolicyRuleHit],
        audit_events: list[AuditEvent],
        sanitized_text: _PolicyText,
        summary: str,
    ) -> AmlPolicyEvaluation:
        if rule_hits:
            decision = max(
                (hit.decision for hit in rule_hits),
                key=lambda item: _DECISION_RANK[item],
            )
        result = PolicyEvaluationResult(
            sender_agent_id=self.config.policy_agent_id,
            sender_role=AgentRole.F6,
            sender_bank_id=self.config.policy_bank_id,
            recipient_agent_id=request.sender_agent_id,
            in_reply_to=request.message_id,
            decision=decision,
            rule_hits=rule_hits,
            safe_output_summary=summary,
            redacted_field_count=(
                sum(len(hit.redacted_fields) for hit in rule_hits)
                if decision == PolicyDecision.REDACT
                else 0
            ),
        )
        return AmlPolicyEvaluation(
            result=result,
            audit_events=audit_events,
            sanitized_content_summary=sanitized_text.content_summary,
            sanitized_declared_purpose=sanitized_text.declared_purpose,
        )


class _PolicyText(BaseModel):
    content_summary: str
    declared_purpose: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


def normalize_lobstertrap_audit(
    raw_record: Mapping[str, Any] | LobsterTrapAuditRecord,
    *,
    evaluator: AmlPolicyEvaluator | None = None,
) -> NormalizedLobsterTrapAudit:
    """Module-level convenience wrapper for LT audit normalization."""
    return (evaluator or AmlPolicyEvaluator()).normalize_lobstertrap_audit(raw_record)


def _rule_hit(
    *,
    rule_id: str,
    detail: str,
    severity: PolicySeverity,
) -> PolicyRuleHit:
    return PolicyRuleHit(
        rule_id=rule_id,
        decision=PolicyDecision.BLOCK,
        severity=severity,
        detail=detail,
    )


def _route_violation(detail: str) -> PolicyRuleHit:
    return _rule_hit(
        rule_id="F6-B3-ROLE-ROUTE",
        detail=detail,
        severity=PolicySeverity.HIGH,
    )


def _purpose_violation(detail: str) -> PolicyRuleHit:
    return _rule_hit(
        rule_id="F6-B9-PURPOSE",
        detail=detail,
        severity=PolicySeverity.HIGH,
    )


def _a3_agent_id(bank_id: BankId) -> str:
    return f"{bank_id.value}.A3"


def _normalize_now(now: datetime | None) -> datetime:
    value = now or utc_now()
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)
