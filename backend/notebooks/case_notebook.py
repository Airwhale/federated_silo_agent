"""Build federation-safe AML case-analysis notebooks on demand."""

from __future__ import annotations

import json
from html import escape
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, NonNegativeFloat, NonNegativeInt, StringConstraints

from backend import BACKEND_ROOT
from backend.agents.llm_client import LLMClient, LobsterTrapMetadata
from backend.demo.seeds import CANONICAL_RUN_LABEL
from backend.orchestrator.runtime import SessionOrchestratorState
from backend.runtime.context import LLMClientConfig, TrustDomain
from shared.enums import AgentRole, BankId, PolicyDecision
from shared.messages import (
    AuditEvent,
    AuditReviewRequest,
    AuditReviewResult,
    GraphPatternRequest,
    GraphPatternResponse,
    PolicyEvaluationResult,
    SARAssemblyRequest,
    SARDraft,
    SanctionsCheckResponse,
    StrictModel,
)


NotebookText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NotebookParagraph = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1600),
]
NOTEBOOK_PROMPT_PATH = BACKEND_ROOT / "notebooks" / "prompts" / "case_notebook_narrative.md"


class NotebookNarrativeMode(StrEnum):
    """How explanatory notebook prose is generated."""

    TEMPLATE = "template"
    LLM = "llm"


class StatisticalIntermediaryRow(StrictModel):
    """One bank-safe aggregate row produced for F2."""

    bank_id: BankId
    edge_count_distribution: list[NonNegativeInt]
    bucketed_flow_histogram: list[NonNegativeInt]
    candidate_entity_hashes: list[NotebookText] = Field(default_factory=list)
    candidate_entity_count: NonNegativeInt
    rho_debited: NonNegativeFloat


class DpProvenanceRow(StrictModel):
    """One privacy/provenance record attached to a released statistic."""

    bank_id: BankId
    field_name: NotebookText
    primitive_name: NotebookText
    returned_value_kind: NotebookText
    rho_debited: NonNegativeFloat
    per_bucket_rho: NonNegativeFloat | None = None
    sensitivity: NonNegativeFloat
    sigma_applied: NonNegativeFloat | None = None
    eps_delta_display: tuple[NonNegativeFloat, NonNegativeFloat] | None = None
    args_hash: NotebookText
    timestamp: datetime


class PolicyEvidenceRow(StrictModel):
    """One F6/Lobster Trap policy verdict used by F5."""

    turn_id: NotebookText
    message_id: UUID
    evaluated_message_type: NotebookText
    evaluated_sender_agent_id: NotebookText
    evaluated_recipient_agent_id: NotebookText
    decision: PolicyDecision
    rule_hit_count: NonNegativeInt


class NotebookNarrativeInput(StrictModel):
    """Bounded facts sent to an optional LLM narrative writer."""

    scenario_id: NotebookText
    run_id: NotebookText
    terminal_code: NotebookText | None
    terminal_reason: NotebookText | None
    pattern_class: NotebookText | None
    pattern_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    sar_priority: NotebookText | None
    sar_typology: NotebookText | None
    audit_finding_count: NonNegativeInt
    policy_decision_counts: dict[NotebookText, NonNegativeInt]
    statistical_intermediaries: list[StatisticalIntermediaryRow]
    dp_provenance: list[DpProvenanceRow]
    caveats: list[NotebookText]


class NotebookNarrative(StrictModel):
    """Notebook prose sections generated from supplied facts only."""

    executive_summary: NotebookParagraph
    statistical_method: NotebookParagraph
    aml_analysis: NotebookParagraph
    audit_conclusion: NotebookParagraph
    limitations: NotebookParagraph
    next_steps: list[NotebookParagraph] = Field(default_factory=list, max_length=5)


class CaseNotebookArtifacts(StrictModel):
    """Sanitized case bundle that can be embedded in a notebook."""

    scenario_id: NotebookText = CANONICAL_RUN_LABEL
    run_id: NotebookText
    generated_at: datetime
    terminal_code: NotebookText | None = None
    terminal_reason: NotebookText | None = None
    duration_seconds: NonNegativeFloat
    turn_count: NonNegativeInt
    graph_pattern_request: GraphPatternRequest | None = None
    graph_pattern_response: GraphPatternResponse | None = None
    sanctions_response: SanctionsCheckResponse | None = None
    sar_assembly_request: SARAssemblyRequest | None = None
    sar_draft: SARDraft | None = None
    audit_review_request: AuditReviewRequest | None = None
    audit_review_result: AuditReviewResult | None = None
    statistical_intermediaries: list[StatisticalIntermediaryRow] = Field(
        default_factory=list,
    )
    dp_provenance: list[DpProvenanceRow] = Field(default_factory=list)
    policy_evidence: list[PolicyEvidenceRow] = Field(default_factory=list)
    audit_events: list[AuditEvent] = Field(default_factory=list)


