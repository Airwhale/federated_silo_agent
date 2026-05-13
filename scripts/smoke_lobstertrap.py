"""Smoke-test Lobster Trap policy behavior without calling Gemini."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.p0_cases import ALL_CASES


DEFAULT_POLICY = REPO_ROOT / "infra" / "lobstertrap" / "base_policy.yaml"
DEFAULT_LOCAL_BIN = REPO_ROOT / ".tools" / "lobstertrap" / "bin" / "lobstertrap.exe"

app = typer.Typer(add_completion=False)
console = Console()


def resolve_binary(explicit: str | None) -> Path:
    """Resolve the Lobster Trap binary path."""
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
        raise typer.BadParameter(f"Lobster Trap binary not found: {path}")

    if DEFAULT_LOCAL_BIN.exists():
        return DEFAULT_LOCAL_BIN

    found = shutil.which("lobstertrap")
    if found:
        return Path(found)

    raise typer.BadParameter(
        "Lobster Trap binary not found. Run scripts\\bootstrap_lobstertrap.ps1 "
        "or pass --lobstertrap-bin."
    )


def inspect_case(binary: Path, policy: Path, prompt: str) -> str:
    """Run lobstertrap inspect and return the policy action."""
    completed = subprocess.run(
        [str(binary), "inspect", "--policy", str(policy), prompt],
        check=False,
        capture_output=True,
        text=True,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0:
        raise RuntimeError(output)

    match = re.search(r"Action:\s+([A-Z_]+)", output)
    if not match:
        raise RuntimeError(f"Could not parse Lobster Trap action from output:\n{output}")
    return match.group(1)


@app.command()
def main(
    policy: Annotated[Path, typer.Option(help="Path to Lobster Trap policy YAML.")] = DEFAULT_POLICY,
    lobstertrap_bin: Annotated[
        str | None,
        typer.Option(help="Path to lobstertrap executable. Defaults to .tools or PATH."),
    ] = None,
) -> None:
    """Validate the P0 policy against benign and blocked prompt cases."""
    if not policy.exists():
        raise typer.BadParameter(f"Policy not found: {policy}")

    binary = resolve_binary(lobstertrap_bin)
    table = Table(title="Lobster Trap P0 Policy Smoke")
    table.add_column("case")
    table.add_column("expected")
    table.add_column("actual")
    table.add_column("status")

    failures: list[str] = []
    for case in ALL_CASES:
        action = inspect_case(binary, policy, case.prompt)
        ok = action in case.expected_verdicts
        if not ok:
            failures.append(
                f"{case.name}: expected one of {case.expected_verdicts}, got {action}"
            )
        table.add_row(
            case.name,
            ", ".join(case.expected_verdicts),
            action,
            "[green]PASS[/green]" if ok else "[red]FAIL[/red]",
        )

    console.print(table)
    if failures:
        for failure in failures:
            console.print(f"[red]{failure}[/red]")
        raise typer.Exit(1)

    console.print("[green]P0 Lobster Trap policy smoke passed.[/green]")


if __name__ == "__main__":
    app()
