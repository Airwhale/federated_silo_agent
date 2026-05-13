"""OpenRouter smoke test through the existing P0 proxy chain."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.smoke_proxy import DEFAULT_URL, main as run_proxy_smoke

DEFAULT_OPENROUTER_MODEL = "openrouter-gemini-narrator"

app = typer.Typer(add_completion=False)


@app.command()
def main(
    url: Annotated[str, typer.Option(help="OpenAI-compatible Lobster Trap URL.")] = DEFAULT_URL,
    model: Annotated[str, typer.Option(help="OpenRouter-backed LiteLLM model alias.")] = (
        DEFAULT_OPENROUTER_MODEL
    ),
    timeout_seconds: Annotated[float, typer.Option(help="HTTP timeout in seconds.")] = 30.0,
    include_benign: Annotated[
        bool,
        typer.Option(help="Run benign OpenRouter pass-through check."),
    ] = True,
) -> None:
    """Exercise the P0 smoke cases with OpenRouter as the upstream provider."""
    run_proxy_smoke(
        url=url,
        model=model,
        timeout_seconds=timeout_seconds,
        include_benign=include_benign,
        key_env="OPENROUTER_API_KEY",
    )


if __name__ == "__main__":
    app()
