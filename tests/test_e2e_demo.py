from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

from backend.demo.canonical_flow import run_canonical_flow
from backend.demo.seeds import S1_ENTITY_HASHES
from backend.orchestrator.runtime import TerminalCode
from backend.runtime.network import tcp_url_reachable
from shared.enums import AuditEventKind, BankId, SARPriority, TypologyCode


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_CUSTOMER_NAMES = (
    "Acme Holdings",
    "Beacon Logistics",
    "Citadel Trading",
    "Delta Imports",
    "Eagle Consulting",
)
MAX_LIVE_RUNTIME_SECONDS = 180.0
DEFAULT_LITELLM_URL = "http://127.0.0.1:4000"
DEFAULT_LOBSTER_TRAP_URL = "http://127.0.0.1:8080"


load_dotenv(REPO_ROOT / ".env")


@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="requires live Gemini key",
)
def test_live_canonical_flow_reaches_sar_draft_with_policy_and_dp_evidence(
    tmp_path: Path,
) -> None:
    _skip_if_live_proxy_chain_unavailable()

    start = time.perf_counter()
    result = run_canonical_flow(stub=False, out_dir=tmp_path)
    duration_seconds = time.perf_counter() - start

    if duration_seconds >= MAX_LIVE_RUNTIME_SECONDS:
        pytest.fail(
            "live canonical flow exceeded "
            f"{MAX_LIVE_RUNTIME_SECONDS:.0f}s: {duration_seconds:.3f}s"
        )

    assert result.terminal_code == TerminalCode.SAR_DRAFT_READY
    assert result.sar_draft is not None
    assert result.sar_draft.typology_code == TypologyCode.STRUCTURING
    assert result.sar_draft.sar_priority == SARPriority.HIGH
    assert {contributor.bank_id for contributor in result.sar_draft.contributors} >= {
        BankId.BANK_ALPHA,
        BankId.BANK_BETA,
        BankId.BANK_GAMMA,
    }
    assert result.graph_pattern is not None
    assert set(result.graph_pattern.suspect_entity_hashes) & set(S1_ENTITY_HASHES)

    audit_events = _read_audit_events(tmp_path / "audit.jsonl")
    assert len(audit_events) >= 10
    assert any(
        event["kind"] == AuditEventKind.RHO_DEBITED.value
        and event["payload"]["rho_debited"] > 0.0
        for event in audit_events
    )
    assert any(
        event["kind"] == AuditEventKind.LT_VERDICT.value
        and event["payload"]["verdict"] == "allow"
        for event in audit_events
    )
    assert not any(
        event["kind"] == AuditEventKind.CONSTRAINT_VIOLATION.value
        for event in audit_events
    )

    outputs_to_check = [
        result.model_dump_json(),
        (tmp_path / "sar_draft.json").read_text(encoding="utf-8"),
        (tmp_path / "audit.jsonl").read_text(encoding="utf-8"),
    ]
    for output_text in outputs_to_check:
        for raw_name in RAW_CUSTOMER_NAMES:
            assert raw_name not in output_text


def _read_audit_events(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _skip_if_live_proxy_chain_unavailable() -> None:
    endpoints = {
        "Lobster Trap": os.getenv(
            "FEDERATED_SILO_LOBSTER_TRAP_URL",
            DEFAULT_LOBSTER_TRAP_URL,
        ),
        "LiteLLM": os.getenv("FEDERATED_SILO_LITELLM_URL", DEFAULT_LITELLM_URL),
    }
    unavailable = [
        f"{name} at {url}"
        for name, url in endpoints.items()
        if not tcp_url_reachable(url, timeout=1.0)
    ]
    if unavailable:
        pytest.skip("live proxy chain is not running: " + ", ".join(unavailable))
