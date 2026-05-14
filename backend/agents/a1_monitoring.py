"""A1 transaction-monitoring agent and local demo command."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from backend import BACKEND_ROOT
from backend.agents.base import Agent, AuditEmitter
from backend.agents.llm_client import LLMClient
from backend.agents.a1_models import (
    A1BatchInput,
    A1BatchResult,
    A1Decision,
    BypassRuleId,
    SignalCandidate,
)
from backend.agents.rules import BypassRule, ConstraintRule
from backend.runtime.context import AgentRuntimeContext, LLMClientConfig, TrustDomain
from shared.enums import AgentRole, AuditEventKind, BankId, SignalType
from shared.messages import Alert, EvidenceItem


PROJECT_ROOT = BACKEND_ROOT.parent
PROMPT_PATH = BACKEND_ROOT / "agents" / "prompts" / "a1_system.md"
DEFAULT_SDN_LIST_PATH = PROJECT_ROOT / "data" / "mock_sdn_list.json"
CTR_THRESHOLD_USD = 10_000.0
NEAR_CTR_LOWER_USD = 9_000.0
VELOCITY_NEAR_CTR_COUNT_24H = 10

console = Console()
app = typer.Typer(add_completion=False, no_args_is_help=True)


def load_system_prompt(path: Path = PROMPT_PATH) -> str:
    """Load the versioned A1 system prompt."""
    return path.read_text(encoding="utf-8")


def load_sdn_hashes(path: Path = DEFAULT_SDN_LIST_PATH) -> frozenset[str]:
    """Load mock SDN hashes used by A1-B2."""
    if not path.exists():
        return frozenset()
    payload = json.loads(path.read_text(encoding="utf-8"))
    hashes: set[str] = set()
    for entity in payload.get("entities", []):
        if entity.get("source") == "SDN":
            hashes.add(str(entity["name_hash"]))
    return frozenset(hashes)


class A1MonitoringAgent(Agent[A1BatchInput, A1BatchResult]):
    """Local A1 agent that triages one bank's suspicious signals."""

    role = AgentRole.A1
    input_schema = A1BatchInput
    output_schema = A1BatchResult
    declared_intent = "local_transaction_monitoring_triage"

    def __init__(
        self,
        *,
        bank_id: BankId,
        runtime: AgentRuntimeContext,
        local_a2_agent_id: str | None = None,
        sdn_hashes: frozenset[str] | None = None,
        llm: LLMClient | None = None,
        audit: AuditEmitter | None = None,
    ) -> None:
        self.bank_id = bank_id
        self.agent_id = f"{bank_id.value}.A1"
        self.local_a2_agent_id = local_a2_agent_id or f"{bank_id.value}.A2"
        self.sdn_hashes = sdn_hashes if sdn_hashes is not None else load_sdn_hashes()
        self.system_prompt = load_system_prompt()
        self.bypass_rules = build_bypass_rules(self.sdn_hashes)
        self.constraint_rules = build_constraint_rules(self.sdn_hashes)
        super().__init__(runtime=runtime, llm=llm, audit=audit)

    def build_input(self, candidates: list[SignalCandidate]) -> A1BatchInput:
        """Create a typed batch input for this bank's local A1 instance."""
        return A1BatchInput(
            bank_id=self.bank_id,
            a1_agent_id=self.agent_id,
            local_a2_agent_id=self.local_a2_agent_id,
            candidates=candidates,
        )


def build_bypass_rules(
    sdn_hashes: frozenset[str],
) -> tuple[BypassRule[A1BatchInput, A1BatchResult], ...]:
    """Build whole-call bypass rules for deterministic A1-only batches."""
    return (
        _build_single_rule_batch_bypass("A1-B1", sdn_hashes),
        _build_single_rule_batch_bypass("A1-B2", sdn_hashes),
        _build_single_rule_batch_bypass("A1-B3", sdn_hashes),
    )


