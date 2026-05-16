import type { ComponentId } from "@/api/types";

export type ComponentGuidance = {
  description: string;
  expectedBehavior: string;
  attackSucceedsIf: string;
};

/**
 * Judge-facing correctness hints for inspector drawers. Keep these short:
 * the drawer should explain what state means before it asks viewers to
 * parse fields, but it should not turn into documentation.
 */
export const COMPONENT_GUIDANCE: Record<ComponentId, ComponentGuidance> = {
  A1: {
    description: "A1 watches one bank's activity for suspicious signals and turns them into hash-only alerts. It matters because the investigation can start without exposing customer names or raw accounts.",
    expectedBehavior: "Emits hash-only suspicious-activity candidates and handles obvious policy bypasses deterministically before model use.",
    attackSucceedsIf: "A1 sends raw names, raw accounts, or unfiltered injection text into the model route.",
  },
  A2: {
    description: "A2 is the investigator's outside-TEE agent. It turns a local alert into a narrow federated question so other banks can help without opening their records.",
    expectedBehavior: "Builds hash-only Section 314(b) queries from validated local evidence and respects silo refusals.",
    attackSucceedsIf: "A2 asks for raw data, invents hashes, broadens the purpose, or treats a refusal as a successful answer.",
  },
  F1: {
    description: "F1 is the trusted coordinator inside the federation. It checks who is asking, sends approved questions to the right banks, and combines answers without becoming a raw-data broker.",
    expectedBehavior: "Routes signed, approved requests and aggregates only verified silo responses.",
    attackSucceedsIf: "F1 routes stale, unsigned, replayed, misaddressed, or unapproved requests to a bank silo.",
  },
  "bank_alpha.A3": {
    description: "Bank Alpha A3 is the bank's local responder. It decides whether a federation request is allowed to touch Bank Alpha's aggregate-only data tools.",
    expectedBehavior: "Verifies F1 approval, enforces local policy, and returns only DP-safe aggregate fields.",
    attackSucceedsIf: "Bank Alpha answers without a valid route approval, ignores its local rules, or exposes raw silo records.",
  },
  "bank_beta.A3": {
    description: "Bank Beta A3 is the bank's local responder. It decides whether a federation request is allowed to touch Bank Beta's aggregate-only data tools.",
    expectedBehavior: "Verifies F1 approval, enforces local policy, and returns only DP-safe aggregate fields.",
    attackSucceedsIf: "Bank Beta answers without a valid route approval, ignores its local rules, or exposes raw silo records.",
  },
  "bank_gamma.A3": {
    description: "Bank Gamma A3 is the bank's local responder. It decides whether a federation request is allowed to touch Bank Gamma's aggregate-only data tools.",
    expectedBehavior: "Verifies F1 approval, enforces local policy, and returns only DP-safe aggregate fields.",
    attackSucceedsIf: "Bank Gamma answers without a valid route approval, ignores its local rules, or exposes raw silo records.",
  },
  P7: {
    description: "P7 runs the bank's approved summary queries. It matters because answers are useful counts and patterns, not transaction rows or customer records.",
    expectedBehavior: "Runs approved SQLite aggregate primitives and records rho usage for each privacy-budgeted result.",
    attackSucceedsIf: "P7 returns row-level data, hides a privacy-budget debit, or spends budget without a recorded result.",
  },
  F2: {
    description: "F2 looks for cross-bank laundering patterns. A structuring ring is repeated smaller movement around a group; a layering chain moves value through steps to hide origin.",
    expectedBehavior: "Consumes DP-noised, hash-only bank aggregates and applies deterministic graph rules before model fallback.",
    attackSucceedsIf: "F2 sees raw transactions, accepts invented suspect hashes, or lets the model override deterministic graph evidence.",
  },
  F3: {
    description: "F3 screens investigation entities against sanctions indicators using hashes. It matters because sanctions context can be added without exposing the whole watchlist.",
    expectedBehavior: "Screens hash-only entities against the sanctions watchlist and reports bounded hit flags.",
    attackSucceedsIf: "F3 accepts an unverifiable caller, leaks watchlist internals, or screens raw customer names.",
  },
  F4: {
    description: "F4 turns validated findings into a draft suspicious activity report. It matters because humans get a reviewable compliance artifact instead of a pile of model text.",
    expectedBehavior: "Computes required SAR fields from structured evidence and lets the model write only the bounded narrative.",
    attackSucceedsIf: "F4 invents facts, includes raw customer names, omits Section 314(b), or marks incomplete evidence as complete.",
  },
  F5: {
    description: "F5 reviews the federation's message flow, refusals, privacy budget use, and rate anomalies. It matters because the demo must prove how each answer was allowed.",
    expectedBehavior: "Audits message flow, policy events, budget use, refusals, and rate anomalies.",
    attackSucceedsIf: "F5 misses suspicious rates, loses event ordering, or treats audit gaps as clean state.",
  },
  lobster_trap: {
    description: "Lobster Trap scans text and tool payloads before they reach sensitive model paths. It matters because prompt injection should be visible and blocked, not trusted.",
    expectedBehavior: "Scans model-bound content per instance and blocks or redacts unsafe text before the model sees it.",
    attackSucceedsIf: "Prompt injection, raw private data, or policy-bypass language reaches the model route unflagged.",
  },
  litellm: {
    description: "The model route shows which provider and model a trust domain would call. It matters because judges can see where LLMs are used and where code stays deterministic.",
    expectedBehavior: "Shows provider health, safe I/O preview, model errors, and route state per trust domain.",
    attackSucceedsIf: "Provider errors are hidden, API keys leak, or one global model route silently handles every domain.",
  },
  signing: {
    description: "Signing gives every federated message a cryptographic sender identity. It matters because banks should reject forged coordination requests.",
    expectedBehavior: "Uses the expected public identity and never exposes private signing material.",
    attackSucceedsIf: "Unsigned or forged traffic is accepted, or private signing keys appear in a snapshot.",
  },
  envelope: {
    description: "Envelope verification checks the signed sender, recipient, message body, and freshness. It matters because tampering or stale messages must fail before policy logic runs.",
    expectedBehavior: "Checks body hash, freshness, declared sender, recipient, and signature before route logic runs.",
    attackSucceedsIf: "A tampered, stale, replayed, or misaddressed message reaches the next component.",
  },
  replay: {
    description: "Replay protection remembers valid messages already seen by this trust domain. It matters because copied traffic should not count as a second authorization.",
    expectedBehavior: "Stores redacted nonce hashes and blocks reused valid messages.",
    attackSucceedsIf: "The same signed message is accepted twice or raw nonces leak into the UI.",
  },
  route_approval: {
    description: "Route approval is F1's signed permission slip for a silo request. It binds the exact request body to an allowed route so A3 can reject lookalike requests.",
    expectedBehavior: "Binds request body, purpose, sender, recipient, route kind, and retry count.",
    attackSucceedsIf: "A silo accepts a request body that does not match F1's signed route approval.",
  },
  dp_ledger: {
    description: "The DP ledger tracks how much privacy budget each requester spends. It matters because repeated summary queries can still leak information if they are unlimited.",
    expectedBehavior: "Tracks rho spent by requester, target, primitive, and silo without exposing raw requester secrets.",
    attackSucceedsIf: "Budget goes negative, debits are hidden, or repeated queries avoid the ledger.",
  },
  audit_chain: {
    description: "The audit chain is the durable event history for approvals, refusals, retries, and releases. It matters because the federation needs evidence, not just final answers.",
    expectedBehavior: "Persists ordered, tamper-evident events once P13/P15 lands.",
    attackSucceedsIf: "Approvals, refusals, or releases can be changed or lost without leaving an audit trace.",
  },
};