class CaseNotebookGenerationResult(StrictModel):
    """Paths and summary for a generated case notebook."""

    scenario_id: NotebookText
    run_id: NotebookText
    notebook_path: Path
    artifact_path: Path
    notebook_html_path: Path
    artifact_html_path: Path
    cell_count: NonNegativeInt


class CaseNotebookHtml(StrictModel):
    """Self-contained HTML renderings of generated case artifacts."""

    notebook_html: NotebookText
    artifact_html: NotebookText


class NotebookMarkdownCell(StrictModel):
    cell_type: Literal["markdown"] = "markdown"
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: list[str]


class NotebookCodeCell(StrictModel):
    cell_type: Literal["code"] = "code"
    execution_count: None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    outputs: list[Any] = Field(default_factory=list)
    source: list[str]


NotebookCell = NotebookMarkdownCell | NotebookCodeCell


class JupyterNotebook(StrictModel):
    """Minimal nbformat v4 notebook model."""

    cells: list[NotebookCell]
    metadata: dict[str, Any]
    nbformat: Literal[4] = 4
    nbformat_minor: int = 5


def build_case_artifacts_from_state(
    state: SessionOrchestratorState,
    *,
    duration_seconds: float,
    scenario_id: str = CANONICAL_RUN_LABEL,
) -> CaseNotebookArtifacts:
    """Build a notebook-safe artifact bundle from orchestrator state."""
    audit_events = (
        list(state.audit_review_request.audit_events)
        if state.audit_review_request is not None
        else []
    )
    return CaseNotebookArtifacts(
        scenario_id=scenario_id,
        run_id=state.run_id,
        generated_at=datetime.now(UTC),
        terminal_code=state.terminal_code.value if state.terminal_code else None,
        terminal_reason=state.terminal_reason,
        duration_seconds=duration_seconds,
        turn_count=state.turn_count,
        graph_pattern_request=state.graph_pattern_request,
        graph_pattern_response=state.graph_pattern_response,
        sanctions_response=state.sanctions_response,
        sar_assembly_request=state.sar_assembly_request,
        sar_draft=state.sar_draft,
        audit_review_request=state.audit_review_request,
        audit_review_result=state.audit_review_result,
        statistical_intermediaries=_statistical_intermediaries(state),
        dp_provenance=_dp_provenance(state),
        policy_evidence=_policy_evidence(state),
        audit_events=audit_events,
    )


