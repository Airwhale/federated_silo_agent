from __future__ import annotations

import json

import httpx
from pydantic import BaseModel, ConfigDict

from backend.agents import LLMClient, LobsterTrapMetadata
from backend.runtime import LLMClientConfig, TrustDomain
from shared.enums import AgentRole, BankId


class EchoInput(BaseModel):
    text: str

    model_config = ConfigDict(extra="forbid", strict=True)


class EchoOutput(BaseModel):
    echo: str

    model_config = ConfigDict(extra="forbid", strict=True)


def metadata(node_id: str) -> LobsterTrapMetadata:
    return LobsterTrapMetadata(
        agent_id=f"{node_id}.agent",
        role=AgentRole.A2,
        bank_id=BankId.BANK_ALPHA,
        trust_domain=TrustDomain.INVESTIGATOR,
        node_id=node_id,
        run_id="run-client-test",
        declared_intent="p5_llm_client_test",
        extra={"scenario": "client"},
    )


def test_chat_structured_posts_to_configured_base_url_and_metadata() -> None:
    seen_urls: list[str] = []
    seen_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        body = json.loads(request.content)
        seen_bodies.append(body)
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"echo": "ok"}',
                        }
                    }
                ],
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    config = LLMClientConfig(
        base_url="https://node-a.example/v1/chat/completions",
        default_model="test-model",
        max_retries=0,
        timeout_seconds=5.0,
        node_id="node-a",
    )
    client = LLMClient(config, http_client=http_client)

    response = client.chat_structured(
        system_prompt="Return JSON.",
        input_model=EchoInput(text="hello"),
        output_schema=EchoOutput,
        metadata=metadata("node-a"),
    )

    assert response.content == '{"echo": "ok"}'
    assert seen_urls == ["https://node-a.example/v1/chat/completions"]
    assert client.request_urls == ["https://node-a.example/v1/chat/completions"]
    assert seen_bodies[0]["model"] == "test-model"
    assert seen_bodies[0]["response_format"]["type"] == "json_schema"
    assert seen_bodies[0]["_lobstertrap"]["agent_id"] == "node-a.agent"
    assert seen_bodies[0]["_lobstertrap"]["role"] == "A2"
    assert seen_bodies[0]["_lobstertrap"]["bank_id"] == "bank_alpha"
    assert seen_bodies[0]["_lobstertrap"]["trust_domain"] == "investigator"
    assert seen_bodies[0]["_lobstertrap"]["node_id"] == "node-a"
    assert seen_bodies[0]["_lobstertrap"]["scenario"] == "client"


def test_two_clients_can_use_different_node_local_urls() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"echo": "ok"}',
                        }
                    }
                ],
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    node_a = LLMClient(
        LLMClientConfig(
            base_url="https://node-a.example/v1/chat/completions",
            default_model="test-model",
            max_retries=0,
            timeout_seconds=5.0,
            node_id="node-a",
        ),
        http_client=http_client,
    )
    node_b = LLMClient(
        LLMClientConfig(
            base_url="https://node-b.example/v1/chat/completions",
            default_model="test-model",
            max_retries=0,
            timeout_seconds=5.0,
            node_id="node-b",
        ),
        http_client=http_client,
    )

    for client, node_id in ((node_a, "node-a"), (node_b, "node-b")):
        client.chat_structured(
            system_prompt="Return JSON.",
            input_model=EchoInput(text="hello"),
            output_schema=EchoOutput,
            metadata=metadata(node_id),
        )

    assert seen_urls == [
        "https://node-a.example/v1/chat/completions",
        "https://node-b.example/v1/chat/completions",
    ]