def build_constraint_rules(
    sdn_hashes: frozenset[str],
) -> tuple[ConstraintRule[A1BatchInput, A1BatchResult], ...]:
    """Build A1 deterministic constraints around LLM output."""
    return (
        ConstraintRule(
            name="one_decision_per_candidate",
            check=has_one_decision_per_candidate,
            violation_msg=lambda _input_data, _output: (
                "output must contain exactly one decision per input signal_id"
            ),
        ),
        ConstraintRule(
            name="alert_routing",
            check=alerts_route_to_local_a2,
            violation_msg=lambda _input_data, _output: (
                "all emitted alerts must route from local A1 to local A2"
            ),
        ),
        ConstraintRule(
            name="bypass_candidates_must_emit",
            check=lambda input_data, output: bypass_candidates_emit(
                input_data,
                output,
                sdn_hashes,
            ),
            violation_msg=lambda _input_data, _output: (
                "candidates matching A1 bypass rules cannot be suppressed"
            ),
        ),
        ConstraintRule(
            name="alert_matches_candidate",
            check=alerts_match_candidates,
            violation_msg=lambda _input_data, _output: (
                "emitted alerts must match their source candidate transaction and account"
            ),
        ),
        ConstraintRule(
            name="evidence_uses_hashed_identifiers",
            check=evidence_uses_hashed_identifiers,
            violation_msg=lambda _input_data, _output: (
                "alert evidence must use hashed identifiers, not raw account or transaction ids"
            ),
        ),
    )


def _build_single_rule_batch_bypass(
    rule_id: BypassRuleId,
    sdn_hashes: frozenset[str],
) -> BypassRule[A1BatchInput, A1BatchResult]:
    return BypassRule(
        name=rule_id,
        trigger=lambda input_data: all(
            candidate_bypass_rule(candidate, sdn_hashes) == rule_id
            for candidate in input_data.candidates
        ),
        force_output=lambda input_data: A1BatchResult(
            decisions=[
                forced_decision(input_data, candidate, rule_id)
                for candidate in input_data.candidates
            ]
        ),
        reason=f"{rule_id} deterministic monitoring bypass triggered.",
    )


def candidate_bypass_rule(
    candidate: SignalCandidate,
    sdn_hashes: frozenset[str],
) -> BypassRuleId | None:
    """Return the A1 bypass rule id for a candidate, if one applies."""
    if candidate.amount >= CTR_THRESHOLD_USD:
        return "A1-B1"
    if candidate.counterparty_account_id_hashed in sdn_hashes:
        return "A1-B2"
    if candidate.recent_near_ctr_count_24h >= VELOCITY_NEAR_CTR_COUNT_24H:
        return "A1-B3"
    return None


def forced_decision(
    input_data: A1BatchInput,
    candidate: SignalCandidate,
    rule_id: BypassRuleId,
) -> A1Decision:
    """Build a deterministic emit decision for an A1 bypass candidate."""
    return A1Decision(
        signal_id=candidate.signal_id,
        action="emit",
        alert=build_alert(
            input_data=input_data,
            candidate=candidate,
            rationale=bypass_rationale(rule_id, candidate),
            bypass_rule_id=rule_id,
        ),
        llm_rationale=f"{rule_id} forced emit before LLM review.",
        bypass_rule_id=rule_id,
    )


def build_alert(
    *,
    input_data: A1BatchInput,
    candidate: SignalCandidate,
    rationale: str,
    bypass_rule_id: BypassRuleId | None = None,
) -> Alert:
    """Build a P4 Alert from one A1 candidate."""
    return Alert(
        sender_agent_id=input_data.a1_agent_id,
        sender_role=AgentRole.A1,
        sender_bank_id=input_data.bank_id,
        recipient_agent_id=input_data.local_a2_agent_id,
        transaction_id=candidate.transaction_id,
        account_id=candidate.account_id,
        signal_type=map_signal_type(candidate, bypass_rule_id),
        severity=alert_severity(candidate, bypass_rule_id),
        rationale=rationale,
        evidence=[
            EvidenceItem(
                summary=evidence_summary(candidate, bypass_rule_id),
                entity_hashes=[candidate.customer_name_hash],
                account_hashes=[hash_identifier(candidate.account_id)],
                transaction_hashes=[hash_identifier(candidate.transaction_id)],
            )
        ],
    )


