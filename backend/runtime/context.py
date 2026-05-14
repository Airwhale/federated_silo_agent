"""Runtime configuration boundary objects for agent nodes."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Annotated, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TrustDomain(StrEnum):
    """Trust domains used to bind an agent to its local runtime stack."""

    INVESTIGATOR = "investigator"
    FEDERATION = "federation"
    BANK_SILO = "bank_silo"


class RuntimeModel(BaseModel):
    """Strict base class for runtime config models."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )


class LLMClientConfig(RuntimeModel):
    """Configuration for a node-local Lobster Trap / LiteLLM endpoint."""

    base_url: NonEmptyStr = "http://127.0.0.1:8080/v1/chat/completions"
    api_key_env: NonEmptyStr | None = None
    default_model: NonEmptyStr = "gemini-narrator"
    timeout_seconds: float = Field(default=30.0, gt=0.0)
    max_retries: int = Field(default=2, ge=0)
    stub_mode: bool = False
    node_id: NonEmptyStr = "local-dev"

    @field_validator("base_url")
    @classmethod
    def base_url_must_be_http(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value

    def effective_stub_mode(self) -> bool:
        """Return whether this client should avoid network calls."""
        env_value = os.environ.get("LLM_STUB_MODE", "").strip().lower()
        return self.stub_mode or env_value in {"1", "true", "yes", "on"}


class AgentRuntimeContext(RuntimeModel):
    """Runtime identity and local LLM configuration passed to an agent."""

    run_id: NonEmptyStr = Field(default_factory=lambda: str(uuid4()))
    node_id: NonEmptyStr = "local-dev"
    trust_domain: TrustDomain
    llm: LLMClientConfig = Field(default_factory=LLMClientConfig)
    audit: Any | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
