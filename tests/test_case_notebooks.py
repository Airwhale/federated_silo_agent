from __future__ import annotations

import json

import pytest

from backend.agents.llm_client import LLMClient
from backend.demo.canonical_flow import run_canonical_flow_state
from backend.demo.seeds import CANONICAL_RUN_LABEL
from backend.notebooks.case_notebook import (
    NOTEBOOK_REPORTER_AGENT_ID,
    NOTEBOOK_REPORTER_NODE_ID,
    NotebookNarrativeMode,
    build_case_artifacts_from_state,
    generate_case_notebook,
)
from backend.notebooks.generate_case_notebook import _run_supported_scenario
from backend.runtime.context import LLMClientConfig


RAW_CUSTOMER_NAMES = (
    "Acme Holdings",
    "Beacon Logistics",
    "Citadel Trading",
    "Delta Imports",
    "Eagle Consulting",
)


def test_canonical_flow_builds_notebook_artifacts_without_raw_names() -> None:
    execution = run_canonical_flow_state(stub=True, out_dir=None)
    artifacts = build_case_artifacts_from_state(
        execution.state,
        duration_seconds=execution.duration_seconds,
    )
    combined = artifacts.model_dump_json()

    assert artifacts.scenario_id == CANONICAL_RUN_LABEL
    assert artifacts.graph_pattern_response is not None
    assert artifacts.sar_draft is not None
    assert artifacts.audit_review_result is not None
    assert len(artifacts.statistical_intermediaries) == 3
    assert len(artifacts.dp_provenance) >= 6
    assert {row.bank_id for row in artifacts.statistical_intermediaries} == {
        "bank_alpha",
        "bank_beta",
        "bank_gamma",
    }
    for raw_name in RAW_CUSTOMER_NAMES:
        assert raw_name not in combined


def test_generate_case_notebook_writes_reproducible_ipynb(tmp_path) -> None:
    execution = run_canonical_flow_state(stub=True, out_dir=None)
    artifacts = build_case_artifacts_from_state(
        execution.state,
        duration_seconds=execution.duration_seconds,
    )

    result = generate_case_notebook(
        artifacts,
        out_dir=tmp_path,
        narrative_mode=NotebookNarrativeMode.TEMPLATE,
    )

    notebook = json.loads(result.notebook_path.read_text(encoding="utf-8"))
    artifact_json = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    notebook_html = result.notebook_html_path.read_text(encoding="utf-8")
    artifact_html = result.artifact_html_path.read_text(encoding="utf-8")
    source_text = "\n".join("".join(cell["source"]) for cell in notebook["cells"])

    assert result.cell_count >= 12
    assert notebook["nbformat"] == 4
    assert notebook["metadata"]["kernelspec"]["name"] == "python3"
    assert artifact_json["scenario_id"] == CANONICAL_RUN_LABEL
    assert "Statistical intermediaries" in source_text
    assert "Construct the pooled statistic" in source_text
    assert "DP provenance" in source_text
    assert "F5 audit review" in source_text
    assert "CASE_ARTIFACTS" in source_text
    assert "<!doctype html>" in notebook_html
    assert "Generated notebook HTML" in notebook_html
    assert "Federation-safe artifact bundle" in artifact_html
    assert "CASE_ARTIFACTS" in notebook_html
    assert "s1_structuring_ring" in artifact_html
    assert "Case visuals" in notebook_html
    assert "Pooled edge-count buckets" in notebook_html
    assert "DP rho by bank" in notebook_html
    assert '<details class="case-card code-cell"' in notebook_html

    for raw_name in RAW_CUSTOMER_NAMES:
        assert raw_name not in source_text
        assert raw_name not in notebook_html
        assert raw_name not in artifact_html