def generate_case_notebook(
    artifacts: CaseNotebookArtifacts,
    *,
    out_dir: Path,
    narrative_mode: NotebookNarrativeMode = NotebookNarrativeMode.TEMPLATE,
    llm: LLMClient | None = None,
) -> CaseNotebookGenerationResult:
    """Write a case artifact JSON file and an analysis notebook."""
    out_dir.mkdir(parents=True, exist_ok=True)
    narrative = _build_narrative(artifacts, mode=narrative_mode, llm=llm)
    notebook = _build_notebook(artifacts, narrative)
    rendered_html = render_case_notebook_html(artifacts, notebook)
    slug = _case_slug(artifacts.scenario_id)
    artifact_path = out_dir / f"{slug}_artifacts.json"
    notebook_path = out_dir / f"{slug}_analysis.ipynb"
    artifact_html_path = out_dir / f"{slug}_artifacts.html"
    notebook_html_path = out_dir / f"{slug}_analysis.html"
    artifact_path.write_text(
        artifacts.model_dump_json(indent=2),
        encoding="utf-8",
    )
    notebook_path.write_text(
        json.dumps(notebook.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    artifact_html_path.write_text(rendered_html.artifact_html, encoding="utf-8")
    notebook_html_path.write_text(rendered_html.notebook_html, encoding="utf-8")
    return CaseNotebookGenerationResult(
        scenario_id=artifacts.scenario_id,
        run_id=artifacts.run_id,
        notebook_path=notebook_path,
        artifact_path=artifact_path,
        notebook_html_path=notebook_html_path,
        artifact_html_path=artifact_html_path,
        cell_count=len(notebook.cells),
    )


def render_case_notebook_html(
    artifacts: CaseNotebookArtifacts,
    notebook: JupyterNotebook,
) -> CaseNotebookHtml:
    """Render generated notebook content as safe static HTML."""
    notebook_sections: list[str] = []
    notebook_sections.append(_summary_graphics_html(artifacts))
    for index, cell in enumerate(notebook.cells, start=1):
        if isinstance(cell, NotebookMarkdownCell):
            notebook_sections.append(_markdown_cell_html("".join(cell.source), index=index))
        else:
            notebook_sections.append(_code_cell_html("".join(cell.source), index=index))
    artifact_json = json.dumps(
        artifacts.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
    )
    notebook_html = _html_document(
        title=f"AML case notebook: {artifacts.scenario_id}",
        eyebrow="Generated notebook HTML",
        body="\n".join(notebook_sections),
    )
    artifact_html = _html_document(
        title=f"Sanitized artifacts: {artifacts.scenario_id}",
        eyebrow="Federation-safe artifact bundle",
        body=(
            "<section class=\"case-card\">"
            "<h2>What this file contains</h2>"
            "<p>This is the exact sanitized JSON bundle embedded in the notebook. "
            "It contains signed message outputs, hash-only evidence, DP provenance, "
            "policy verdicts, SAR fields, and audit findings. It does not contain "
            "raw customer names, raw account identifiers, or raw transaction rows.</p>"
            "</section>"
            f"{_summary_graphics_html(artifacts)}"
            f"<pre class=\"json-block\"><code>{escape(artifact_json)}</code></pre>"
        ),
    )
    return CaseNotebookHtml(
        notebook_html=notebook_html,
        artifact_html=artifact_html,
    )


def _build_narrative(
    artifacts: CaseNotebookArtifacts,
    *,
    mode: NotebookNarrativeMode,
    llm: LLMClient | None,
) -> NotebookNarrative:
    narrative_input = _narrative_input(artifacts)
    if mode == NotebookNarrativeMode.TEMPLATE:
        return _template_narrative(narrative_input)
    if llm is None:
        # Don't fall back to a hardcoded model + node_id silently: an
        # LLM-mode notebook needs a caller-provided client so the model,
        # the LT metadata, and the LiteLLM route are governed by the
        # same configuration as every other LLM call in the run. The
        # alternative (instantiate a default here) hid an implicit
        # dependency that broke whenever a caller forgot to wire the
        # client through and the default model name didn't exist in the
        # configured provider.
        raise ValueError(
            "An LLMClient must be provided when narrative_mode=LLM. "
            "Pass the same governed client used by F4 (or a federation-"
            "scoped notebook-narrator client) so the prompt flows "
            "through LT/LiteLLM under audited metadata."
        )
    response = llm.chat_structured(
        system_prompt=NOTEBOOK_PROMPT_PATH.read_text(encoding="utf-8"),
        input_model=narrative_input,
        output_schema=NotebookNarrative,
        metadata=LobsterTrapMetadata(
            agent_id="federation.notebook_reporter",
            role=AgentRole.ORCHESTRATOR,
            bank_id=BankId.FEDERATION,
            trust_domain=TrustDomain.FEDERATION,
            node_id="federation-notebook-node",
            run_id=artifacts.run_id,
            declared_intent="generate_federation_safe_case_notebook",
            extra={"scenario_id": artifacts.scenario_id},
        ),
    )
    return NotebookNarrative.model_validate_json(response.content)


def _build_notebook(
    artifacts: CaseNotebookArtifacts,
    narrative: NotebookNarrative,
) -> JupyterNotebook:
    artifacts_json = json.dumps(
        artifacts.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
    )
    cells: list[NotebookCell] = [
        _markdown(
            f"# Federated AML case analysis: {artifacts.scenario_id}\n\n"
            f"{narrative.executive_summary}"
        ),
        _markdown(
            "## Privacy boundary\n\n"
            "This notebook is built only from federation-safe artifacts: signed "
            "messages, hash-only evidence, DP provenance, policy verdicts, SAR "
            "fields, and F5 audit results. It does not query silo databases and "
            "does not contain raw customer names, raw account identifiers, or "
            "raw transaction rows."
        ),
        _code(
            "import json\n"
            "import pandas as pd\n\n"
            f"CASE_ARTIFACTS = json.loads({artifacts_json!r})\n"
            "pd.set_option('display.max_colwidth', 140)\n"
            "CASE_ARTIFACTS['scenario_id'], CASE_ARTIFACTS['terminal_code']"
        ),
        _markdown(
            "## Statistical intermediaries\n\n"
            f"{narrative.statistical_method}"
        ),
        _code(
            "intermediaries = pd.DataFrame(CASE_ARTIFACTS['statistical_intermediaries'])\n"
            "intermediaries"
        ),
        _markdown(
            "## Construct the pooled statistic\n\n"
            "The federation combines per-bank statistical intermediaries by "
            "summing same-shaped histogram buckets. Candidate hashes are carried "
            "through as approved tokens, not discovered from raw bank rows."
        ),
        # Deliberate duplication with the module-level ``_sum_vectors``
        # helper at the bottom of this file: the in-notebook function is
        # part of what a regulator/judge SEES when they open the
        # notebook, and the inspection-and-re-run value depends on the
        # pooling math being visible as code rather than as a
        # pre-computed result injected from Python. Keep both copies in
        # lockstep; the alternative (inject the result, drop the code
        # cell) loses the notebook's "verify the algorithm" property.
        _code(
            "def sum_vectors(rows, key):\n"
            "    # Match the module-level ``_sum_vectors`` semantics:\n"
            "    # banks may emit different-width vectors and the\n"
            "    # narrow ``len(rows[0][key])`` form would IndexError\n"
            "    # on the first cross-width pooling.\n"
            "    if not rows:\n"
            "        return []\n"
            "    vectors = [row[key] for row in rows]\n"
            "    width = max(len(v) for v in vectors)\n"
            "    return [\n"
            "        sum(v[idx] for v in vectors if idx < len(v))\n"
            "        for idx in range(width)\n"
            "    ]\n\n"
            "rows = CASE_ARTIFACTS['statistical_intermediaries']\n"
            "pooled = {\n"
            "    'edge_count_distribution': sum_vectors(rows, 'edge_count_distribution'),\n"
            "    'bucketed_flow_histogram': sum_vectors(rows, 'bucketed_flow_histogram'),\n"
            "    'candidate_entity_hashes': sorted({\n"
            "        token\n"
            "        for row in rows\n"
            "        for token in row['candidate_entity_hashes']\n"
            "    }),\n"
            "    'rho_debited_total': sum(row['rho_debited'] for row in rows),\n"
            "}\n"
            "pooled"
        ),
        _markdown(
            "## DP provenance\n\n"
            "Each row below is a primitive provenance record. `rho_debited` is "
            "the privacy-budget spend recorded for the released statistic; "
            "`args_hash` is a canonical hash of primitive arguments, not the "
            "raw argument values."
        ),
        _code(
            "dp = pd.DataFrame(CASE_ARTIFACTS['dp_provenance'])\n"
            "dp[['bank_id', 'field_name', 'primitive_name', 'returned_value_kind', "
            "'rho_debited', 'per_bucket_rho', 'sensitivity', 'sigma_applied', "
            "'eps_delta_display', 'args_hash']] if not dp.empty else dp"
        ),
        _markdown(
            "## AML pattern analysis\n\n"
            f"{narrative.aml_analysis}"
        ),
        _code(
            "graph = CASE_ARTIFACTS.get('graph_pattern_response') or {}\n"
            "pd.DataFrame([{\n"
            "    'pattern_class': graph.get('pattern_class'),\n"
            "    'confidence': graph.get('confidence'),\n"
            "    'suspect_entity_hashes': graph.get('suspect_entity_hashes', []),\n"
            "    'narrative': graph.get('narrative'),\n"
            "}])"
        ),
        _markdown("## Sanctions and PEP context"),
        _code(
            "sanctions = CASE_ARTIFACTS.get('sanctions_response') or {}\n"
            "results = sanctions.get('results') or {}\n"
            "pd.DataFrame([\n"
            "    {'entity_hash': token, **value}\n"
            "    for token, value in results.items()\n"
            "])"
        ),
        _markdown("## SAR draft evidence"),
        _code(
            "sar = CASE_ARTIFACTS.get('sar_draft') or {}\n"
            "pd.DataFrame([{\n"
            "    'sar_id': sar.get('sar_id'),\n"
            "    'filing_institution': sar.get('filing_institution'),\n"
            "    'amount_range_cents': sar.get('suspicious_amount_range'),\n"
            "    'typology_code': sar.get('typology_code'),\n"
            "    'priority': sar.get('sar_priority'),\n"
            "    'mandatory_fields_complete': sar.get('mandatory_fields_complete'),\n"
            "    'contributors': [item.get('bank_id') for item in sar.get('contributors', [])],\n"
            "    'narrative': sar.get('narrative'),\n"
            "}])"
        ),
        _markdown(
            "## F5 audit review\n\n"
            f"{narrative.audit_conclusion}"
        ),
        _code(
            "audit_result = CASE_ARTIFACTS.get('audit_review_result') or {}\n"
            "findings = audit_result.get('findings') or []\n"
            "pd.DataFrame(findings) if findings else pd.DataFrame([{\n"
            "    'human_review_required': audit_result.get('human_review_required'),\n"
            "    'rate_limit_triggered': audit_result.get('rate_limit_triggered'),\n"
            "    'finding_count': 0,\n"
            "}])"
        ),
        _markdown(
            "## Policy and audit evidence\n\n"
            "F6/Lobster Trap verdicts and F5 audit events show whether the case "
            "was produced through governed message flow rather than an "
            "unreviewable data pull."
        ),
        _code(
            "policy = pd.DataFrame(CASE_ARTIFACTS['policy_evidence'])\n"
            "audit_events = pd.DataFrame(CASE_ARTIFACTS['audit_events'])\n"
            "{\n"
            "    'policy_decisions': policy['decision'].value_counts().to_dict() if not policy.empty else {},\n"
            "    'audit_event_kinds': audit_events['kind'].value_counts().to_dict() if not audit_events.empty else {},\n"
            "}"
        ),
        _markdown(
            "## Limitations and reviewer next steps\n\n"
            f"{narrative.limitations}\n\n"
            + "\n".join(f"- {step}" for step in narrative.next_steps)
        ),
        _markdown("## Sanitized artifact appendix"),
        _code("CASE_ARTIFACTS"),
    ]
    return JupyterNotebook(
        cells=cells,
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
    )


def _narrative_input(artifacts: CaseNotebookArtifacts) -> NotebookNarrativeInput:
    policy_counts = Counter(row.decision.value for row in artifacts.policy_evidence)
    graph = artifacts.graph_pattern_response
    sar = artifacts.sar_draft
    audit = artifacts.audit_review_result
    return NotebookNarrativeInput(
        scenario_id=artifacts.scenario_id,
        run_id=artifacts.run_id,
        terminal_code=artifacts.terminal_code,
        terminal_reason=artifacts.terminal_reason,
        pattern_class=graph.pattern_class.value if graph else None,
        pattern_confidence=graph.confidence if graph else None,
        sar_priority=sar.sar_priority.value if sar else None,
        sar_typology=sar.typology_code.value if sar and sar.typology_code else None,
        audit_finding_count=len(audit.findings) if audit else 0,
        policy_decision_counts=dict(policy_counts),
        statistical_intermediaries=artifacts.statistical_intermediaries,
        dp_provenance=artifacts.dp_provenance,
        caveats=[
            "No raw customer names, account identifiers, or transaction rows are present.",
            "DP provenance records show privacy-budget accounting for released aggregates.",
            "LLM narrative is bounded to supplied evidence and should be reviewed by a human.",
        ],
    )


def _template_narrative(input_data: NotebookNarrativeInput) -> NotebookNarrative:
    pattern = input_data.pattern_class or "no_pattern"
    confidence = (
        f"{input_data.pattern_confidence:.2f}"
        if input_data.pattern_confidence is not None
        else "not available"
    )
    policy_counts = ", ".join(
        f"{key}={value}" for key, value in sorted(input_data.policy_decision_counts.items())
    ) or "none"
    bank_count = len(input_data.statistical_intermediaries)
    rho_total = sum(row.rho_debited for row in input_data.statistical_intermediaries)
    return NotebookNarrative(
        executive_summary=(
            f"Run {input_data.run_id} ended with terminal state "
            f"{input_data.terminal_code or 'not available'}. The federation "
            f"found {pattern} with confidence {confidence}, then produced "
            f"SAR priority {input_data.sar_priority or 'not available'} "
            f"and typology {input_data.sar_typology or 'not available'}."
        ),
        statistical_method=(
            f"{bank_count} bank silos supplied hash-only statistical "
            f"intermediaries. Their edge-count and flow-histogram buckets are "
            f"combined in the notebook to reconstruct the pooled statistic. "
            f"The intermediary rows report total rho spend {rho_total:.4f}."
        ),
        aml_analysis=(
            "The AML conclusion comes from the pooled aggregate pattern, not "
            "from raw transaction inspection. F2 receives candidate hash tokens "
            "plus DP-noised histograms and emits the pattern class, confidence, "
            "and suspect hash tokens that downstream components may cite."
        ),
        audit_conclusion=(
            f"F5 reviewed signed audit artifacts and emitted "
            f"{input_data.audit_finding_count} finding(s). F6/Lobster Trap "
            f"policy decision counts were: {policy_counts}."
        ),
        limitations=(
            "This notebook is an analysis artifact over federation-safe output. "
            "It cannot prove facts that were not emitted by the nodes, and it "
            "cannot inspect raw bank records. Any final filing still requires "
            "human compliance review."
        ),
        next_steps=[
            "Review the SAR draft narrative against the provenance tables.",
            "Confirm DP budget use and policy verdict coverage are acceptable.",
            "Escalate any F5 findings or missing evidence before filing.",
        ],
    )


def _statistical_intermediaries(
    state: SessionOrchestratorState,
) -> list[StatisticalIntermediaryRow]:
    request = state.graph_pattern_request
    if request is None:
        return []
    rows: list[StatisticalIntermediaryRow] = []
    for aggregate in request.pattern_aggregates:
        rows.append(
            StatisticalIntermediaryRow(
                bank_id=aggregate.bank_id,
                edge_count_distribution=aggregate.edge_count_distribution,
                bucketed_flow_histogram=aggregate.bucketed_flow_histogram,
                candidate_entity_hashes=list(aggregate.candidate_entity_hashes),
                candidate_entity_count=len(aggregate.candidate_entity_hashes),
                rho_debited=aggregate.rho_debited,
            )
        )
    return rows


def _dp_provenance(state: SessionOrchestratorState) -> list[DpProvenanceRow]:
    return [
        DpProvenanceRow(
            bank_id=item.bank_id,
            field_name=item.record.field_name,
            primitive_name=item.record.primitive_name,
            returned_value_kind=item.record.returned_value_kind.value,
            rho_debited=item.record.rho_debited,
            per_bucket_rho=item.record.per_bucket_rho,
            sensitivity=item.record.sensitivity,
            sigma_applied=item.record.sigma_applied,
            eps_delta_display=item.record.eps_delta_display,
            args_hash=item.record.args_hash,
            timestamp=item.record.timestamp,
        )
        for item in state.pattern_aggregate_provenance
    ]


def _policy_evidence(state: SessionOrchestratorState) -> list[PolicyEvidenceRow]:
    rows: list[PolicyEvidenceRow] = []
    for record in state.policy_evaluations:
        result: PolicyEvaluationResult = record.policy_result
        rows.append(
            PolicyEvidenceRow(
                turn_id=record.turn_id,
                message_id=record.message_id,
                evaluated_message_type=record.evaluated_message_type.value,
                evaluated_sender_agent_id=record.evaluated_sender_agent_id,
                evaluated_recipient_agent_id=record.evaluated_recipient_agent_id,
                decision=result.decision,
                rule_hit_count=len(result.rule_hits),
            )
        )
    return rows


def _markdown(source: str) -> NotebookMarkdownCell:
    return NotebookMarkdownCell(source=_source_lines(source))


def _code(source: str) -> NotebookCodeCell:
    return NotebookCodeCell(source=_source_lines(source))


def _source_lines(source: str) -> list[str]:
    lines = source.splitlines(keepends=True)
    return lines if lines else [""]


def _markdown_cell_html(source: str, *, index: int) -> str:
    return (
        f"<section class=\"case-card markdown-cell\" data-cell=\"{index}\">"
        f"{_markdown_to_html(source)}"
        "</section>"
    )


def _code_cell_html(source: str, *, index: int) -> str:
    return (
        f"<details class=\"case-card code-cell\" data-cell=\"{index}\">"
        f"<summary>Show code cell {index}</summary>"
        f"<pre><code>{escape(source)}</code></pre>"
        "</details>"
    )


def _sum_vectors(vectors: list[list[int]]) -> list[int]:
    if not vectors:
        return []
    width = max(len(vector) for vector in vectors)
    return [
        sum(vector[index] for vector in vectors if index < len(vector))
        for index in range(width)
    ]


def _summary_graphics_html(artifacts: CaseNotebookArtifacts) -> str:
    graph = artifacts.graph_pattern_response
    sar = artifacts.sar_draft
    audit = artifacts.audit_review_result
    pooled_edges = _sum_vectors(
        [row.edge_count_distribution for row in artifacts.statistical_intermediaries]
    )
    pooled_flows = _sum_vectors(
        [row.bucketed_flow_histogram for row in artifacts.statistical_intermediaries]
    )
    policy_counts = Counter(row.decision.value for row in artifacts.policy_evidence)
    rho_by_bank = {
        row.bank_id.value: row.rho_debited
        for row in artifacts.statistical_intermediaries
    }
    summary_cards = [
        ("Terminal", artifacts.terminal_code or "not available"),
        ("Pattern", graph.pattern_class.value if graph else "not available"),
        (
            "Confidence",
            f"{graph.confidence:.2f}" if graph and graph.confidence is not None else "not available",
        ),
        ("SAR priority", sar.sar_priority.value if sar else "not available"),
        ("F5 findings", str(len(audit.findings) if audit else 0)),
        ("Policy verdicts", ", ".join(f"{k}: {v}" for k, v in sorted(policy_counts.items())) or "none"),
    ]
    cards_html = "".join(
        "<div class=\"metric-card\">"
        f"<span>{escape(label)}</span>"
        f"<strong>{escape(value)}</strong>"
        "</div>"
        for label, value in summary_cards
    )
    return (
        "<section class=\"case-card visual-summary\">"
        "<h2>Case visuals</h2>"
        "<p>These graphics are built from the same federation-safe artifact bundle "
        "as the notebook. They show the flow, the pooled statistic, and privacy "
        "budget use without exposing raw bank rows.</p>"
        f"<div class=\"metric-grid\">{cards_html}</div>"
        f"{_flow_svg_html()}"
        "<div class=\"chart-grid\">"
        f"{_bar_chart_html('Pooled edge-count buckets', pooled_edges)}"
        f"{_bar_chart_html('Pooled flow buckets', pooled_flows)}"
        f"{_key_value_bar_html('DP rho by bank', rho_by_bank)}"
        f"{_key_value_bar_html('Policy decisions', dict(policy_counts))}"
        "</div>"
        "</section>"
    )


def _flow_svg_html() -> str:
    nodes = [
        ("A1", 40, 44),
        ("A2", 140, 44),
        ("F1", 250, 44),
        ("A3/P7", 250, 128),
        ("F2", 376, 44),
        ("F3", 484, 44),
        ("F4", 592, 44),
        ("F5", 700, 44),
    ]
    node_html = "".join(
        f"<g><rect x=\"{x}\" y=\"{y}\" rx=\"8\" width=\"72\" height=\"36\" />"
        f"<text x=\"{x + 36}\" y=\"{y + 23}\" text-anchor=\"middle\">{label}</text></g>"
        for label, x, y in nodes
    )
    paths = [
        "M112 62 L140 62",
        "M212 62 L250 62",
        "M286 80 L286 128",
        "M322 146 C356 132 362 90 376 62",
        "M448 62 L484 62",
        "M556 62 L592 62",
        "M664 62 L700 62",
    ]
    path_html = "".join(f"<path d=\"{path}\" />" for path in paths)
    return (
        "<div class=\"flow-graphic\" role=\"img\" "
        "aria-label=\"Canonical AML flow from A1 through F5\">"
        "<svg viewBox=\"0 0 812 188\" preserveAspectRatio=\"xMidYMid meet\">"
        "<defs><marker id=\"arrow\" markerWidth=\"8\" markerHeight=\"8\" "
        "refX=\"7\" refY=\"4\" orient=\"auto\"><path d=\"M0,0 L8,4 L0,8 Z\" /></marker></defs>"
        f"{path_html}{node_html}"
        "<text class=\"boundary\" x=\"286\" y=\"118\" text-anchor=\"middle\">bank silos</text>"
        "</svg>"
        "</div>"
    )


def _bar_chart_html(title: str, values: list[int | float]) -> str:
    if not values:
        return _empty_chart_html(title)
    max_value = max(float(value) for value in values) or 1.0
    bars = "".join(
        "<div class=\"bar-row\">"
        f"<span class=\"bar-label\">B{index + 1}</span>"
        "<span class=\"bar-track\">"
        f"<span class=\"bar-fill\" style=\"width:{(float(value) / max_value) * 100:.2f}%\"></span>"
        "</span>"
        f"<strong>{escape(_format_number(value))}</strong>"
        "</div>"
        for index, value in enumerate(values)
    )
    return f"<div class=\"chart-card\"><h3>{escape(title)}</h3>{bars}</div>"


def _key_value_bar_html(title: str, values: dict[str, int | float]) -> str:
    if not values:
        return _empty_chart_html(title)
    max_value = max(float(value) for value in values.values()) or 1.0
    rows = "".join(
        "<div class=\"bar-row\">"
        f"<span class=\"bar-label\">{escape(key)}</span>"
        "<span class=\"bar-track\">"
        f"<span class=\"bar-fill\" style=\"width:{(float(value) / max_value) * 100:.2f}%\"></span>"
        "</span>"
        f"<strong>{escape(_format_number(value))}</strong>"
        "</div>"
        for key, value in sorted(values.items())
    )
    return f"<div class=\"chart-card\"><h3>{escape(title)}</h3>{rows}</div>"


def _empty_chart_html(title: str) -> str:
    return (
        f"<div class=\"chart-card\"><h3>{escape(title)}</h3>"
        "<p>No released rows for this chart.</p></div>"
    )


def _format_number(value: int | float) -> str:
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _markdown_to_html(source: str) -> str:
    # Intentionally minimal markdown -> HTML: #/##/### headers,
    # ``- `` bullets, and paragraphs. Everything else (inline
    # emphasis, links, raw HTML)
    # is silently dropped after ``html.escape``. This is a whitelist, not
    # a feature gap -- the source can be LLM-generated narrative
    # (NotebookNarrativeMode.LLM), so adopting a full markdown library
    # would give model output more rendering surface (links, HTML
    # passthrough via extensions, inline formatting that interleaves with
    # structured fields). Keep the parser narrow until a real product
    # need forces richer formatting.
    html_parts: list[str] = []
    paragraph: list[str] = []
    bullet_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            html_parts.append(f"<p>{escape(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_bullets() -> None:
        if bullet_items:
            items = "".join(f"<li>{escape(item)}</li>" for item in bullet_items)
            html_parts.append(f"<ul>{items}</ul>")
            bullet_items.clear()

    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_bullets()
            continue
        if line.startswith("### "):
            flush_paragraph()
            flush_bullets()
            html_parts.append(f"<h3>{escape(line[4:])}</h3>")
            continue
        if line.startswith("## "):
            flush_paragraph()
            flush_bullets()
            html_parts.append(f"<h2>{escape(line[3:])}</h2>")
            continue
        if line.startswith("# "):
            flush_paragraph()
            flush_bullets()
            html_parts.append(f"<h1>{escape(line[2:])}</h1>")
            continue
        if line.startswith("- "):
            flush_paragraph()
            bullet_items.append(line[2:])
            continue
        flush_bullets()
        paragraph.append(line)
    flush_paragraph()
    flush_bullets()
    return "\n".join(html_parts)


def _html_document(*, title: str, eyebrow: str, body: str) -> str:
    escaped_title = escape(title)
    escaped_eyebrow = escape(eyebrow)
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\" />\n"
        f"  <title>{escaped_title}</title>\n"
        "  <style>\n"
        "    :root { color-scheme: light; font-family: Inter, ui-sans-serif, "
        "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }\n"
        "    body { margin: 0; background: #f8fafc; color: #0f172a; }\n"
        "    main { max-width: 1040px; margin: 0 auto; padding: 32px 24px 48px; }\n"
        "    .eyebrow { margin: 0 0 8px; color: #0369a1; font-size: 12px; "
        "font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }\n"
        "    h1 { margin: 0 0 16px; font-size: 30px; line-height: 1.15; }\n"
        "    h2 { margin: 0 0 10px; font-size: 18px; }\n"
        "    h3 { margin: 0 0 8px; font-size: 15px; }\n"
        "    p, li { color: #334155; font-size: 14px; line-height: 1.6; }\n"
        "    ul { margin: 8px 0 0 22px; padding: 0; }\n"
        "    .case-card { margin-top: 14px; border: 1px solid #cbd5e1; "
        "border-radius: 8px; background: #ffffff; padding: 18px; "
        "box-shadow: 0 1px 2px rgba(15, 23, 42, .06); }\n"
        "    .code-cell { background: #0f172a; color: #dbeafe; }\n"
        "    .code-cell summary { cursor: pointer; color: #93c5fd; font-size: 11px; "
        "font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }\n"
        "    .code-cell[open] summary { margin-bottom: 8px; }\n"
        "    pre { overflow-x: auto; margin: 0; white-space: pre-wrap; "
        "word-break: break-word; }\n"
        "    code { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', "
        "monospace; font-size: 12px; line-height: 1.55; }\n"
        "    .json-block { margin-top: 14px; border-radius: 8px; background: #0f172a; "
        "color: #dbeafe; padding: 18px; }\n"
        "    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); "
        "gap: 10px; margin-top: 14px; }\n"
        "    .metric-card { border: 1px solid #dbe3ee; border-radius: 8px; padding: 10px; "
        "background: #f8fafc; }\n"
        "    .metric-card span { display: block; color: #64748b; font-size: 11px; "
        "font-weight: 700; text-transform: uppercase; }\n"
        "    .metric-card strong { display: block; margin-top: 4px; color: #0f172a; "
        "font-size: 15px; }\n"
        "    .flow-graphic { margin-top: 14px; overflow-x: auto; border: 1px solid #e2e8f0; "
        "border-radius: 8px; background: #f8fafc; }\n"
        "    .flow-graphic svg { display: block; min-width: 760px; width: 100%; height: auto; }\n"
        "    .flow-graphic rect { fill: #ffffff; stroke: #38bdf8; stroke-width: 1.4; }\n"
        "    .flow-graphic path { stroke: #64748b; stroke-width: 1.6; fill: none; "
        "marker-end: url(#arrow); }\n"
        "    .flow-graphic marker path { fill: #64748b; }\n"
        "    .flow-graphic text { fill: #0f172a; font-size: 13px; font-weight: 700; }\n"
        "    .flow-graphic .boundary { fill: #92400e; font-size: 11px; "
        "letter-spacing: .08em; text-transform: uppercase; }\n"
        "    .chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); "
        "gap: 12px; margin-top: 14px; }\n"
        "    .chart-card { border: 1px solid #dbe3ee; border-radius: 8px; padding: 12px; "
        "background: #f8fafc; }\n"
        "    .bar-row { display: grid; grid-template-columns: minmax(54px, 1fr) 4fr auto; "
        "align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; }\n"
        "    .bar-label { overflow: hidden; color: #475569; text-overflow: ellipsis; white-space: nowrap; }\n"
        "    .bar-track { height: 10px; overflow: hidden; border-radius: 999px; background: #e2e8f0; }\n"
        "    .bar-fill { display: block; height: 100%; border-radius: 999px; "
        "background: linear-gradient(90deg, #0ea5e9, #10b981); }\n"
        "    .bar-row strong { color: #0f172a; font-size: 12px; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <main>\n"
        f"    <p class=\"eyebrow\">{escaped_eyebrow}</p>\n"
        f"    <h1>{escaped_title}</h1>\n"
        f"    {body}\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )


def _case_slug(scenario_id: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in scenario_id.strip().lower()
    ).strip("_")
    return cleaned or "case"
