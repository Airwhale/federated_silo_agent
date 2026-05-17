"""CLI for generating federation-safe AML case-analysis notebooks."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from backend.agents.llm_client import LLMClient
from backend.demo.canonical_flow import run_canonical_flow_state
from backend.demo.seeds import CANONICAL_RUN_LABEL
from backend.notebooks.case_notebook import (
    CaseNotebookArtifacts,
    CaseNotebookGenerationResult,
    NOTEBOOK_REPORTER_NODE_ID,
    NotebookNarrativeMode,
    build_case_artifacts_from_state,
    generate_case_notebook,
)
from backend.runtime.context import LLMClientConfig

# Default route used when the CLI is invoked with ``--llm-narrative``. Kept
# visible at the CLI boundary (rather than buried in ``_build_narrative``)
# so the model + node id are obviously configurable / overridable by the
# next caller who needs a non-default route. ``_build_narrative`` itself
# now requires the caller to pass a client -- there is no silent fallback.
DEFAULT_NARRATIVE_MODEL = "gemini-notebook-narrator"
DEFAULT_NARRATIVE_NODE_ID = NOTEBOOK_REPORTER_NODE_ID


DEFAULT_NOTEBOOK_DIR = Path("out") / "notebooks"
app = typer.Typer(add_completion=False, no_args_is_help=False)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    scenario_id: Annotated[
        str,
        typer.Option(
            "--scenario-id",
            help=(
                "Scenario to generate from built runners. Current built runner "
                "supports s1_structuring_ring."
            ),
        ),
    ] = CANONICAL_RUN_LABEL,
    artifact_bundle: Annotated[
        Path | None,
        typer.Option(
            "--artifact-bundle",
            help="Existing CaseNotebookArtifacts JSON bundle to render.",
        ),
    ] = None,
    out_dir: Annotated[
        Path,
        typer.Option("--out-dir", help="Directory for .ipynb and artifact JSON."),
    ] = DEFAULT_NOTEBOOK_DIR,
    stub: Annotated[
        bool,
        typer.Option(
            "--stub/--live",
            help="Run the canonical flow in deterministic stub mode by default.",
        ),
    ] = True,
    llm_narrative: Annotated[
        bool,
        typer.Option(
            "--llm-narrative/--template-narrative",
            help="Ask the local model route for notebook prose instead of templates.",
        ),
    ] = False,
) -> None:
    """Generate a Jupyter notebook from federation-safe case artifacts."""
    try:
        artifacts = (
            _load_artifact_bundle(artifact_bundle)
            if artifact_bundle is not None
            else _run_supported_scenario(scenario_id=scenario_id, stub=stub)
        )
        narrative_mode = (
            NotebookNarrativeMode.LLM
            if llm_narrative
            else NotebookNarrativeMode.TEMPLATE
        )
        narrative_llm = (
            LLMClient(
                LLMClientConfig(
                    default_model=DEFAULT_NARRATIVE_MODEL,
                    node_id=DEFAULT_NARRATIVE_NODE_ID,
                )
            )
            if narrative_mode == NotebookNarrativeMode.LLM
            else None
        )
        result = generate_case_notebook(
            artifacts,
            out_dir=out_dir,
            narrative_mode=narrative_mode,
            llm=narrative_llm,
        )
    except Exception as exc:
        console.print(f"[red]Notebook generation failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    _render_summary(result)


def _run_supported_scenario(
    *,
    scenario_id: str,
    stub: bool,
) -> CaseNotebookArtifacts:
    if scenario_id != CANONICAL_RUN_LABEL:
        raise ValueError(
            "Only s1_structuring_ring has a built canonical runner today. "
            "For other scenarios, pass --artifact-bundle with a saved "
            "CaseNotebookArtifacts JSON bundle."
        )
    execution = run_canonical_flow_state(stub=stub, out_dir=None)
    return build_case_artifacts_from_state(
        execution.state,
        duration_seconds=execution.duration_seconds,
        scenario_id=scenario_id,
    )


def _load_artifact_bundle(path: Path) -> CaseNotebookArtifacts:
    return CaseNotebookArtifacts.model_validate_json(path.read_text(encoding="utf-8"))


def _render_summary(result: CaseNotebookGenerationResult) -> None:
    table = Table(title="Generated AML Case Notebook")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("scenario", result.scenario_id)
    table.add_row("run_id", result.run_id)
    table.add_row("notebook", str(result.notebook_path))
    table.add_row("artifacts", str(result.artifact_path))
    table.add_row("notebook_html", str(result.notebook_html_path))
    table.add_row("artifact_html", str(result.artifact_html_path))
    table.add_row("cells", str(result.cell_count))
    console.print(table)


if __name__ == "__main__":
    app()