def map_signal_type(
    candidate: SignalCandidate,
    bypass_rule_id: BypassRuleId | None,
) -> SignalType:
    """Map local scorer labels and bypasses onto shared alert signal types.

    A1-B1 (transaction amount >= $10K) maps to CTR_REPORT, not STRUCTURING.
    Structuring is the sub-$10K splitting typology; a single transaction at
    or above the threshold is a Currency Transaction Report obligation.
    """
    if bypass_rule_id == "A1-B1":
        return SignalType.CTR_REPORT
    if bypass_rule_id == "A1-B2":
        return SignalType.SANCTIONS_MATCH
    if bypass_rule_id == "A1-B3":
        return SignalType.RAPID_MOVEMENT
    if "velocity" in candidate.source_signal_type:
        return SignalType.RAPID_MOVEMENT
    if "counterparty" in candidate.source_signal_type:
        return SignalType.COUNTERPARTY_RISK
    return SignalType.STRUCTURING


def alert_severity(
    candidate: SignalCandidate,
    bypass_rule_id: BypassRuleId | None,
) -> float:
    """Return bounded alert severity for a candidate."""
    if bypass_rule_id in {"A1-B1", "A1-B2"}:
        return 1.0
    if bypass_rule_id == "A1-B3":
        return 0.95
    return min(max(candidate.source_severity, 0.0), 1.0)


def bypass_rationale(rule_id: BypassRuleId, candidate: SignalCandidate) -> str:
    """Return concise deterministic rationale for a bypass alert."""
    if rule_id == "A1-B1":
        return f"A1-B1: transaction amount {candidate.amount:.2f} meets CTR threshold."
    if rule_id == "A1-B2":
        return "A1-B2: counterparty hash matches a known SDN entry."
    return (
        "A1-B3: account has "
        f"{candidate.recent_near_ctr_count_24h} near-CTR transactions in 24 hours."
    )


def evidence_summary(
    candidate: SignalCandidate,
    bypass_rule_id: BypassRuleId | None,
) -> str:
    """Return a safe hash-only evidence summary."""
    if bypass_rule_id is not None:
        return f"{bypass_rule_id} local monitoring signal for hashed entity."
    return f"Local {candidate.source_signal_type} signal for hashed entity."


