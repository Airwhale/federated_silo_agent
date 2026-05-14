"""Shared agent runtime with deterministic rule plumbing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Generic, Protocol, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.agents.llm_client import LLMClient, LobsterTrapMetadata
from backend.agents.rules import BypassRule, ConstraintRule
from backend.runtime.context import AgentRuntimeContext
from shared.enums import AgentRole, AuditEventKind, BankId


InT = TypeVar("InT", bound=BaseModel)
OutT = TypeVar("OutT", bound=BaseModel)


class AgentRuntimeError(RuntimeError):
    """Base class for runtime failures raised by agents."""


class InvalidAgentInput(AgentRuntimeError):
    """Raised when an agent receives the wrong input boundary object."""


class LLMOutputUnparseable(AgentRuntimeError):
    """Raised when the LLM cannot produce the requested schema after repair."""


class ConstraintViolation(AgentRuntimeError):
    """Raised when repaired LLM output still violates deterministic rules."""


class RuntimeAuditEvent(BaseModel):
    """Runtime-only audit event emitted before wire AuditEvent conversion."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: AuditEventKind
    run_id: str
    node_id: str
    agent_id: str
    role: AgentRole
    phase: str
    status: str
    detail: str | None = None
    rule_name: str | None = None
    retry_count: int = Field(default=0, ge=0)
    model_name: str | None = None
    bypass_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid", strict=True)


class AuditEmitter(Protocol):
    """Minimal audit sink needed by the base runtime."""

    def emit(self, event: RuntimeAuditEvent) -> None:
        """Record one audit event."""


class InMemoryAuditEmitter:
    """Test and local-development audit sink."""

    def __init__(self) -> None:
        self.events: list[RuntimeAuditEvent] = []

    def emit(self, event: RuntimeAuditEvent) -> None:
        self.events.append(event)


