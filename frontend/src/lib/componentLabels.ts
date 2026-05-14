import type { ComponentId } from "@/api/types";

/**
 * Human-readable labels for `ComponentId` values. Mirrors the backend's
 * `_component(...)` labels in `backend/ui/state.py` so the UI and the
 * raw snapshot data describe the same thing.
 */
export const COMPONENT_LABELS: Record<ComponentId, string> = {
  A1: "A1 local monitor",
  A2: "A2 investigator",
  F1: "F1 coordinator",
  "bank_alpha.A3": "Bank Alpha A3",
  "bank_beta.A3": "Bank Beta A3",
  "bank_gamma.A3": "Bank Gamma A3",
  P7: "P7 stats primitives",
  F2: "F2 graph analysis",
  F3: "F3 sanctions",
  F4: "F4 SAR drafter",
  F5: "F5 auditor",
  lobster_trap: "Lobster Trap",
  litellm: "LiteLLM",
  signing: "Signing",
  envelope: "Envelope verification",
  replay: "Replay cache",
  route_approval: "Route approvals",
  dp_ledger: "DP ledger",
  audit_chain: "Audit chain",
};

export function labelFor(id: ComponentId): string {
  return COMPONENT_LABELS[id] ?? id;
}

/** Mechanisms get a different visual treatment from agents in the topology. */
const MECHANISM_IDS = new Set<ComponentId>([
  "lobster_trap",
  "litellm",
  "signing",
  "envelope",
  "replay",
  "route_approval",
  "dp_ledger",
  "audit_chain",
]);

export function isMechanism(id: ComponentId): boolean {
  return MECHANISM_IDS.has(id);
}
