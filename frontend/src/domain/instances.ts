/**
 * Trust-domain instance registry.
 *
 * The backend `ComponentId` enum is currently a flat set (`signing`, `replay`,
 * `litellm`, …) — singletons that exist once per process. In reality the
 * federated-silo architecture has five trust domains, each owning its own
 * signing identity, replay cache, route-approval state, DP ledger, LT route,
 * and LiteLLM route. P9b structures the UI around those five **instances**
 * so the topology, attack lab, and inspector all speak the same domain
 * language. When P15 swaps the backend to per-instance ComponentIds, this
 * registry's `mechanism` mappings change but the UI surface does not.
 *
 *   investigator   — A2 + investigator signing/replay/LT/LiteLLM
 *   federation     — F1..F5 + federation signing/replay/route_approval/LT/LiteLLM/audit
 *   bank_alpha     — bank_alpha.A3 + Alpha P7/signing/replay/DP-ledger/LT/LiteLLM
 *   bank_beta      — bank_beta.A3 + Beta P7/signing/replay/DP-ledger/LT/LiteLLM
 *   bank_gamma     — bank_gamma.A3 + Gamma P7/signing/replay/DP-ledger/LT/LiteLLM
 */

import type { ComponentId } from "@/api/types";

export type TrustDomain =
  | "investigator"
  | "federation"
  | "bank_alpha"
  | "bank_beta"
  | "bank_gamma";

export interface InstanceSpec {
  id: TrustDomain;
  label: string;
  shortLabel: string;
  /**
   * Agent ComponentIds that live in this trust domain. For P9b, A2 and F1..F5
   * are global singletons; per-bank A3s already have distinct ComponentIds
   * (`bank_alpha.A3`, `bank_beta.A3`, `bank_gamma.A3`).
   */
  agents: ComponentId[];
  /**
   * Mechanism ComponentIds that conceptually live in this domain. Backend
   * still serves singleton snapshots today; the UI renders the same data
   * under multiple instances. P15 ships real per-instance ComponentIds and
   * this list becomes truly distinct per domain.
   */
  mechanisms: ComponentId[];
}

export const INSTANCES: readonly InstanceSpec[] = [
  {
    id: "investigator",
    label: "Investigator (Bank Alpha A2)",
    shortLabel: "Investigator",
    agents: ["A1", "A2"],
    mechanisms: ["signing", "envelope", "replay", "lobster_trap", "litellm"],
  },
  {
    id: "federation",
    label: "Federation TEE",
    shortLabel: "Federation",
    agents: ["F1", "F2", "F3", "F4", "F5"],
    mechanisms: [
      "signing",
      "envelope",
      "replay",
      "route_approval",
      "lobster_trap",
      "litellm",
      "audit_chain",
    ],
  },
  {
    id: "bank_alpha",
    label: "Bank Alpha silo",
    shortLabel: "Bank Alpha",
    agents: ["bank_alpha.A3", "P7"],
    mechanisms: ["signing", "envelope", "replay", "dp_ledger", "lobster_trap", "litellm"],
  },
  {
    id: "bank_beta",
    label: "Bank Beta silo",
    shortLabel: "Bank Beta",
    agents: ["bank_beta.A3", "P7"],
    mechanisms: ["signing", "envelope", "replay", "dp_ledger", "lobster_trap", "litellm"],
  },
  {
    id: "bank_gamma",
    label: "Bank Gamma silo",
    shortLabel: "Bank Gamma",
    agents: ["bank_gamma.A3", "P7"],
    mechanisms: ["signing", "envelope", "replay", "dp_ledger", "lobster_trap", "litellm"],
  },
] as const;

export function findInstance(id: TrustDomain): InstanceSpec {
  const spec = INSTANCES.find((i) => i.id === id);
  if (!spec) {
    // Defensive: the InstanceSpec union exhausts TrustDomain so this only
    // fires if someone passes an untyped string.
    throw new Error(`unknown TrustDomain: ${id}`);
  }
  return spec;
}
