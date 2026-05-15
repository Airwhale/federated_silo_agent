import type { ComponentId } from "../api/types";

export type TrustDomain = "investigator" | "federation" | "bank_alpha" | "bank_beta" | "bank_gamma";

export type InstanceMechanism = {
  id: string;
  label: string;
  componentId: ComponentId;
  kind: "agent" | "security" | "policy" | "model" | "data" | "audit";
};

export type TrustInstance = {
  id: TrustDomain;
  label: string;
  subtitle: string;
  mechanisms: InstanceMechanism[];
};

const sharedSecurity: InstanceMechanism[] = [
  { id: "signing", label: "Signing", componentId: "signing", kind: "security" },
  { id: "envelope", label: "Envelope", componentId: "envelope", kind: "security" },
  { id: "replay", label: "Replay", componentId: "replay", kind: "security" },
  { id: "lt", label: "Lobster Trap", componentId: "lobster_trap", kind: "policy" },
  { id: "llm", label: "Model route", componentId: "litellm", kind: "model" },
];

function silo(
  id: TrustDomain,
  label: string,
  a3: ComponentId,
): TrustInstance {
  return {
    id,
    label,
    subtitle: "Bank silo trust domain",
    mechanisms: [
      { id: "a3", label: "A3 responder", componentId: a3, kind: "agent" },
      { id: "p7", label: "P7 primitives", componentId: "P7", kind: "data" },
      { id: "dp", label: "DP ledger", componentId: "dp_ledger", kind: "data" },
      { id: "route", label: "Route approval", componentId: "route_approval", kind: "security" },
      ...sharedSecurity,
    ],
  };
}

export const TRUST_INSTANCES: TrustInstance[] = [
  {
    id: "investigator",
    label: "Investigator",
    subtitle: "Outside-TEE bank investigator",
    mechanisms: [
      { id: "a1", label: "A1 monitor", componentId: "A1", kind: "agent" },
      { id: "a2", label: "A2 investigator", componentId: "A2", kind: "agent" },
      ...sharedSecurity,
    ],
  },
  {
    id: "federation",
    label: "Federation",
    subtitle: "Federation coordination domain",
    mechanisms: [
      { id: "f1", label: "F1 coordinator", componentId: "F1", kind: "agent" },
      { id: "f2", label: "F2 graph", componentId: "F2", kind: "agent" },
      { id: "f3", label: "F3 sanctions", componentId: "F3", kind: "agent" },
      { id: "f4", label: "F4 SAR", componentId: "F4", kind: "agent" },
      { id: "f5", label: "F5 auditor", componentId: "F5", kind: "agent" },
      { id: "route", label: "Route approval", componentId: "route_approval", kind: "security" },
      { id: "audit", label: "Audit chain", componentId: "audit_chain", kind: "audit" },
      ...sharedSecurity,
    ],
  },
  silo("bank_alpha", "Bank Alpha", "bank_alpha.A3"),
  silo("bank_beta", "Bank Beta", "bank_beta.A3"),
  silo("bank_gamma", "Bank Gamma", "bank_gamma.A3"),
];

export const componentLabel = (componentId: ComponentId) =>
  TRUST_INSTANCES.flatMap((item) => item.mechanisms).find(
    (mechanism) => mechanism.componentId === componentId,
  )?.label ?? componentId;

export const trustDomainLabel = (id: TrustDomain) =>
  TRUST_INSTANCES.find((item) => item.id === id)?.label ?? id;