class Agent(Generic[InT, OutT]):
    """Base class for LLM-backed agents with deterministic rule enforcement."""

    agent_id: str
    role: AgentRole
    bank_id: BankId
    input_schema: type[InT]
    output_schema: type[OutT]
    system_prompt: str
    declared_intent: str = "agent_runtime"
    bypass_rules: tuple[BypassRule[InT, OutT], ...] = ()
    constraint_rules: tuple[ConstraintRule[InT, OutT], ...] = ()

    def __init__(
        self,
        *,
        runtime: AgentRuntimeContext,
        llm: LLMClient | None = None,
        audit: AuditEmitter | None = None,
    ) -> None:
        self.runtime = runtime
        self.llm = llm or LLMClient(runtime.llm)
        self.audit = audit or runtime.audit or InMemoryAuditEmitter()

    def run(self, input_data: InT | object) -> OutT:
        """Validate input, apply bypasses, call the LLM, and enforce constraints."""
        validated_input = self._validate_input(input_data)

        bypassed = self._run_bypass(validated_input)
        if bypassed is not None:
            return bypassed

        retry_count = 0
        output = self._call_and_parse(validated_input)
        violations = self._constraint_violations(validated_input, output)

        if violations:
            rule, message = violations[0]
            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="constraint",
                status="retry",
                detail=message,
                rule_name=rule.name,
                retry_count=retry_count,
            )
            retry_count += 1
            output = self._call_and_parse(
                validated_input,
                repair_instruction=(
                    "Your previous output violated a deterministic constraint. "
                    f"Repair it and return only valid JSON. Constraint: {message}"
                ),
            )
            violations = self._constraint_violations(validated_input, output)
            if violations:
                rule, message = violations[0]
                self._emit(
                    kind=AuditEventKind.CONSTRAINT_VIOLATION,
                    phase="constraint",
                    status="blocked",
                    detail=message,
                    rule_name=rule.name,
                    retry_count=retry_count,
                )
                raise ConstraintViolation(message)

        self._emit(
            kind=AuditEventKind.MESSAGE_SENT,
            phase="return",
            status="ok",
            retry_count=retry_count,
            model_name=self.llm.config.default_model,
        )
        return output

    def _validate_input(self, input_data: InT | object) -> InT:
        try:
            return self.input_schema.model_validate(input_data)
        except ValidationError as exc:
            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="input_validation",
                status="blocked",
                detail=str(exc),
            )
            raise InvalidAgentInput(str(exc)) from exc

    def _run_bypass(self, input_data: InT) -> OutT | None:
        for rule in self.bypass_rules:
            if not rule.trigger(input_data):
                continue
            output = self._validate_forced_output(rule, input_data)
            self._emit(
                kind=AuditEventKind.BYPASS_TRIGGERED,
                phase="bypass",
                status="ok",
                detail=rule.reason,
                rule_name=rule.name,
                bypass_name=rule.name,
            )
            self._emit(
                kind=AuditEventKind.MESSAGE_SENT,
                phase="return",
                status="ok",
                bypass_name=rule.name,
                model_name="deterministic_bypass",
            )
            return output
        return None

    def _validate_forced_output(self, rule: BypassRule[InT, OutT], input_data: InT) -> OutT:
        raw_output = rule.force_output(input_data)
        try:
            return self.output_schema.model_validate(raw_output)
        except ValidationError as exc:
            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="bypass",
                status="blocked",
                detail=str(exc),
                rule_name=rule.name,
            )
            raise ConstraintViolation(str(exc)) from exc

    def _call_and_parse(
        self,
        input_data: InT,
        *,
        repair_instruction: str | None = None,
    ) -> OutT:
        metadata = self._metadata()
        response = self.llm.chat_structured(
            system_prompt=self.system_prompt,
            input_model=input_data,
            output_schema=self.output_schema,
            metadata=metadata,
            repair_instruction=repair_instruction,
        )
        try:
            return self.output_schema.model_validate_json(response.content)
        except ValidationError as first_error:
            if repair_instruction is not None:
                self._emit(
                    kind=AuditEventKind.CONSTRAINT_VIOLATION,
                    phase="llm_parse",
                    status="blocked",
                    detail=str(first_error),
                )
                raise LLMOutputUnparseable(str(first_error)) from first_error

            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="llm_parse",
                status="retry",
                detail=str(first_error),
            )
            repair_response = self.llm.chat_structured(
                system_prompt=self.system_prompt,
                input_model=input_data,
                output_schema=self.output_schema,
                metadata=metadata,
                repair_instruction=(
                    "Your previous output did not match the required JSON schema. "
                    f"Return only valid JSON for {self.output_schema.__name__}. "
                    f"Parser error: {first_error}"
                ),
            )
            try:
                return self.output_schema.model_validate_json(repair_response.content)
            except ValidationError as second_error:
                self._emit(
                    kind=AuditEventKind.CONSTRAINT_VIOLATION,
                    phase="llm_parse",
                    status="blocked",
                    detail=str(second_error),
                    retry_count=1,
                )
                raise LLMOutputUnparseable(str(second_error)) from second_error

    def _constraint_violations(
        self,
        input_data: InT,
        output: OutT,
    ) -> list[tuple[ConstraintRule[InT, OutT], str]]:
        violations: list[tuple[ConstraintRule[InT, OutT], str]] = []
        for rule in self.constraint_rules:
            if rule.check(input_data, output):
                continue
            message = rule.violation_msg(input_data, output)
            violations.append((rule, message))
        return violations

    def _metadata(self) -> LobsterTrapMetadata:
        return LobsterTrapMetadata(
            agent_id=self.agent_id,
            role=self.role,
            bank_id=self.bank_id,
            trust_domain=self.runtime.trust_domain,
            node_id=self.runtime.node_id,
            run_id=self.runtime.run_id,
            declared_intent=self.declared_intent,
            extra=self.runtime.metadata,
        )

    def _emit(
        self,
        *,
        kind: AuditEventKind,
        phase: str,
        status: str,
        detail: str | None = None,
        rule_name: str | None = None,
        retry_count: int = 0,
        model_name: str | None = None,
        bypass_name: str | None = None,
    ) -> None:
        self.audit.emit(
            RuntimeAuditEvent(
                kind=kind,
                run_id=self.runtime.run_id,
                node_id=self.runtime.node_id,
                agent_id=self.agent_id,
                role=self.role,
                phase=phase,
                status=status,
                detail=detail,
                rule_name=rule_name,
                retry_count=retry_count,
                model_name=model_name,
                bypass_name=bypass_name,
            )
        )


# Compatibility alias for older imports. New code should use RuntimeAuditEvent
# and reserve shared.messages.AuditEvent for the signed wire-level event.
AgentAuditEvent = RuntimeAuditEvent