def hash_identifier(value: str) -> str:
    """Hash a local identifier before placing it in cross-message evidence."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def has_one_decision_per_candidate(
    input_data: A1BatchInput,
    output: A1BatchResult,
) -> bool:
    expected = [candidate.signal_id for candidate in input_data.candidates]
    actual = [decision.signal_id for decision in output.decisions]
    return len(actual) == len(set(actual)) and set(actual) == set(expected)


def alerts_route_to_local_a2(
    input_data: A1BatchInput,
    output: A1BatchResult,
) -> bool:
    for decision in output.decisions:
        if decision.alert is None:
            continue
        alert = decision.alert
        if alert.sender_agent_id != input_data.a1_agent_id:
            return False
        if alert.sender_role != AgentRole.A1:
            return False
        if alert.sender_bank_id != input_data.bank_id:
            return False
        if alert.recipient_agent_id != input_data.local_a2_agent_id:
            return False
    return True


def bypass_candidates_emit(
    input_data: A1BatchInput,
    output: A1BatchResult,
    sdn_hashes: frozenset[str],
) -> bool:
    decisions = {decision.signal_id: decision for decision in output.decisions}
    for candidate in input_data.candidates:
        rule_id = candidate_bypass_rule(candidate, sdn_hashes)
        if rule_id is None:
            continue
        decision = decisions.get(candidate.signal_id)
        if decision is None or decision.action != "emit" or decision.alert is None:
            return False
    return True


def alerts_match_candidates(
    input_data: A1BatchInput,
    output: A1BatchResult,
) -> bool:
    candidates = {candidate.signal_id: candidate for candidate in input_data.candidates}
    for decision in output.decisions:
        if decision.alert is None:
            continue
        candidate = candidates.get(decision.signal_id)
        if candidate is None:
            return False
        if decision.alert.transaction_id != candidate.transaction_id:
            return False
        if decision.alert.account_id != candidate.account_id:
            return False
    return True


def evidence_uses_hashed_identifiers(
    input_data: A1BatchInput,
    output: A1BatchResult,
) -> bool:
    candidates = {candidate.signal_id: candidate for candidate in input_data.candidates}
    for decision in output.decisions:
        if decision.alert is None:
            continue
        candidate = candidates.get(decision.signal_id)
        if candidate is None:
            return False
        for item in decision.alert.evidence:
            if candidate.account_id in item.account_hashes:
                return False
            if candidate.transaction_id in item.transaction_hashes:
                return False
    return True


def demo_stub_result(input_data: A1BatchInput, sdn_hashes: frozenset[str]) -> A1BatchResult:
    """Build deterministic stub decisions for local demo runs."""
    decisions: list[A1Decision] = []
    emitted = 0
    for candidate in input_data.candidates:
        rule_id = candidate_bypass_rule(candidate, sdn_hashes)
        planted_local_signal = (
            "_s1_" in candidate.transaction_id
            and candidate.source_signal_type == "amount_near_ctr_threshold"
        )
        should_emit = (
            rule_id is not None
            or planted_local_signal
            or (
                candidate.source_signal_type == "amount_near_ctr_threshold"
                and emitted < 8
            )
        )
        if should_emit:
            emitted += 1
            decisions.append(
                A1Decision(
                    signal_id=candidate.signal_id,
                    action="emit",
                    alert=build_alert(
                        input_data=input_data,
                        candidate=candidate,
                        rationale=(
                            bypass_rationale(rule_id, candidate)
                            if rule_id
                            else "LLM triage: repeated near-threshold activity merits review."
                        ),
                        bypass_rule_id=rule_id,
                    ),
                    llm_rationale=(
                        f"{rule_id} forced emit."
                        if rule_id
                        else "LLM triage emit."
                    ),
                    bypass_rule_id=rule_id,
                )
            )
        else:
            decisions.append(
                A1Decision(
                    signal_id=candidate.signal_id,
                    action="suppress",
                    alert=None,
                    llm_rationale="Likely monitoring noise.",
                )
            )
    return A1BatchResult(decisions=decisions)


def synthetic_ctr_candidate() -> SignalCandidate:
    """Build a synthetic CTR bypass candidate for tests and demo output."""
    return SignalCandidate(
        signal_id="synthetic_A1_B1_ctr",
        transaction_id="synthetic_txn_A1_B1_ctr",
        amount=10_250.0,
        transaction_type="debit",
        channel="cash",
        timestamp=datetime(2026, 5, 13, 12, 0, 0),
        account_id="synthetic_acct_A1_B1",
        customer_name_hash="synthetic_entity_hash_A1_B1",
        customer_kyc_tier="small_business",
        recent_near_ctr_count_24h=1,
        counterparty_account_id_hashed="synthetic_counterparty_A1_B1",
        source_signal_type="synthetic_ctr_threshold",
        source_severity=1.0,
    )


def synthetic_sdn_candidate(sdn_hash: str = "sdn_counterparty_hash_0001") -> SignalCandidate:
    """Build a synthetic SDN bypass candidate for tests and demo output."""
    return SignalCandidate(
        signal_id="synthetic_A1_B2_sdn",
        transaction_id="synthetic_txn_A1_B2_sdn",
        amount=7_800.0,
        transaction_type="wire",
        channel="wire",
        timestamp=datetime(2026, 5, 13, 12, 0, 0),
        account_id="synthetic_acct_A1_B2",
        customer_name_hash="synthetic_entity_hash_A1_B2",
        customer_kyc_tier="commercial",
        recent_near_ctr_count_24h=1,
        counterparty_account_id_hashed=sdn_hash,
        source_signal_type="synthetic_sdn_counterparty",
        source_severity=1.0,
    )


def synthetic_velocity_candidate() -> SignalCandidate:
    """Build a synthetic velocity bypass candidate for tests."""
    return SignalCandidate(
        signal_id="synthetic_A1_B3_velocity",
        transaction_id="synthetic_txn_A1_B3_velocity",
        amount=9_250.0,
        transaction_type="debit",
        channel="cash",
        timestamp=datetime(2026, 5, 13, 12, 0, 0),
        account_id="synthetic_acct_A1_B3",
        customer_name_hash="synthetic_entity_hash_A1_B3",
        customer_kyc_tier="small_business",
        recent_near_ctr_count_24h=10,
        counterparty_account_id_hashed="synthetic_counterparty_A1_B3",
        source_signal_type="synthetic_velocity_spike",
        source_severity=0.95,
    )


@app.callback()
def main() -> None:
    """A1 local monitoring commands."""


@app.command("demo")
def demo(
    bank: Annotated[BankId, typer.Option(help="Bank id to run locally.")] = BankId.BANK_ALPHA,
    limit: Annotated[int, typer.Option(help="Number of real local candidates to load.")] = 50,
    stub: Annotated[bool, typer.Option(help="Use deterministic LLM stub mode.")] = True,
) -> None:
    """Run a local A1 demo and print a decision table."""
    from backend.silos.local_reader import read_signal_candidates

    runtime = AgentRuntimeContext(
        run_id="a1-demo",
        node_id=f"{bank.value}-local",
        trust_domain=TrustDomain.BANK_SILO,
        llm=LLMClientConfig(
            default_model="gemini-narrator",
            stub_mode=stub,
            node_id=f"{bank.value}-local",
        ),
    )
    sdn_hashes = load_sdn_hashes()
    real_candidates = read_signal_candidates(bank, limit=limit)
    synthetic_candidates = [synthetic_ctr_candidate(), synthetic_sdn_candidate()]

    agent = A1MonitoringAgent(bank_id=bank, runtime=runtime, sdn_hashes=sdn_hashes)
    real_input = agent.build_input(real_candidates)
    stub_responses = [demo_stub_result(real_input, sdn_hashes)] if stub else None
    agent.llm = LLMClient(runtime.llm, stub_responses=stub_responses)

    results = [agent.run(real_input)]
    for candidate in synthetic_candidates:
        results.append(agent.run(agent.build_input([candidate])))

    all_candidates = real_candidates + synthetic_candidates
    all_decisions = [decision for result in results for decision in result.decisions]
    render_demo_table(bank, all_candidates, all_decisions, real_count=len(real_candidates))


def render_demo_table(
    bank: BankId,
    candidates: list[SignalCandidate],
    decisions: list[A1Decision],
    *,
    real_count: int,
) -> None:
    """Render the local A1 demo decision table."""
    candidate_by_id = {candidate.signal_id: candidate for candidate in candidates}
    emitted = sum(1 for decision in decisions if decision.action == "emit")
    suppressed = len(decisions) - emitted

    table = Table(title=f"{bank.value.replace('_', ' ').title()} A1 Monitoring")
    table.add_column("signal_id")
    table.add_column("amount", justify="right")
    table.add_column("source")
    table.add_column("decision")
    table.add_column("bypass")
    table.add_column("rationale")

    for decision in decisions[: min(len(decisions), 14)]:
        candidate = candidate_by_id[decision.signal_id]
        label = "S1 local" if "_s1_" in candidate.transaction_id else ""
        table.add_row(
            decision.signal_id,
            f"{candidate.amount:,.2f}",
            f"{candidate.source_signal_type} {label}".strip(),
            decision.action,
            decision.bypass_rule_id or "",
            decision.llm_rationale,
        )

    console.print(f"Loaded {real_count} suspicious signal candidates")
    console.print("Injected 2 deterministic bypass examples")
    console.print(table)
    console.print(f"Emitted {emitted} alerts to local A2")
    console.print(f"Suppressed {suppressed} noisy signals")


if __name__ == "__main__":
    app()
