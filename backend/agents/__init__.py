"""Agent runtime exports."""

from typing import TYPE_CHECKING

from backend.agents.base import (
    Agent,
    AgentAuditEvent,
    AgentRuntimeError,
    AuditEmitter,
    ConstraintViolation,
    InMemoryAuditEmitter,
    InvalidAgentInput,
    LLMOutputUnparseable,
    RuntimeAuditEvent,
)
from backend.agents.llm_client import (
    ChatCompletionRequest,
    ChatMessage,
    LLMClient,
    LLMProviderError,
    LLMResponse,
    LobsterTrapMetadata,
)
from backend.agents.rules import BypassRule, ConstraintRule

if TYPE_CHECKING:
    from backend.agents.a2_investigator import A2InvestigatorAgent
    from backend.agents.a3_silo_responder import A3SiloResponderAgent
    from backend.agents.f1_coordinator import F1CoordinatorAgent
    from backend.agents.f3_sanctions import F3SanctionsAgent

_LAZY_EXPORTS = {
    "A2InvestigatorAgent": ("backend.agents.a2_investigator", "A2InvestigatorAgent"),
    "A3SiloResponderAgent": ("backend.agents.a3_silo_responder", "A3SiloResponderAgent"),
    "F1CoordinatorAgent": ("backend.agents.f1_coordinator", "F1CoordinatorAgent"),
    "F3SanctionsAgent": ("backend.agents.f3_sanctions", "F3SanctionsAgent"),
}

__all__ = [
    "Agent",
    "AgentAuditEvent",
    "AgentRuntimeError",
    "A2InvestigatorAgent",
    "A3SiloResponderAgent",
    "AuditEmitter",
    "BypassRule",
    "ChatCompletionRequest",
    "ChatMessage",
    "ConstraintRule",
    "ConstraintViolation",
    "F1CoordinatorAgent",
    "F3SanctionsAgent",
    "InMemoryAuditEmitter",
    "InvalidAgentInput",
    "LLMClient",
    "LLMOutputUnparseable",
    "LLMProviderError",
    "LLMResponse",
    "LobsterTrapMetadata",
    "RuntimeAuditEvent",
]


def __getattr__(name: str) -> object:
    """Lazy-load concrete agents so data-layer imports do not cycle through A3."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import importlib

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
