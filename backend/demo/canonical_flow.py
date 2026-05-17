"""Run the canonical S1 AML demo flow from a deterministic seed."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from pydantic import Field
from rich.console import Console
from rich.table import Table

from backend.demo.seeds import CANONICAL_SESSION_ID
from backend.orchestrator.agents import OrchestratorPrincipals
from backend.orchestrator.runtime import (
    Orchestrator,
    SessionOrchestratorState,
    TerminalCode,
)
from backend.ui.state import DemoControlService
from shared.enums import PatternClass, SARPriority, TypologyCode
from shared.messages import AuditReviewResult, GraphPatternResponse, SARDraft, StrictModel


DEFAULT_OUT_DIR = Path("out")
app = typer.Typer(add_completion=False, no_args_is_help=False)
console = Console()


@dataclass(frozen=True)
class CanonicalFlowExecution:
    """Internal canonical-run bundle for downstream artifact generators."""

    state: SessionOrchestratorState
    duration_seconds: float
    output_files: list[str]


class CanonicalFlowResult(StrictModel):
    """Structured result returned by the P16 canonical runner."""

    terminal_code: TerminalCode | None
    terminal_reason: str | None
    turn_count: int = Field(ge=0)
    duration_seconds: float = Field(ge=0.0)
    graph_pattern: GraphPatternResponse | None = None
    sar_draft: SARDraft | None = None
    audit_review: AuditReviewResult | None = None
    audit_event_count: int = Field(ge=0)
    policy_evaluation_count: int = Field(ge=0)
    policy_message_types: list[str] = Field(default_factory=list)
    output_files: list[str] = Field(default_factory=list)


def run_canonical_flow(
    *,
    stub: bool = True,
    session_id: UUID = CANONICAL_SESSION_ID,
    out_dir: Path | None = DEFAULT_OUT_DIR,
    max_turns: int = 50,
) -> CanonicalFlowResult:
    """Run the canonical orchestrator path until a terminal state."""
    execution = run_canonical_flow_state(
        stub=stub,
        session_id=session_id,
        out_dir=out_dir,
        max_turns=max_turns,
    )
    state = execution.state
    audit_event_count = (
        len(state.audit_review_request.audit_events)
        if state.audit_review_request is not None
        else 0
    )
    return CanonicalFlowResult(
        terminal_code=state.terminal_code,
        terminal_reason=state.terminal_reason,
        turn_count=state.turn_count,
        duration_seconds=round(execution.duration_seconds, 6),
        graph_pattern=state.graph_pattern_response,
        sar_draft=state.sar_draft,
        audit_review=state.audit_review_result,
        audit_event_count=audit_event_count,
        policy_evaluation_count=len(state.policy_evaluations),
        policy_message_types=[
            record.evaluated_message_type.value for record in state.policy_evaluations
        ],
        output_files=execution.output_files,
    )


def run_canonical_flow_state(
    *,
    stub: bool = True,
    session_id: UUID = CANONICAL_SESSION_ID,
    out_dir: Path | None = DEFAULT_OUT_DIR,
    max_turns: int = 50,
) -> CanonicalFlowExecution:
    """Run the canonical path and return the live state for safe reporting."""
    if not stub:
        _assert_live_readiness()

    start = time.perf_counter()
    principals = OrchestratorPrincipals.build()
    orchestrator = Orchestrator(principals=principals)
    state = orchestrator.bootstrap(
        session_id=session_id,
        mode="stub" if stub else "live",
    )

    while state.turn_count < max_turns:
        turn = orchestrator.next_turn(state)
        if turn is None:
            break
        orchestrator.run_turn(state, turn)
    else:
        raise RuntimeError(f"canonical flow exceeded max_turns={max_turns}")

    duration = time.perf_counter() - start
    output_files = _write_outputs(state, out_dir) if out_dir is not None else []
    return CanonicalFlowExecution(
        state=state,
        duration_seconds=round(duration, 6),
        output_files=output_files,
    )


@app.callback(invoke_without_command=True)
def main(
    stub: Annotated[
        bool,
        typer.Option(
            "--stub/--live",
            help="Use deterministic stubs by default; --live requires provider readiness.",
        ),
    ] = True,
    out_dir: Annotated[
        Path,
        typer.Option(help="Directory for sar_draft.json and audit.jsonl outputs."),
    ] = DEFAULT_OUT_DIR,
    max_turns: Annotated[
        int,
        typer.Option(help="Defensive maximum number of orchestrator turns."),
    ] = 50,
) -> None:
    """Run the canonical S1 structuring-ring demo."""
    try:
        result = run_canonical_flow(
            stub=stub,
            out_dir=out_dir,
            max_turns=max_turns,
        )
    except Exception as exc:
        console.print(f"[red]Canonical flow failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    _render_summary(result)
    if result.terminal_code != TerminalCode.SAR_DRAFT_READY:
        raise typer.Exit(2)


def _write_outputs(state, out_dir: Path) -> list[str]:  # noqa: ANN001
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if state.sar_draft is not None:
        sar_path = out_dir / "sar_draft.json"
        sar_path.write_text(state.sar_draft.model_dump_json(indent=2), encoding="utf-8")
        paths.append(sar_path)
    if state.audit_review_request is not None:
        audit_path = out_dir / "audit.jsonl"
        with audit_path.open("w", encoding="utf-8") as handle:
            for event in state.audit_review_request.audit_events:
                handle.write(json.dumps(event.model_dump(mode="json"), sort_keys=True))
                handle.write("\n")
        paths.append(audit_path)
    return [str(path) for path in paths]


def _render_summary(result: CanonicalFlowResult) -> None:
    table = Table(title="Canonical S1 Demo Flow")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("terminal", result.terminal_code.value if result.terminal_code else "none")
    table.add_row("reason", result.terminal_reason or "none")
    table.add_row("turns", str(result.turn_count))
    table.add_row("duration_seconds", f"{result.duration_seconds:.3f}")
    table.add_row(
        "F2 pattern",
        (
            result.graph_pattern.pattern_class.value
            if result.graph_pattern is not None
            else "none"
        ),
    )
    table.add_row(
        "F2 confidence",
        (
            f"{result.graph_pattern.confidence:.2f}"
            if result.graph_pattern is not None
            else "n/a"
        ),
    )
    table.add_row(
        "SAR typology",
        (
            result.sar_draft.typology_code.value
            if result.sar_draft is not None and result.sar_draft.typology_code
            else "none"
        ),
    )
    table.add_row(
        "SAR priority",
        (
            result.sar_draft.sar_priority.value
            if result.sar_draft is not None
            else "none"
        ),
    )
    table.add_row(
        "contributors",
        (
            str(len(result.sar_draft.contributors))
            if result.sar_draft is not None
            else "0"
        ),
    )
    table.add_row(
        "F5 findings",
        (
            str(len(result.audit_review.findings))
            if result.audit_review is not None
            else "n/a"
        ),
    )
    table.add_row("audit events", str(result.audit_event_count))
    table.add_row("policy evaluations", str(result.policy_evaluation_count))
    table.add_row("outputs", ", ".join(result.output_files) or "none")
    console.print(table)


def _assert_live_readiness() -> None:
    health = DemoControlService().provider_health()
    missing: list[str] = []
    if not health.lobster_trap_configured:
        missing.append("Lobster Trap config")
    if not health.litellm_configured:
        missing.append("LiteLLM config")
    if not (health.gemini_api_key_present or health.openrouter_api_key_present):
        missing.append("Gemini or OpenRouter API key")
    if missing:
        raise RuntimeError(
            "--live requires provider readiness before the first turn; missing "
            + ", ".join(missing)
        )


def _assert_result_types() -> None:
    """Keep imported enum types live for static checkers and schema drift."""
    _ = (PatternClass.STRUCTURING_RING, SARPriority.HIGH, TypologyCode.STRUCTURING)


if __name__ == "__main__":
    app()