def test_notebook_pooled_statistic_matches_intermediary_sums(tmp_path) -> None:
    execution = run_canonical_flow_state(stub=True, out_dir=None)
    artifacts = build_case_artifacts_from_state(
        execution.state,
        duration_seconds=execution.duration_seconds,
    )
    result = generate_case_notebook(artifacts, out_dir=tmp_path)
    artifact_json = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    rows = artifact_json["statistical_intermediaries"]

    # Mirror the robust ``_sum_vectors`` semantics in the production
    # code: banks may emit different-width vectors and the test should
    # validate the pooling logic that actually ships, not a narrower
    # ``rows[0][key]``-width assumption that quietly succeeds on the
    # canonical fixture.
    edge_vectors = [row["edge_count_distribution"] for row in rows]
    edge_width = max(len(v) for v in edge_vectors) if edge_vectors else 0
    pooled_edges = [
        sum(v[i] for v in edge_vectors if i < len(v)) for i in range(edge_width)
    ]
    flow_vectors = [row["bucketed_flow_histogram"] for row in rows]
    flow_width = max(len(v) for v in flow_vectors) if flow_vectors else 0
    pooled_flows = [
        sum(v[i] for v in flow_vectors if i < len(v)) for i in range(flow_width)
    ]

    assert pooled_edges == [3, 5, 7, 15]
    assert pooled_flows == [0, 8, 129, 9, 0]
    assert sum(row["rho_debited"] for row in rows) == pytest.approx(0.12)


def test_llm_narrative_uses_federation_reporter_metadata(tmp_path) -> None:
    execution = run_canonical_flow_state(stub=True, out_dir=None)
    artifacts = build_case_artifacts_from_state(
        execution.state,
        duration_seconds=execution.duration_seconds,
    )
    llm = LLMClient(
        LLMClientConfig(
            default_model="stub-notebook-model",
            node_id=NOTEBOOK_REPORTER_NODE_ID,
            stub_mode=True,
        ),
        stub_responses=[
            {
                "executive_summary": "Federated evidence shows a repeatable pattern.",
                "statistical_method": "The report pools noised aggregate statistics.",
                "aml_analysis": "The pattern is consistent with structuring risk.",
                "audit_conclusion": "Audit records link each conclusion to provenance.",
                "limitations": "The notebook omits raw customer and account data.",
                "next_steps": ["Escalate the generated SAR draft for review."],
            }
        ],
    )

    generate_case_notebook(
        artifacts,
        out_dir=tmp_path,
        narrative_mode=NotebookNarrativeMode.LLM,
        llm=llm,
    )

    assert llm.requests[0].lobstertrap["agent_id"] == NOTEBOOK_REPORTER_AGENT_ID
    assert llm.requests[0].lobstertrap["node_id"] == NOTEBOOK_REPORTER_NODE_ID
    assert llm.requests[0].lobstertrap["trust_domain"] == "federation"


def test_llm_narrative_rejects_non_federation_client(tmp_path) -> None:
    execution = run_canonical_flow_state(stub=True, out_dir=None)
    artifacts = build_case_artifacts_from_state(
        execution.state,
        duration_seconds=execution.duration_seconds,
    )
    bank_scoped_llm = LLMClient(
        LLMClientConfig(
            default_model="stub-notebook-model",
            node_id="bank-alpha-f4-node",
            stub_mode=True,
        ),
        stub_responses=[
            {
                "executive_summary": "Should not be used.",
                "statistical_method": "Should not be used.",
                "aml_analysis": "Should not be used.",
                "audit_conclusion": "Should not be used.",
                "limitations": "Should not be used.",
            }
        ],
    )

    with pytest.raises(ValueError, match="federation-scoped"):
        generate_case_notebook(
            artifacts,
            out_dir=tmp_path,
            narrative_mode=NotebookNarrativeMode.LLM,
            llm=bank_scoped_llm,
        )


def test_unknown_scenario_requires_artifact_bundle() -> None:
    with pytest.raises(ValueError, match="artifact-bundle"):
        _run_supported_scenario(scenario_id="s2_layering", stub=True)
