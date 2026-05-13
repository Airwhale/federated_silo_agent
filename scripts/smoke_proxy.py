"""End-to-end smoke test for Lobster Trap -> LiteLLM -> Gemini."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.table import Table

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.p0_cases import BENIGN_CASE, BLOCKED_CASES, PromptCase  # noqa: E402


DEFAULT_URL = "http://127.0.0.1:8080/v1/chat/completions"
DEFAULT_MODEL = "gemini-narrator"

app = typer.Typer(add_completion=False)
console = Console()


class ChatMessage(BaseModel):
    """OpenAI-compatible chat message boundary object."""

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat-completion request boundary object."""

    model: str
    messages: list[ChatMessage]
    temperature: float = 0
    max_tokens: int = 64
    stream: bool = False
    lobstertrap: dict[str, Any] = Field(default_factory=dict, alias="_lobstertrap")

    model_config = ConfigDict(populate_by_name=True)


class ChatChoice(BaseModel):
    """OpenAI-compatible chat-completion choice boundary object."""

    index: int | None = None
    message: ChatMessage | None = None
    finish_reason: str | None = None

    model_config = ConfigDict(extra="allow")


class LobsterTrapReport(BaseModel):
    """Subset of Lobster Trap response metadata needed by the smoke test."""

    request_id: str | None = None
    verdict: str
    ingress: dict[str, Any] | None = None
    egress: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat response with Lobster Trap metadata."""

    choices: list[ChatChoice] = Field(default_factory=list)
    lobstertrap: LobsterTrapReport = Field(alias="_lobstertrap")

    model_config = ConfigDict(extra="allow", populate_by_name=True)


def build_request(case: PromptCase, model: str) -> ChatCompletionRequest:
    """Build a smoke-test chat request."""
    return ChatCompletionRequest(
        model=model,
        messages=[
            ChatMessage(
                role="system",
                content=(
                    "You are a concise P0 smoke-test assistant. Reply briefly. "
                    "Do not mention private customer data."
                ),
            ),
            ChatMessage(role="user", content=case.prompt),
        ],
        _lobstertrap={
            "agent_id": "p0-smoke",
            "declared_intent": "aml_federation_smoke_test",
        },
    )


def infer_required_key_env(model: str) -> str:
    """Infer the provider key environment variable from the LiteLLM model alias."""
    normalized = model.lower()
    if normalized.startswith("openrouter") or "/openrouter/" in normalized:
        return "OPENROUTER_API_KEY"
    return "GEMINI_API_KEY"


def post_case(client: httpx.Client, url: str, case: PromptCase, model: str) -> ChatCompletionResponse:
    """Post one case through the proxy chain and parse the response."""
    request = build_request(case, model)
    response = client.post(url, json=request.model_dump(by_alias=True, exclude_none=True))
    response.raise_for_status()
    return ChatCompletionResponse.model_validate(response.json())


def response_text(response: ChatCompletionResponse) -> str:
    """Extract assistant text from a response."""
    if not response.choices or response.choices[0].message is None:
        return ""
    return response.choices[0].message.content


@app.command()
def main(
    url: Annotated[str, typer.Option(help="OpenAI-compatible Lobster Trap URL.")] = DEFAULT_URL,
    model: Annotated[str, typer.Option(help="LiteLLM model alias to call.")] = DEFAULT_MODEL,
    timeout_seconds: Annotated[float, typer.Option(help="HTTP timeout in seconds.")] = 30.0,
    include_benign: Annotated[bool, typer.Option(help="Run benign Gemini pass-through check.")] = True,
    key_env: Annotated[
        str | None,
        typer.Option(help="Provider API-key environment variable. Inferred from model when omitted."),
    ] = None,
) -> None:
    """Exercise benign and blocked prompts through the live P0 proxy chain."""
    load_dotenv(REPO_ROOT / ".env")

    required_key_env = key_env or infer_required_key_env(model)
    if include_benign and not os.environ.get(required_key_env):
        console.print(
            f"[yellow]{required_key_env} is not set. Benign pass-through may fail.[/yellow]"
        )

    cases = ([BENIGN_CASE] if include_benign else []) + list(BLOCKED_CASES)
    failures: list[str] = []
    table = Table(title=f"P0 Proxy-Chain Smoke ({model})")
    table.add_column("case")
    table.add_column("expected")
    table.add_column("verdict")
    table.add_column("rule")
    table.add_column("status")

    with httpx.Client(timeout=timeout_seconds) as client:
        for case in cases:
            try:
                parsed = post_case(client, url, case, model)
                verdict = parsed.lobstertrap.verdict
                rule = ""
                if parsed.lobstertrap.ingress:
                    rule = str(parsed.lobstertrap.ingress.get("rule_name") or "")
                ok = verdict in case.expected_verdicts
                if case is BENIGN_CASE:
                    ok = ok and bool(response_text(parsed).strip())
                else:
                    ok = ok and "[LOBSTER TRAP]" in response_text(parsed)
            except Exception as exc:  # noqa: BLE001 - CLI reports all smoke failures uniformly.
                verdict = "ERROR"
                rule = type(exc).__name__
                ok = False
                failures.append(f"{case.name}: {exc}")
            else:
                if not ok:
                    failures.append(
                        f"{case.name}: expected {case.expected_verdicts}, got {verdict}"
                    )

            table.add_row(
                case.name,
                ", ".join(case.expected_verdicts),
                verdict,
                rule,
                "[green]PASS[/green]" if ok else "[red]FAIL[/red]",
            )

    console.print(table)
    if failures:
        for failure in failures:
            console.print(f"[red]{failure}[/red]")
        raise typer.Exit(1)

    console.print("[green]P0 proxy-chain smoke passed.[/green]")


if __name__ == "__main__":
    app()
