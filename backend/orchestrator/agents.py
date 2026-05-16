"""Agent registry and local test-mode dependencies for P15."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from backend.agents.a1_monitoring import A1MonitoringAgent
from backend.agents.a2_investigator import A2InvestigatorAgent
from backend.agents.a2_states import SynthesisDecision
from backend.agents.a3_silo_responder import A3SiloResponderAgent
from backend.agents.base import AuditEmitter
from backend.agents.f1_coordinator import F1CoordinatorAgent
from backend.agents.f3_sanctions import F3SanctionsAgent
from backend.agents.llm_client import LLMClient
from backend.runtime.context import AgentRuntimeContext, LLMClientConfig, TrustDomain
from backend.security import (
    PrincipalAllowlist,
    PrincipalAllowlistEntry,
    ReplayCache,
    generate_key_pair,
)
from backend.silos.budget import RequesterKey
from backend.silos.stats_primitives import BankStatsPrimitives, PrimitiveResult
from shared.enums import (
    AgentRole,
    BankId,
    MessageType,
    PrivacyUnit,
    ResponseValueKind,
    RouteKind,
)
from shared.messages import BankAggregate, PrimitiveCallRecord


BANK_IDS: tuple[BankId, ...] = (
    BankId.BANK_ALPHA,
    BankId.BANK_BETA,
    BankId.BANK_GAMMA,
)


class PrimitiveProvider(Protocol):
    """Subset of P7 methods A3 needs during local orchestration."""

    bank_id: BankId


@dataclass(frozen=True)
class OrchestratorPrincipal:
    """One demo principal with private key retained server-side."""

    agent_id: str
    role: AgentRole
    bank_id: BankId
    signing_key_id: str
    private_key: str
    public_key: str


@dataclass(frozen=True)
class OrchestratorPrincipals:
    """Principal set shared by UI probes and the live orchestrator."""

    principals: dict[str, OrchestratorPrincipal]
    allowlist: PrincipalAllowlist

    @classmethod
    def build(cls) -> OrchestratorPrincipals:
        principals: dict[str, OrchestratorPrincipal] = {}
        specs = [
            *(
                (f"{bank_id.value}.A2", AgentRole.A2, bank_id)
                for bank_id in BANK_IDS
            ),
            *(
                (f"{bank_id.value}.A3", AgentRole.A3, bank_id)
                for bank_id in BANK_IDS
            ),
            ("federation.F1", AgentRole.F1, BankId.FEDERATION),
            *(
                (f"{bank_id.value}.F6", AgentRole.F6, bank_id)
                for bank_id in BANK_IDS
            ),
            ("federation.F6", AgentRole.F6, BankId.FEDERATION),
        ]
        for agent_id, role, bank_id in specs:
            pair = generate_key_pair(f"{agent_id}.demo-key")
            principals[agent_id] = OrchestratorPrincipal(
                agent_id=agent_id,
                role=role,
                bank_id=bank_id,
                signing_key_id=pair.signing_key_id,
                private_key=pair.private_key,
                public_key=pair.public_key,
            )

        return cls(
            principals=principals,
            allowlist=PrincipalAllowlist(_allowlist_entries(principals)),
        )


@dataclass
class AgentRegistry:
    """Per-session local agent instances."""

    a1_by_bank: dict[BankId, A1MonitoringAgent]
    a2_by_bank: dict[BankId, A2InvestigatorAgent]
    a3_by_bank: dict[BankId, A3SiloResponderAgent]
    f1: F1CoordinatorAgent
    f3: F3SanctionsAgent
    replay_cache: ReplayCache

    @classmethod
    def build(
        cls,
        *,
        run_id: str,
        session_mode: str,
        principals: OrchestratorPrincipals,
        audit: AuditEmitter,
    ) -> AgentRegistry:
        stub_mode = session_mode != "live"
        replay_cache = ReplayCache()
        a1_by_bank: dict[BankId, A1MonitoringAgent] = {}
        a2_by_bank: dict[BankId, A2InvestigatorAgent] = {}
        a3_by_bank: dict[BankId, A3SiloResponderAgent] = {}

        for bank_id in BANK_IDS:
            a1_by_bank[bank_id] = A1MonitoringAgent(
                bank_id=bank_id,
                runtime=_context(
                    run_id=run_id,
                    node_id=f"{bank_id.value}-a1-node",
                    trust_domain=TrustDomain.BANK_SILO,
                    stub_mode=stub_mode,
                    audit=audit,
                ),
                audit=audit,
            )
            a2_by_bank[bank_id] = A2InvestigatorAgent(
                bank_id=bank_id,
                runtime=_context(
                    run_id=run_id,
                    node_id=f"{bank_id.value}-a2-node",
                    trust_domain=TrustDomain.INVESTIGATOR,
                    stub_mode=stub_mode,
                    audit=audit,
                ),
                llm=LLMClient(
                    _llm_config(
                        node_id=f"{bank_id.value}-a2-node",
                        stub_mode=stub_mode,
                    ),
                    stub_responses=[
                        SynthesisDecision(
                            action="sar_contribution",
                            rationale=(
                                "Peer-bank aggregate signals corroborate the local "
                                "structuring alert under Section 314(b)."
                            ),
                        )
                    ],
                ),
                audit=audit,
            )

            a3_principal = principals.principals[f"{bank_id.value}.A3"]
            a3_by_bank[bank_id] = A3SiloResponderAgent(
                bank_id=bank_id,
                runtime=_context(
                    run_id=run_id,
                    node_id=f"{bank_id.value}-a3-node",
                    trust_domain=TrustDomain.BANK_SILO,
                    stub_mode=stub_mode,
                    audit=audit,
                ),
                primitives=(
                    StubBankStatsPrimitives(bank_id=bank_id)
                    if stub_mode
                    else BankStatsPrimitives(bank_id=bank_id)
                ),
                principal_allowlist=principals.allowlist,
                replay_cache=replay_cache,
                response_private_key=a3_principal.private_key,
                response_signing_key_id=a3_principal.signing_key_id,
                audit=audit,
            )

        f1_principal = principals.principals["federation.F1"]
        f1 = F1CoordinatorAgent(
            runtime=_context(
                run_id=run_id,
                node_id="federation-f1-node",
                trust_domain=TrustDomain.FEDERATION,
                stub_mode=stub_mode,
                audit=audit,
            ),
            principal_allowlist=principals.allowlist,
            replay_cache=replay_cache,
            private_key=f1_principal.private_key,
            signing_key_id=f1_principal.signing_key_id,
            audit=audit,
        )
        f3 = F3SanctionsAgent(
            runtime=_context(
                run_id=run_id,
                node_id="federation-f3-node",
                trust_domain=TrustDomain.FEDERATION,
                stub_mode=stub_mode,
                audit=audit,
            ),
            audit=audit,
        )
        return cls(
            a1_by_bank=a1_by_bank,
            a2_by_bank=a2_by_bank,
            a3_by_bank=a3_by_bank,
            f1=f1,
            f3=f3,
            replay_cache=replay_cache,
        )


class StubBankStatsPrimitives:
    """Deterministic P7 substitute for stub-mode orchestrator runs."""

    def __init__(self, *, bank_id: BankId) -> None:
        if bank_id == BankId.FEDERATION:
            raise ValueError("stub primitives require a real bank")
        self.bank_id = bank_id

    def count_entities_by_name_hash(
        self,
        *,
        name_hashes: list[str],
        requester: RequesterKey,
        rho: float = 0.0,
    ) -> PrimitiveResult:
        _ = requester
        return PrimitiveResult(
            value=len(name_hashes),
            records=[
                # Entity presence is an exact P7 primitive; A3 invokes it with rho=0.
                _primitive_record(
                    field_name="entity_count",
                    primitive_name="stub_count_entities_by_name_hash",
                    args={"name_hashes": name_hashes, "rho": rho},
                    returned_value_kind=ResponseValueKind.INT,
                    rho_debited=0.0,
                )
            ],
        )

    def alert_count_for_entity(
        self,
        *,
        name_hash: str,
        window: tuple[date, date],
        requester: RequesterKey,
        rho: float = 0.02,
    ) -> PrimitiveResult:
        _ = requester
        value_by_bank = {
            BankId.BANK_ALPHA: 4,
            BankId.BANK_BETA: 3,
            BankId.BANK_GAMMA: 2,
        }
        return PrimitiveResult(
            value=value_by_bank[self.bank_id],
            records=[
                _primitive_record(
                    field_name="alert_count",
                    primitive_name="stub_alert_count_for_entity",
                    args={
                        "name_hash": name_hash,
                        "window_start": window[0].isoformat(),
                        "window_end": window[1].isoformat(),
                        "rho": rho,
                    },
                    returned_value_kind=ResponseValueKind.INT,
                    rho_debited=rho,
                )
            ],
        )

    def flow_histogram(
        self,
        *,
        name_hashes: list[str],
        window: tuple[date, date],
        requester: RequesterKey,
        rho: float = 0.03,
    ) -> PrimitiveResult:
        _ = requester
        return PrimitiveResult(
            value=[0, 2, 4, 1, 0],
            records=[
                _primitive_record(
                    field_name="flow_histogram",
                    primitive_name="stub_flow_histogram",
                    args={
                        "name_hashes": name_hashes,
                        "window_start": window[0].isoformat(),
                        "window_end": window[1].isoformat(),
                        "rho": rho,
                    },
                    returned_value_kind=ResponseValueKind.HISTOGRAM,
                    rho_debited=rho,
                )
            ],
        )

    def pattern_aggregate_for_f2(
        self,
        *,
        window: tuple[date, date],
        requester: RequesterKey,
        candidate_entity_hashes: list[str] | None = None,
        rho: float = 0.04,
    ) -> PrimitiveResult:
        _ = requester
        approved_candidates = sorted(set(candidate_entity_hashes or []))
        aggregate = BankAggregate(
            bank_id=self.bank_id,
            edge_count_distribution=[1, 0, 2, 0],
            bucketed_flow_histogram=[0, 4, 1, 0, 0],
            candidate_entity_hashes=approved_candidates,
            rho_debited=rho,
        )
        return PrimitiveResult(
            value=aggregate,
            records=[
                _primitive_record(
                    field_name="edge_count_distribution",
                    primitive_name="stub_pattern_aggregate_for_f2",
                    args={"window_start": window[0].isoformat(), "rho": rho},
                    returned_value_kind=ResponseValueKind.HISTOGRAM,
                    rho_debited=rho / 2,
                ),
                _primitive_record(
                    field_name="bucketed_flow_histogram",
                    primitive_name="stub_pattern_aggregate_for_f2",
                    args={"window_end": window[1].isoformat(), "rho": rho},
                    returned_value_kind=ResponseValueKind.HISTOGRAM,
                    rho_debited=rho / 2,
                ),
                _primitive_record(
                    field_name="candidate_entity_hashes",
                    primitive_name="stub_pattern_aggregate_for_f2",
                    args={
                        "candidate_entity_hashes": approved_candidates,
                        "rho": 0.0,
                    },
                    returned_value_kind=ResponseValueKind.HASH_LIST,
                    rho_debited=0.0,
                ),
            ],
        )


def _allowlist_entries(
    principals: dict[str, OrchestratorPrincipal],
) -> list[PrincipalAllowlistEntry]:
    # These message and recipient constraints are consumed by
    # PrincipalAllowlist.verify_message/verify_route_approval, not by the
    # dataclass itself. Keeping them here makes the orchestrator and UI probes
    # share the same security envelope policy.
    entries: list[PrincipalAllowlistEntry] = []
    for bank_id in BANK_IDS:
        a2 = principals[f"{bank_id.value}.A2"]
        entries.append(
            PrincipalAllowlistEntry(
                agent_id=a2.agent_id,
                role=a2.role,
                bank_id=a2.bank_id,
                signing_key_id=a2.signing_key_id,
                public_key=a2.public_key,
                allowed_message_types=[MessageType.SEC314B_QUERY.value],
                allowed_recipients=["federation.F1"],
            )
        )
        a3 = principals[f"{bank_id.value}.A3"]
        entries.append(
            PrincipalAllowlistEntry(
                agent_id=a3.agent_id,
                role=a3.role,
                bank_id=a3.bank_id,
                signing_key_id=a3.signing_key_id,
                public_key=a3.public_key,
                allowed_message_types=[MessageType.SEC314B_RESPONSE.value],
                allowed_recipients=["federation.F1"],
            )
        )

    f1 = principals["federation.F1"]
    entries.append(
        PrincipalAllowlistEntry(
            agent_id=f1.agent_id,
            role=f1.role,
            bank_id=f1.bank_id,
            signing_key_id=f1.signing_key_id,
            public_key=f1.public_key,
            allowed_message_types=[
                MessageType.SEC314B_QUERY.value,
                MessageType.LOCAL_SILO_CONTRIBUTION_REQUEST.value,
                MessageType.SEC314B_RESPONSE.value,
                MessageType.SANCTIONS_CHECK_REQUEST.value,
            ],
            allowed_recipients=["*"],
            allowed_routes=[RouteKind.PEER_314B, RouteKind.LOCAL_CONTRIBUTION],
        )
    )
    entries.extend(
        PrincipalAllowlistEntry(
            agent_id=principal.agent_id,
            role=principal.role,
            bank_id=principal.bank_id,
            signing_key_id=principal.signing_key_id,
            public_key=principal.public_key,
            allowed_message_types=[
                MessageType.POLICY_EVALUATION_RESULT.value,
                MessageType.AUDIT_EVENT.value,
            ],
            allowed_recipients=["*"],
        )
        for principal in principals.values()
        if principal.role == AgentRole.F6
    )
    return entries


def _context(
    *,
    run_id: str,
    node_id: str,
    trust_domain: TrustDomain,
    stub_mode: bool,
    audit: AuditEmitter,
) -> AgentRuntimeContext:
    return AgentRuntimeContext(
        run_id=run_id,
        node_id=node_id,
        trust_domain=trust_domain,
        llm=_llm_config(node_id=node_id, stub_mode=stub_mode),
        audit=audit,
    )


def _llm_config(*, node_id: str, stub_mode: bool) -> LLMClientConfig:
    return LLMClientConfig(
        default_model="gemini-narrator",
        stub_mode=stub_mode,
        node_id=node_id,
    )


def _primitive_record(
    *,
    field_name: str,
    primitive_name: str,
    args: dict[str, object],
    returned_value_kind: ResponseValueKind,
    rho_debited: float,
) -> PrimitiveCallRecord:
    return PrimitiveCallRecord(
        field_name=field_name,
        primitive_name=primitive_name,
        args_hash=_args_hash(args),
        privacy_unit=PrivacyUnit.TRANSACTION,
        rho_debited=rho_debited,
        eps_delta_display=(0.5, 0.000001) if rho_debited else None,
        sigma_applied=5.0 if rho_debited else None,
        sensitivity=1.0,
        returned_value_kind=returned_value_kind,
    )


def _args_hash(args: dict[str, object]) -> str:
    encoded = json.dumps(args, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
