"""OpenAI-compatible LLM client for the node-local proxy chain."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from backend.runtime.context import LLMClientConfig, TrustDomain
from shared.enums import AgentRole, BankId


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
StubResponse = str | Mapping[str, Any] | BaseModel


class LLMProviderError(RuntimeError):
    """Raised when the proxy or provider cannot return a usable response."""


class LLMClientModel(BaseModel):
    """Base model for OpenAI-compatible request/response boundaries."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)


class ChatMessage(LLMClientModel):
    """OpenAI-compatible chat message."""

    role: Literal["system", "user", "assistant"]
    content: str


class LobsterTrapMetadata(LLMClientModel):
    """Metadata carried in the request body's `_lobstertrap` field."""

    agent_id: NonEmptyStr
    role: AgentRole
    bank_id: BankId
    trust_domain: TrustDomain
    node_id: NonEmptyStr
    run_id: NonEmptyStr
    declared_intent: NonEmptyStr
    extra: dict[str, str] = Field(default_factory=dict)

    def as_proxy_payload(self) -> dict[str, Any]:
        """Return the flat metadata shape expected by Lobster Trap."""
        payload = self.model_dump(mode="json", exclude={"extra"})
        payload.update(self.extra)
        return payload


class ChatCompletionRequest(LLMClientModel):
    """OpenAI-compatible structured-output chat request."""

    model: NonEmptyStr
    messages: list[ChatMessage]
    temperature: float = 0.0
    max_tokens: int = Field(default=1024, gt=0)
    stream: bool = False
    response_format: dict[str, Any]
    lobstertrap: dict[str, Any] = Field(default_factory=dict, alias="_lobstertrap")


class ResponseMessage(BaseModel):
    """Subset of an OpenAI-compatible response message."""

    role: str | None = None
    content: str | None = None

    model_config = ConfigDict(extra="allow")


class ChatChoice(BaseModel):
    """Subset of an OpenAI-compatible response choice."""

    index: int | None = None
    message: ResponseMessage | None = None
    finish_reason: str | None = None

    model_config = ConfigDict(extra="allow")


class ChatCompletionResponse(BaseModel):
    """Subset of an OpenAI-compatible chat completion response."""

    choices: list[ChatChoice] = Field(default_factory=list)
    model: str | None = None

    model_config = ConfigDict(extra="allow")


class LLMResponse(LLMClientModel):
    """Parsed response returned to the agent base class."""

    content: str
    model: NonEmptyStr
    raw_response: dict[str, Any] = Field(default_factory=dict)


class LLMClient:
    """Thin client for structured-output calls through Lobster Trap and LiteLLM."""

    def __init__(
        self,
        config: LLMClientConfig,
        *,
        stub_responses: Sequence[StubResponse] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._stub_responses = list(stub_responses or [])
        self._stub_index = 0
        self._http_client = http_client
        self.call_count = 0
        self.request_urls: list[str] = []
        self.requests: list[ChatCompletionRequest] = []

    def set_stub_responses(self, responses: Sequence[StubResponse]) -> None:
        """Replace the stub-response queue and reset the cursor.

        Public test affordance so tests don't have to reach into the
        private `_stub_responses` list. Always resets the stub index to
        zero so the next call returns the first new response.
        """
        self._stub_responses = list(responses)
        self._stub_index = 0

    def chat_structured(
        self,
        *,
        system_prompt: str,
        input_model: BaseModel,
        output_schema: type[BaseModel],
        metadata: LobsterTrapMetadata,
        repair_instruction: str | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Call the local proxy chain and return assistant content."""
        request = self._build_request(
            system_prompt=system_prompt,
            input_model=input_model,
            output_schema=output_schema,
            metadata=metadata,
            repair_instruction=repair_instruction,
            model=model,
        )
        self.call_count += 1
        self.request_urls.append(self.config.base_url)
        self.requests.append(request)

        if self.config.effective_stub_mode():
            return self._next_stub_response(output_schema, request.model)

        return self._post_with_retries(request)

    def _build_request(
        self,
        *,
        system_prompt: str,
        input_model: BaseModel,
        output_schema: type[BaseModel],
        metadata: LobsterTrapMetadata,
        repair_instruction: str | None,
        model: str | None,
    ) -> ChatCompletionRequest:
        user_content = input_model.model_dump_json()
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]
        if repair_instruction:
            messages.append(ChatMessage(role="user", content=repair_instruction))

        return ChatCompletionRequest(
            model=model or self.config.default_model,
            messages=messages,
            response_format=self._response_format(output_schema),
            _lobstertrap=metadata.as_proxy_payload(),
        )

    def _response_format(self, output_schema: type[BaseModel]) -> dict[str, Any]:
        schema_name = output_schema.__name__
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": output_schema.model_json_schema(),
                "strict": True,
            },
        }

    def _next_stub_response(
        self,
        output_schema: type[BaseModel],
        model: str,
    ) -> LLMResponse:
        if self._stub_index < len(self._stub_responses):
            raw = self._stub_responses[self._stub_index]
            self._stub_index += 1
        else:
            raise LLMProviderError(
                "LLM stub mode requires a queued stub response for "
                f"{output_schema.__name__}"
            )

        if isinstance(raw, BaseModel):
            content = raw.model_dump_json()
        elif isinstance(raw, str):
            content = raw
        else:
            content = json.dumps(dict(raw))

        return LLMResponse(content=content, model=model, raw_response={"stub": True})

    def _post_with_retries(self, request: ChatCompletionRequest) -> LLMResponse:
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return self._post_once(request)
            except (httpx.HTTPError, LLMProviderError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                time.sleep(min(0.25 * (2**attempt), 2.0))

        raise LLMProviderError("LLM provider request failed") from last_error

    def _post_once(self, request: ChatCompletionRequest) -> LLMResponse:
        client = self._http_client or httpx.Client(timeout=self.config.timeout_seconds)
        close_client = self._http_client is None
        try:
            response = client.post(
                self.config.base_url,
                headers=self._headers(),
                json=request.model_dump(by_alias=True, exclude_none=True, mode="json"),
            )
            response.raise_for_status()
            try:
                response_payload = response.json()
            except ValueError as exc:
                raise LLMProviderError("LLM response was not valid JSON") from exc
            try:
                parsed = ChatCompletionResponse.model_validate(response_payload)
            except ValidationError as exc:
                raise LLMProviderError("LLM response had an unexpected shape") from exc
        finally:
            if close_client:
                client.close()

        if not parsed.choices or parsed.choices[0].message is None:
            raise LLMProviderError("LLM response had no choices")
        content = parsed.choices[0].message.content
        if not content:
            raise LLMProviderError("LLM response message had no content")
        return LLMResponse(
            content=content,
            model=parsed.model or request.model,
            raw_response=response_payload,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key_env:
            api_key = os.environ.get(self.config.api_key_env)
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
        return headers
