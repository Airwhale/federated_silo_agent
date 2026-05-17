from __future__ import annotations

import json

from backend.demo.canonical_flow import run_canonical_flow
from backend.orchestrator.runtime import TerminalCode
from shared.enums import AuditEventKind, PatternClass, SARPriority, TypologyCode


RAW_CUSTOMER_NAMES = (
    "Acme Holdings",
    "Beacon Logistics",
    "Citadel Trading",
    "Delta Imports",
    "Eagle Consulting",
)


def test_stub_canonical_flow_reaches_sar_draft_and_clean_audit(tmp_path) -> None:
    result = run_canonical_flow(stub=True, out_dir=tmp_path)

    assert result.terminal_code == TerminalCode.SAR_DRAFT_READY
    assert result.graph_pattern is not None
    assert result.graph_pattern.pattern_class == PatternClass.STRUCTURING_RING
    assert result.graph_pattern.confidence >= 0.85
    assert result.sar_draft is not None
    assert result.sar_draft.typology_code == TypologyCode.STRUCTURING
    assert result.sar_draft.sar_priority == SARPriority.HIGH
    assert result.sar_draft.mandatory_fields_complete is True
    assert len(result.sar_draft.contributors) >= 2
    assert result.audit_review is not None
    assert result.audit_review.human_review_required is False
    assert result.audit_review.findings == []
    assert "audit_review_result" in result.policy_message_types
    assert result.audit_event_count >= 10
    assert result.policy_evaluation_count >= 10
    assert (tmp_path / "sar_draft.json").exists()
    assert (tmp_path / "audit.jsonl").exists()


def test_stub_canonical_flow_outputs_policy_and_dp_audit_evidence(tmp_path) -> None:
    result = run_canonical_flow(stub=True, out_dir=tmp_path)
    audit_events = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    kinds = {event["kind"] for event in audit_events}
    rho_payloads = [
        event["payload"]
        for event in audit_events
        if event["kind"] == AuditEventKind.RHO_DEBITED.value
    ]

    assert result.audit_review is not None
    assert AuditEventKind.MESSAGE_SENT.value in kinds
    assert AuditEventKind.LT_VERDICT.value in kinds
    assert AuditEventKind.RHO_DEBITED.value in kinds
    assert rho_payloads
    assert all(payload["rho_remaining"] < 1.0 for payload in rho_payloads)
    assert all(
        event["payload"]["verdict"] == "allow"
        for event in audit_events
        if event["kind"] == AuditEventKind.LT_VERDICT.value
    )


def test_stub_canonical_flow_redacts_raw_customer_names(tmp_path) -> None:
    result = run_canonical_flow(stub=True, out_dir=tmp_path)
    combined = "\n".join(
        [
            result.model_dump_json(),
            (tmp_path / "sar_draft.json").read_text(encoding="utf-8"),
            (tmp_path / "audit.jsonl").read_text(encoding="utf-8"),
        ]
    )

    for raw_name in RAW_CUSTOMER_NAMES:
        assert raw_name not in combined


def test_stub_canonical_flow_has_stable_business_fields() -> None:
    runs = [run_canonical_flow(stub=True, out_dir=None) for _ in range(3)]
    business_tuples = [
        (
            run.terminal_code,
            run.graph_pattern.pattern_class if run.graph_pattern else None,
            run.sar_draft.typology_code if run.sar_draft else None,
            run.sar_draft.sar_priority if run.sar_draft else None,
            len(run.sar_draft.contributors) if run.sar_draft else 0,
            len(run.audit_review.findings) if run.audit_review else -1,
        )
        for run in runs
    ]

    assert len(set(business_tuples)) == 1
