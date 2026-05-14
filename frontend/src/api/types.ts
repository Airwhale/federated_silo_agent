/**
 * Hand-curated convenience types that mirror the P9a Pydantic snapshot models
 * in `backend/ui/snapshots.py`. These wrap the generated OpenAPI schema
 * (`schema.ts`, produced by `npm run gen:api`) with clean import paths so
 * components can `import type { SessionSnapshot } from "@/api/types"` instead
 * of digging into `paths[...]["responses"][...]["content"]`.
 *
 * If a Pydantic field changes on the backend, regenerate `schema.ts` and then
 * fix any type errors that surface here — `tsc` keeps the two aligned.
 */

// ---------------------------------------------------------------------------
// Enum string-literal unions (mirror StrEnum values from `backend/ui/snapshots.py`).
// ---------------------------------------------------------------------------

export type SnapshotStatus =
  | "live"
  | "blocked"
  | "not_built"
  | "pending"
  | "simulated"
  | "error";

export type ComponentId =
  | "A1"
  | "A2"
  | "F1"
  | "bank_alpha.A3"
  | "bank_beta.A3"
  | "bank_gamma.A3"
  | "P7"
  | "F2"
  | "F3"
  | "F4"
  | "F5"
  | "lobster_trap"
  | "litellm"
  | "signing"
  | "envelope"
  | "replay"
  | "route_approval"
  | "dp_ledger"
  | "audit_chain";

export type SecurityLayer =
  | "schema"
  | "signature"
  | "allowlist"
  | "freshness"
  | "replay"
  | "route_approval"
  | "lobster_trap"
  | "a3_policy"
  | "p7_budget"
  | "not_built"
  | "accepted"
  | "internal_error";

export type ProbeKind =
  | "prompt_injection"
  | "unsigned_message"
  | "body_tamper"
  | "wrong_role"
  | "replay_nonce"
  | "route_mismatch"
  | "unsupported_query_shape"
  | "budget_exhaustion";

export type AttackerProfile = "unknown" | "wrong_role" | "valid_but_malicious";

export type SessionMode = "stub" | "live" | "live_with_stub_fallback";

export type SignatureStatus = "valid" | "invalid" | "missing" | "not_checked";
export type FreshnessStatus = "fresh" | "expired" | "not_checked";
export type BindingStatus = "matched" | "mismatched" | "not_checked";

export type BankId = "bank_alpha" | "bank_beta" | "bank_gamma" | "federation";
export type RouteKind = "peer_314b" | "local_contribution";

// ---------------------------------------------------------------------------
// Nested snapshot types.
// ---------------------------------------------------------------------------

export interface SnapshotField {
  name: string;
  value: string;
  redacted?: boolean;
}

export interface ComponentReadinessSnapshot {
  component_id: ComponentId;
  label: string;
  status: SnapshotStatus;
  available_after: string | null;
  detail: string;
}

export interface SigningStateSnapshot {
  status: SnapshotStatus;
  known_signing_key_ids: string[];
  private_key_material_exposed: false;
  last_verified_key_id: string | null;
  detail: string;
}

export interface EnvelopeVerificationSnapshot {
  status: SnapshotStatus;
  message_type: string | null;
  sender_agent_id: string | null;
  recipient_agent_id: string | null;
  body_hash: string | null;
  signature_status: SignatureStatus;
  freshness_status: FreshnessStatus;
  blocked_by: SecurityLayer | null;
  detail: string;
}

export interface RouteApprovalSnapshot {
  status: SnapshotStatus;
  query_id: string | null;
  route_kind: RouteKind | null;
  approved_query_body_hash: string | null;
  computed_query_body_hash: string | null;
  requester_bank_id: BankId | null;
  responder_bank_id: BankId | null;
  binding_status: BindingStatus;
  detail: string;
}

export interface DpLedgerEntrySnapshot {
  requester_key: string;
  responding_bank_id: BankId;
  rho_spent: number;
  rho_remaining: number;
  rho_max: number;
}

export interface DpLedgerSnapshot {
  status: SnapshotStatus;
  entries: DpLedgerEntrySnapshot[];
  detail: string;
}

export interface ProviderHealthSnapshot {
  status: SnapshotStatus;
  lobster_trap_configured: boolean;
  litellm_configured: boolean;
  gemini_api_key_present: boolean;
  openrouter_api_key_present: boolean;
  secret_values: "redacted";
  detail: string;
}

export interface AuditChainSnapshot {
  status: SnapshotStatus;
  event_count: number;
  latest_event_hash: string | null;
  detail: string;
}

export interface ReplayCacheEntrySnapshot {
  principal_id: string;
  nonce_hash: string;
  first_seen_at: string;
  expires_at: string;
}

export interface ReplayCacheSnapshot {
  entries: ReplayCacheEntrySnapshot[];
}

export interface ComponentSnapshot {
  component_id: ComponentId;
  status: SnapshotStatus;
  title: string;
  fields: SnapshotField[];
  signing: SigningStateSnapshot | null;
  envelope: EnvelopeVerificationSnapshot | null;
  replay: ReplayCacheSnapshot | null;
  route_approval: RouteApprovalSnapshot | null;
  dp_ledger: DpLedgerSnapshot | null;
  provider_health: ProviderHealthSnapshot | null;
  audit_chain: AuditChainSnapshot | null;
}

export interface TimelineEventSnapshot {
  event_id: string;
  timestamp: string;
  component_id: ComponentId;
  title: string;
  detail: string;
  status: SnapshotStatus;
  blocked_by: SecurityLayer | null;
}

// ---------------------------------------------------------------------------
// Top-level API request / response shapes.
// ---------------------------------------------------------------------------

export interface HealthSnapshot {
  status: "ok";
}

export interface SystemSnapshot {
  status: SnapshotStatus;
  components: ComponentReadinessSnapshot[];
  provider_health: ProviderHealthSnapshot;
  detail: string;
}

export interface SessionCreateRequest {
  scenario_id?: string;
  mode?: SessionMode;
}

export interface SessionSnapshot {
  session_id: string;
  scenario_id: string;
  mode: SessionMode;
  phase: string;
  created_at: string;
  updated_at: string;
  components: ComponentReadinessSnapshot[];
  latest_events: TimelineEventSnapshot[];
}

export interface ProbeRequest {
  probe_kind: ProbeKind;
  target_component: ComponentId;
  attacker_profile?: AttackerProfile;
  payload_text?: string | null;
}

export interface ProbeResult {
  probe_id: string;
  probe_kind: ProbeKind;
  target_component: ComponentId;
  attacker_profile: AttackerProfile;
  accepted: boolean;
  blocked_by: SecurityLayer;
  reason: string;
  envelope: EnvelopeVerificationSnapshot | null;
  replay: ReplayCacheSnapshot | null;
  route_approval: RouteApprovalSnapshot | null;
  dp_ledger: DpLedgerSnapshot | null;
  timeline_event: TimelineEventSnapshot;
}
