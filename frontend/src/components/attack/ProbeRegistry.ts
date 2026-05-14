import type { AttackerProfile, ComponentId, ProbeKind } from "@/api/types";
import type { TrustDomain } from "@/domain/instances";

export interface ProbeConfig {
  kind: ProbeKind;
  label: string;
  summary: string;
  /**
   * Default target_component to send to /sessions/{id}/probes. The backend
   * accepts any ComponentId; this picks the most natural one for the demo.
   */
  defaultTarget: ComponentId;
  /**
   * Default attacker profile.
   */
  defaultProfile: AttackerProfile;
  /**
   * P9b: instance targeting is UI-only today. The probe form lets the judge
   * say "attack Bank Beta's A3 route binding" — backend treats that as a
   * generic /probes call against `target_component`, and we attach the
   * trust-domain hint to the timeline event title. P15 supplies real
   * per-instance probes.
   */
  defaultInstance: TrustDomain;
  /**
   * Whether this probe accepts free-form payload_text (e.g. prompt_injection).
   */
  acceptsPayload: boolean;
  /**
   * Probes whose live adapter has not landed yet. The card surfaces this
   * honestly instead of pretending the result is "real".
   */
  availableAfter?: string;
}

export const PROBE_REGISTRY: readonly ProbeConfig[] = [
  {
    kind: "prompt_injection",
    label: "Prompt injection",
    summary:
      "Send a natural-language attempt to subvert the LT-policed LLM channel. Today returns a typed `not_built` placeholder until P14 lands the LT verdict adapter.",
    defaultTarget: "lobster_trap",
    defaultProfile: "unknown",
    defaultInstance: "federation",
    acceptsPayload: true,
    availableAfter: "P14",
  },
  {
    kind: "unsigned_message",
    label: "Unsigned message",
    summary:
      "Send a message with no `signing_key_id`. Signature gate should refuse before any downstream check.",
    defaultTarget: "F1",
    defaultProfile: "unknown",
    defaultInstance: "federation",
    acceptsPayload: false,
  },
  {
    kind: "body_tamper",
    label: "Body tamper",
    summary:
      "Sign a valid query, then mutate the body. Canonical body-hash gate should refuse the now-stale signature.",
    defaultTarget: "F1",
    defaultProfile: "valid_but_malicious",
    defaultInstance: "federation",
    acceptsPayload: false,
  },
  {
    kind: "wrong_role",
    label: "Wrong role",
    summary:
      "A3 signing key claims an F1 sender role. Allowlist's declared-identity check should refuse on role mismatch.",
    defaultTarget: "F1",
    defaultProfile: "wrong_role",
    defaultInstance: "federation",
    acceptsPayload: false,
  },
  {
    kind: "replay_nonce",
    label: "Replay nonce",
    summary:
      "Send the same signed envelope twice in a row. Replay cache should refuse the second use.",
    defaultTarget: "replay",
    defaultProfile: "valid_but_malicious",
    defaultInstance: "federation",
    acceptsPayload: false,
  },
  {
    kind: "route_mismatch",
    label: "Route mismatch",
    summary:
      "Tamper the routed query after F1 signs the route approval; the live A3 silo responder should refuse with `route_violation`.",
    defaultTarget: "route_approval",
    defaultProfile: "valid_but_malicious",
    defaultInstance: "bank_beta",
    acceptsPayload: false,
  },
  {
    kind: "unsupported_query_shape",
    label: "Unsupported query shape",
    summary:
      "Send a request shape A3 does not accept. Schema gate should refuse before any policy step. P14 lands the live A3 probe adapter.",
    defaultTarget: "bank_beta.A3",
    defaultProfile: "valid_but_malicious",
    defaultInstance: "bank_beta",
    acceptsPayload: true,
    availableAfter: "P14",
  },
  {
    kind: "budget_exhaustion",
    label: "Budget exhaustion",
    summary:
      "Request more rho than the per-requester ledger allows. P7 budget gate should refuse via `BudgetDebit(allowed=false)`.",
    defaultTarget: "dp_ledger",
    defaultProfile: "valid_but_malicious",
    defaultInstance: "bank_beta",
    acceptsPayload: false,
  },
];
