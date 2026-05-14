from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from backend.agents import (
    Agent,
    BypassRule,
    ConstraintRule,
    ConstraintViolation,
    InMemoryAuditEmitter,
    InvalidAgentInput,
    LLMClient,
    LLMOutputUnparseable,
)
from backend.runtime import AgentRuntimeContext, LLMClientConfig, TrustDomain
from shared.enums import AgentRole, AuditEventKind, BankId


class EchoInput(BaseModel):
    text: str

    model_config = ConfigDict(extra="forbid", strict=True)


class EchoOutput(BaseModel):
    echo: str

    model_config = ConfigDict(extra="forbid", strict=True)


def force_echo(input_data: EchoInput) -> EchoOutput:
    return EchoOutput(echo=input_data.text)


def output_is_short(_input_data: EchoInput, output: EchoOutput) -> bool:
    return len(output.echo) <= 100


def output_too_long_message(_input_data: EchoInput, output: EchoOutput) -> str:
    return f"echo must be at most 100 characters, got {len(output.echo)}"


class TrivialEchoAgent(Agent[EchoInput, EchoOutput]):
    agent_id = "bank_alpha.echo"
    role = AgentRole.A1
    bank_id = BankId.BANK_ALPHA
    input_schema = EchoInput
    output_schema = EchoOutput
    system_prompt = "Return an EchoOutput JSON object."
    declared_intent = "p5_agent_base_test"
    bypass_rules = (
        BypassRule(
            name="force_echo",
            trigger=lambda input_data: "FORCE" in input_data.text,
            force_output=force_echo,
            reason="FORCE token requires deterministic echo.",
        ),
    )
    constraint_rules = (
        ConstraintRule(
            name="max_echo_length",
            check=output_is_short,
            violation_msg=output_too_long_message,
        ),
    )


def runtime(node_id: str = "bank-alpha-node") -> AgentRuntimeContext:
    return AgentRuntimeContext(
        run_id="run-p5-test",
        node_id=node_id,
        trust_domain=TrustDomain.BANK_SILO,
        llm=LLMClientConfig(
            base_url=f"http://{node_id}.local:8080/v1/chat/completions",
            default_model="stub-model",
            stub_mode=True,
            node_id=node_id,
        ),
        metadata={"scenario": "p5"},
    )


def agent_with_responses(*responses: object) -> tuple[TrivialEchoAgent, LLMClient, InMemoryAuditEmitter]:
    ctx = runtime()
    audit = InMemoryAuditEmitter()
    llm = LLMClient(ctx.llm, stub_responses=responses)
    return TrivialEchoAgent(runtime=ctx, llm=llm, audit=audit), llm, audit


def event_kinds(audit: InMemoryAuditEmitter) -> list[AuditEventKind]:
    return [event.kind for event in audit.events]


def test_normal_path_returns_valid_output_and_audit() -> None:
    agent, llm, audit = agent_with_responses({"echo": "hello"})

    output = agent.run(EchoInput(text="hello"))

    assert output == EchoOutput(echo="hello")
    assert llm.call_count == 1
    assert event_kinds(audit) == [AuditEventKind.MESSAGE_SENT]
    event = audit.events[0]
    assert event.run_id == "run-p5-test"
    assert event.node_id == "bank-alpha-node"
    assert event.role == AgentRole.A1
    assert event.phase == "return"
    assert event.status == "ok"


def test_bypass_triggers_without_llm_call_and_emits_audit() -> None:
    agent, llm, audit = agent_with_responses({"echo": "should-not-be-used"})

    output = agent.run(EchoInput(text="please FORCE this output"))

    assert output == EchoOutput(echo="please FORCE this output")
    assert llm.call_count == 0
    assert event_kinds(audit) == [
        AuditEventKind.BYPASS_TRIGGERED,
        AuditEventKind.MESSAGE_SENT,
    ]
    assert audit.events[0].phase == "bypass"
    assert audit.events[0].rule_name == "force_echo"
    assert audit.events[1].bypass_name == "force_echo"


def test_malformed_json_triggers_one_parse_repair_retry() -> None:
    agent, llm, audit = agent_with_responses("not-json", {"echo": "fixed"})

    output = agent.run(EchoInput(text="hello"))

    assert output == EchoOutput(echo="fixed")
    assert llm.call_count == 2
    assert [event.phase for event in audit.events] == ["llm_parse", "return"]
    assert audit.events[0].kind == AuditEventKind.CONSTRAINT_VIOLATION
    assert audit.events[0].status == "retry"


def test_second_malformed_json_raises_unparseable() -> None:
    agent, _llm, audit = agent_with_responses("not-json", "still-not-json")

    with pytest.raises(LLMOutputUnparseable):
        agent.run(EchoInput(text="hello"))

    assert [event.status for event in audit.events] == ["retry", "blocked"]


def test_constraint_violation_triggers_one_repair_retry() -> None:
    too_long = "x" * 101
    agent, llm, audit = agent_with_responses({"echo": too_long}, {"echo": "short"})

    output = agent.run(EchoInput(text="hello"))

    assert output == EchoOutput(echo="short")
    assert llm.call_count == 2
    assert [event.phase for event in audit.events] == ["constraint", "return"]
    assert audit.events[0].rule_name == "max_echo_length"
    assert audit.events[0].status == "retry"
    assert audit.events[0].retry_count == 1
    assert audit.events[1].retry_count == 1


def test_second_constraint_failure_raises_constraint_violation() -> None:
    too_long = "x" * 101
    agent, _llm, audit = agent_with_responses({"echo": too_long}, {"echo": too_long})

    with pytest.raises(ConstraintViolation):
        agent.run(EchoInput(text="hello"))

    assert [event.status for event in audit.events] == ["retry", "blocked"]
    assert audit.events[-1].rule_name == "max_echo_length"


def test_invalid_input_raises_and_emits_constraint_audit() -> None:
    agent, _llm, audit = agent_with_responses({"echo": "unused"})

    with pytest.raises(InvalidAgentInput):
        agent.run({"text": 123})

    assert event_kinds(audit) == [AuditEventKind.CONSTRAINT_VIOLATION]
    assert audit.events[0].phase == "input_validation"


def test_llm_stub_mode_environment_prevents_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_STUB_MODE", "1")
    ctx = runtime()
    live_config = ctx.llm.model_copy(update={"stub_mode": False})
    live_ctx = ctx.model_copy(update={"llm": live_config})
    audit = InMemoryAuditEmitter()
    llm = LLMClient(live_config, stub_responses=[{"echo": "from env stub"}])
    agent = TrivialEchoAgent(runtime=live_ctx, llm=llm, audit=audit)

    output = agent.run(EchoInput(text="hello"))

    assert output == EchoOutput(echo="from env stub")
    assert llm.call_count == 1
    assert len(llm.requests) == 1
