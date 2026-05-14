import type { TrustDomain } from "@/domain/instances";

export const TRUST_DOMAIN_LABELS: Record<TrustDomain, string> = {
  investigator: "Investigator",
  federation: "Federation TEE",
  bank_alpha: "Bank Alpha",
  bank_beta: "Bank Beta",
  bank_gamma: "Bank Gamma",
};
