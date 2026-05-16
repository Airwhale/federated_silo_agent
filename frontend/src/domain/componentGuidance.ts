import type { ComponentId } from "@/api/types";

export type ComponentGuidance = {
  description: string;
  correct: string;
  incorrect: string;
};

/**
 * Judge-facing correctness hints for inspector drawers. Keep these short:
 * the drawer should explain what state means before it asks viewers to
 * parse fields, but it should not turn into documentation.
 */
export const COMPONENT_GUIDANCE: Record<ComponentId, ComponentGuidance> = {
  A1: {
    description: "A1 watches one bank's activity for suspicious signals and turns them into hash-only alerts. It matters because the investigation can start without exposing customer names or raw accounts.",
    correct: "Emits hash-only suspicious-activity candidates and deterministic bypass decisions.",
    incorrect: "Leaks names/raw accounts or lets obvious bypass prompts reach the model.",
  },
  A2: {
    description: "A2 is the investigator's outside-TEE agent. It turns a local alert into a narrow federated question so other banks can help without opening their records.",
    correct: "Builds hash-only Section 314(b) queries from validated local evidence.",
    incorrect: "Asks for raw data, invents hashes, or ignores silo refusals.",
  },
  F1: {
    description: "F1 is the trusted coordinator inside the federation. It checks who is asking, sends approved questions to the right banks, and combines answers without becoming a raw-data broker.",
    correct: "Routes signed, approved requests and aggregates only verified silo responses.",
    incorrect: "Routes stale, unsigned, replayed, or unapproved requests.",
  },
  "bank_alpha.A3": {
    description: "Bank Alpha A3 is the bank's local responder. It decides whether a federation request is allowed to touch Bank Alpha's aggregate-only data tools.",
    correct: "Verifies F1 approval, enforces local policy, and returns DP-safe fields.",
    incorrect: "Answers without a valid route approval or exposes raw silo records.",
  },
  "bank_beta.A3": {
    description: "Bank Beta A3 is the bank's local responder. It decides whether a federation request is allowed to touch Bank Beta's aggregate-only data tools.",
    correct: "Verifies F1 approval, enforces local policy, and returns DP-safe fields.",
    incorrect: "Answers without a valid route approval or exposes raw silo records.",
  },
  "bank_gamma.A3": {
    description: "Bank Gamma A3 is the bank's local responder. It decides whether a federation request is allowed to touch Bank Gamma's aggregate-only data tools.",
    correct: "Verifies F1 approval, enforces local policy, and returns DP-safe fields.",
    incorrect: "Answers without a valid route approval or exposes raw silo records.",
  },
  P7: {
    description: "P7 runs the bank's approved summary queries. It matters because answers are useful counts and patterns, not transaction rows or customer records.",
    correct: "Runs approved SQLite aggregate primitives and records rho usage.",
    incorrect: "Returns row-level data or spends privacy budget without a recorded result.",
  },
  F2: {
    description: "F2 looks for cross-bank laundering patterns. A structuring ring is repeated smaller movement around a group; a layering chain moves value through steps to hide origin.",
    correct: "Consumes DP-noised bank aggregates and classifies graph patterns with deterministic rules first.",
    incorrect: "Consumes raw transactions or lets an LLM invent suspect hashes.",
  },
  F3: {
    description: "F3 screens investigation entities against sanctions indicators using hashes. It matters because sanctions context can be added without exposing the whole watchlist.",
    correct: "Screens hash-only entities against the sanctions watchlist and reports bounded hits.",
    incorrect: "Accepts unverifiable callers or leaks watchlist internals beyond the answer.",
  },
  F4: {
    description: "F4 turns validated findings into a draft suspicious activity report. It matters because humans get a reviewable compliance artifact instead of a pile of model text.",
    correct: "Drafts a SAR summary from validated evidence and preserves mandatory field provenance.",
    incorrect: "Adds unsupported facts or omits required SAR fields while claiming completion.",
  },
  F5: {
    description: "F5 reviews the federation's message flow, refusals, privacy budget use, and rate anomalies. It matters because the demo must prove how each answer was allowed.",
    correct: "Audits message flow, policy events, budget use, and rate anomalies.",
    incorrect: "Misses refusals, loses event ordering, or treats audit gaps as clean state.",
  },
  lobster_trap: {
    description: "Lobster Trap scans text and tool payloads before they reach sensitive model paths. It matters because prompt injection should be visible and blocked, not trusted.",
    correct: "Scans model-bound content per instance and blocks or redacts unsafe text.",
    incorrect: "Acts as one global switch or silently lets prompt injection pass.",
  },
  litellm: {
    description: "The model route shows which provider and model a trust domain would call. It matters because judges can see where LLMs are used and where code stays deterministic.",
    correct: "Shows the model route, provider health, safe I/O preview, and failures per domain.",
    incorrect: "Hides provider errors or implies one global LLM owns every decision.",
  },
  signing: {
    description: "Signing gives every federated message a cryptographic sender identity. It matters because banks should reject forged coordination requests.",
    correct: "Uses the expected public identity and never exposes private keys.",
    incorrect: "Accepts unsigned traffic or displays signing secrets.",
  },
  envelope: {
    description: "Envelope verification checks the signed sender, recipient, message body, and freshness. It matters because tampering or stale messages must fail before policy logic runs.",
    correct: "Checks body hash, freshness, declared sender, recipient, and signature.",
    incorrect: "Lets tampered, stale, or misaddressed messages through.",
  },
  replay: {
    description: "Replay protection remembers valid messages already seen by this trust domain. It matters because copied traffic should not count as a second authorization.",
    correct: "Stores nonce hashes and blocks reused valid messages.",
    incorrect: "Leaks raw nonces or accepts the same signed message twice.",
  },
  route_approval: {
    description: "Route approval is F1's signed permission slip for a silo request. It binds the exact request body to an allowed route so A3 can reject lookalike requests.",
    correct: "Binds request body, purpose, sender, recipient, route kind, and retry count.",
    incorrect: "Approves a different body than the one sent to a silo.",
  },
  dp_ledger: {
    description: "The DP ledger tracks how much privacy budget each requester spends. It matters because repeated summary queries can still leak information if they are unlimited.",
    correct: "Tracks rho spent by requester, target, primitive, and silo.",
    incorrect: "Lets budget go negative or hides spending behind aggregate totals.",
  },
  audit_chain: {
    description: "The audit chain is the durable event history for approvals, refusals, retries, and releases. It matters because the federation needs evidence, not just final answers.",
    correct: "Will persist ordered, tamper-evident events once P13/P15 lands.",
    incorrect: "Claims a durable audit chain when only UI timeline events exist.",
  },
};
