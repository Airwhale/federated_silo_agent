# Federated Cross-Bank AML Multi-Agent System — Product Design Doc

> *This document follows a standard product spec structure. **Discovery** sections (Problem, Users, Market) establish what's true about the world. **Define** sections (Goals, Principles) commit to what we're optimizing. **Design** sections (Solution, UX, System) commit to how. **Build / Validate / Launch** sections turn the design into action. **Risks** and **Open Questions** are honest about what we don't yet know.*
>
> *This project pivoted from a clinical federated-stats design (Synthea-OMOP, CHF cohort) to cross-bank AML mid-build. The pivot plan and reasoning are preserved in [`.claude/plans/hi-i-would-like-replicated-pelican.md`](../.claude/plans/) and the clinical plan in [`docs/clinical-archive/plan.md`](docs/clinical-archive/plan.md). The pivot was motivated by the AI-hackathon framing: AML is natively multi-agent while clinical federated stats was structurally single-agent.*

---

## 0. TL;DR

A multi-agent cross-bank Anti-Money-Laundering investigation system. Three synthetic banks each run a transaction-monitoring agent, an outside-TEE investigator agent, and an inside-bank trusted silo responder agent. When suspicious activity surfaces at one bank, the investigator coordinates through a federation layer in an assumed TEE. Peer-bank evidence is answered by each bank's silo responder inside that bank's trusted boundary, using deterministic stats primitives rather than exposing raw data to the outside investigator. Specialist agents (graph analyst, sanctions screener, SAR drafter, compliance auditor) compose investigations across the network. **Every cross-bank conversation is governed by Lobster Trap plus an AML policy adapter; aggregate transaction patterns are shared under differential privacy; no raw customer identifiers or raw transactions cross bank boundaries.**

Pitch comp: **Verafin → Nasdaq $2.75B (2020)** for the non-private version of exactly this.

Demo target: a 3-minute live walkthrough in which a sub-threshold structuring ring spanning all three banks gets detected through federated agent coordination that no single bank could have surfaced alone. Submission: TechEx AI hackathon, May 19, 2026.

---

## 1. Problem & Opportunity *(Discovery)*

### 1.1 The pain

Banks see only their own customers' transactions. Money launderers exploit this gap by structuring activity across multiple institutions to stay under each bank's individual monitoring thresholds. The most common typologies:

- **Structuring (smurfing):** sub-$10K cash deposits or transfers split across banks to evade Currency Transaction Reports.
- **Layering:** rapid transfers through multiple accounts at multiple institutions to obscure money trails.
- **Integration:** depositing structured funds into legitimate-looking accounts via cross-bank channels.

The 2001 USA PATRIOT Act §314(b) explicitly authorizes financial institutions to share information about suspected money laundering and terrorist financing. The statute has been law for 25 years. Banks barely use it. Four frictions, ordered by how much they actually prevent routine §314(b) use:

1. **Legal risk aversion.** General counsels treat §314(b) as a last resort because every disclosure carries a small but nonzero risk of customer-side challenge. §314(b) outreach happens by formal letter, takes weeks, and is reserved for the clearest cases.
2. **No shared infrastructure.** Each bank would have to build its own outbound + inbound process; the fixed cost dominates the marginal case.
3. **Competitive trust.** Banks compete. Sharing customer-relevant signal with a peer — even under §314(b) — creates business-side worry ("what if they use this disclosure to poach the customer?").
4. **No standardized vocabulary.** Each bank has its own alert types, thresholds, data models; there's no common ontology for cross-bank queries.

This system addresses (2), (3), and (4) — shared infrastructure, technical (not contractual) privacy guarantees, a query-primitive ontology. It does **not** address (1). We lower the technical cost; the institutional cost remains. A regulator or consortium operator would still need to push through the legal posture.

Result: cross-institution money laundering is among the most undetected forms of financial crime. FinCEN's most-wanted typologies almost all span multiple banks; banks individually flag tens of thousands of false positives while the actual ring-level activity stays invisible.

### 1.2 What's changed (why now)

- **AI/LLM-powered investigation has become standard** at top-tier banks (Citi, JPM, HSBC publicly describe using LLMs for AML triage).
- **Privacy-preserving computation** (DP, MPC, federated learning) has matured to the point where it can be productized.
- **Regulators have softened** on the safe-harbor question — FinCEN and OCC have published guidance encouraging §314(b) usage with appropriate controls.
- **Veea's Lobster Trap** provides an open-source LLM-policy substrate that banks could plausibly adopt without vendor lock-in.

### 1.3 Demo opportunity (hackathon-specific)

TechEx AI hackathon, submission May 19, 2026. Primary track: **Track 4 (Data & Intelligence)**. Partner-award alignment: **Gemini** powers all agents (Google partner award); **Lobster Trap** is the policy substrate (Veea partner award). The multi-agent architecture also positions us for any agent-orchestration awards if those exist.

---

## 2. Users & Jobs-to-be-Done *(Define)*

### 2.1 Primary personas

**P1: AML investigator at a participating bank.** BSA/AML-certified specialist; has a docket of alerts to clear daily; spends most of their time on false positives. Pain point: when they see a suspicious pattern that hints at cross-bank activity, they have no good way to investigate it because §314(b) outreach is bureaucratic and slow. *Job-to-be-done:* "When I have a suspicious entity at my bank, I want to know in minutes whether peer institutions have related signals — without exposing my customer's identity unless we both find each other's leads credible enough to escalate."

**P2: BSA Officer / Chief Compliance Officer.** Accountable for the bank's overall AML compliance posture; signs off on SARs; faces personal liability if AML controls are inadequate. *Job-to-be-done:* "When my investigators escalate cross-bank cases, I want to be confident that every information disclosure was within §314(b) bounds, fully audited, and would withstand a regulator's review of the audit trail."

### 2.2 Secondary personas (slide deck only)

- FinCEN analyst doing pattern surveillance across the financial system
- Independent AML consortium operator (e.g., what Verafin built for credit unions)
- Regulators (OCC, FDIC, FRB) running supervisory data calls

### 2.3 Anti-personas

- Banks wanting full customer-data sharing (out of scope; defeats the privacy purpose)
- Single-bank AML use cases (single-bank tooling is a different product)
- Real-time payment authorization (we're investigative, not authorization-time)

---

## 3. Market Context *(Discovery)*

### 3.1 Comparable willingness-to-pay

| Market | Annual scale | Demonstrated WTP signal |
|---|---|---|
| Global AML compliance software | ~$3B | NICE Actimize, SAS, Oracle, FICO, ComplyAdvantage |
| US bank compliance staffing | ~$50B / year | Industry estimate |
| Cross-institution AML federation | Effectively zero today | **Verafin → Nasdaq $2.75B (2020)** for the credit-union-focused non-private version |
| Recent AML platform exits / valuations | $0.7–1B+ | Quantexa $1B+, ComplyAdvantage ~$760M, Hawk AI raised, Symphony AyasdiAI acquired |

Total addressable: ~$1–3B / year for federation + AI tooling in the US large-bank market. Verafin's $2.75B exit is the bullseye comparable.

### 3.2 Why cross-bank AML is the right vertical for an AI hackathon

| Criterion | Score |
|---|---|
| Natively multi-agent workflow (real banks have distinct specialist roles) | **High** |
| Federation story is structurally necessary (banks legally can't share raw customer data) | **High** |
| Regulatory framing creates a clear legal pocket (§314(b)) | High |
| Buyer math literacy | Medium (BSA officers + investigators) |
| Synthetic data feasibility | Medium-high (typologies are well-documented) |
| Lobster Trap value is sharper than HIPAA framing | High |

---

## 4. Goals & Non-goals *(Define)*

### 4.1 Goals

1. Demonstrate **8 agent roles across 14 running agent instances** talking to each other across enforced trust boundaries.
2. Demonstrate **federated detection of a planted cross-bank ring** that no single bank could surface alone.
3. Demonstrate **Lobster Trap plus AML policy policing every cross-bank message** (no customer names leaking, sanctions hits not exposing list details, audit trail complete).
4. Demonstrate **layered silo privacy**: (a) hash-based cross-bank entity linkage as the primary mechanism, (b) a deterministic stats-primitives layer in each bank enforcing data-plane isolation, (c) differential privacy applied to aggregate-count primitives via one explicit accounting policy in P7. DP is scoped where it earns its keep (aggregate counts and histograms); binary presence queries rely on hash linkage instead.
5. Win or place at TechEx (Track 4 + Gemini partner award + Veea partner award).

### 4.2 Non-goals

1. **Production-grade AML detection.** The patterns are demoable, not state-of-the-art.
2. **Real banking regulatory certification.** We claim §314(b) authorization framing, not actual approval from a regulator.
3. **Heavy graph-ML.** Federated graph analytics is a research area; we'll do aggregate-graph-statistics, not deep GNN inference.
4. **Real-time / streaming.** Batch query model only.
5. **Sanctions list maintenance.** We use a small mock list with publicly-known typologies; not a real OFAC integration.

### 4.3 Success metrics

- All 14 running agent instances wired and exchanging structured messages through the LT proxy
- A live demo successfully detects the planted ring within 3 minutes
- Every cross-bank message passes through the AML policy adapter and LT inspection path, then lands in the audit log
- Single-bank investigation of the same ring fails (the federation is what makes detection possible)
- Submission complete by May 19 with README + pitch deck + screencast

---

## 5. Solution Thesis *(Ideate → Design)*

Three banks each run three persistent agents: A1 transaction monitoring, A2 outside-TEE investigator, and A3 inside-bank silo responder. A central federation layer in an assumed TEE hosts five cross-cutting specialist agents: F1 coordinator, F2 graph analyst, F3 sanctions screener, F4 SAR drafter, and F5 compliance auditor. Six layered privacy and security mechanisms, in rough order of how much privacy work each does:

- **Hash-based cross-bank entity linkage.** Banks share stable `name_hash` tokens, never customer identifiers. This is the primary privacy mechanism — it's what makes the federation work at all. Same input, same hash, everywhere; different banks holding accounts for the same shell entity can correlate without disclosing identity.
- **Bank-local stats-primitives layer.** A deterministic, non-LLM module in each bank that exposes a fixed set of declared query shapes over local data (e.g., `count_entities_by_name_hash`, `alert_count_for_entity`, `flow_histogram`). Every cross-bank-bound numeric value traces to a primitive call with recorded provenance. The LLM has no syscall to raw transactions on the cross-bank-response path; data-plane isolation is structural, not policy-based. This is the structural enforcement of design principle #6 ("agents reason about signals, not transactions").
- **Lobster Trap plus AML policy adapter on NL channels.** Lobster Trap provides generic prompt inspection, blocking, response metadata, and audit logging. Our Python AML policy adapter enforces the domain-specific rules that the current LT policy language does not natively express: customer-name redaction, role-based routing (A1 can only send local alerts to A2; A2 can request cross-bank coordination only through F1; F1 can route approved queries to peer A3 responders; A3 can only answer F1), purpose-declaration checks on every §314(b) query, and normalized audit-event emission on every cross-bank message.
- **Schema validation.** Only pre-declared message shapes leave a bank; the schema is the trust contract.
- **Message security envelope.** Assume a possible man-in-the-middle on inter-agent network paths. Cross-boundary messages are carried in signed envelopes with canonical body hashes, request/response binding, freshness checks, replay protection, and audit hash-chain links. Lobster Trap governs content; the envelope governs identity and tamper evidence.
- **Differential privacy on aggregate-count primitives.** Gaussian mechanism with σ calibrated from one explicit privacy ledger; per-(investigator, peer-bank) budget tracked consistently inside P7; the channel refuses when the budget is exhausted. Applied where it earns its keep (alert counts, flow histograms, F2 input aggregates) — not applied to binary presence queries where noise would eat the signal (those rely on hash linkage instead). DP's specific job here is bounding sustained insider-abuse leakage in aggregate activity queries, not claiming perfect anonymity for entity-presence lookups.

Honest note on what DP doesn't do: it doesn't protect entity-presence binary queries (sensitivity-1 question with magnitude-1 answer means noise eats the signal); it isn't the protagonist of the headline demo (the protagonist is the cross-bank graph cycle that no single bank can see); it isn't what Verafin uses (Verafin's privacy model is contractual). DP earns its keep against a specific threat — multi-query inference about aggregate activity — and that's the role it plays here.

---

## 6. Design Principles *(Define)*

1. **Privacy-by-default.** No raw transactions leave a bank. Schema validation enforces this structurally.
2. **§314(b)-shaped disclosure rules.** Cross-bank information sharing is allowed for suspected ML/TF only; the AML policy adapter enforces declared-purpose checks and LT logs the decision path.
3. **Honest about guarantees.** The federation provides bounded leakage and full audit; it does not provide perfect anonymity (a determined adversary could potentially infer individual customers from many queries; DP budget bounds this).
4. **Agent roles are typed and enforced.** Each agent has a declared role; the message envelope and AML adapter enforce what messages each role can send and receive.
5. **Audit is product.** Every cross-bank message lands in a structured, regulator-readable audit log. SAR drafts are auditable down to which agent contributed which finding.
6. **No outside-TEE LLM in the transaction data plane.** Agents reason about *signals*, not *transactions*. A1 can read local signals for monitoring. A3 can invoke deterministic P7 stats primitives inside the bank trusted boundary to answer approved peer queries. A2 has no raw DB or P7 handle.
7. **Assume hostile transit.** Network routing is not trusted. Cross-boundary messages require service identity, signatures, freshness, request/response binding, replay protection, and tamper-evident audit logs.
8. **Reproducibility.** Deterministic seeds in synthetic data + structured agent message schemas = bit-equivalent reruns for the canonical demo.

---

## 7. User Experience Design *(Design)*

### 7.1 Primary flow

1. AML analyst opens the investigation console.
2. A1 (transaction-monitoring agent) at their bank shows recent alerts.
3. Analyst selects an alert; A2 (investigator) takes it from there.
4. A2 reasons about the alert; if it has cross-bank signal, A2 asks the federation coordinator (F1) to query peer banks.
5. F1 routes anonymized queries to peer banks' A3 silo responders through Lobster Trap.
6. Peer A3 agents independently re-check role, purpose, query shape, DP budget, and primitive allowlist. They respond with anonymized signals from inside their bank trusted boundary, or return a structured refusal.
7. F2 (graph analyst) assembles cross-bank pattern; F3 (sanctions) screens entities.
8. F4 drafts a SAR; F5 audits the entire conversation; analyst signs off.

### 7.2 Key UI surfaces

| Surface | What it shows | Why it matters |
|---|---|---|
| Bank investigator console | A1 alerts, A2 reasoning, cross-bank query status, manual "ask A2" action | Primary operational surface |
| Federation timeline | Live agent-to-agent conversation with LT verdicts overlaid, plus step/run controls | The multi-agent demo's signature visual |
| Silo inspector | Per-bank A3 inbox, route approvals, P7 primitive calls, privacy budget, and returned fields | Shows that each silo owns its own data-plane enforcement |
| Policy and attack lab | Prompt injection, customer-name leakage, MITM body tamper, replay, route mismatch, and budget-exhaustion attempts | Lets judges probe the security claims directly |
| Audit panel | Every LT decision, every DP debit, every schema violation, every route approval, and hash-chain status | The compliance dashboard |
| SAR draft viewer | Structured form + attributed contributions | Regulatory artifact |

The UI is an interactive control surface over the full stack, not just a playback view. A judge should be able to click into any component and see what it knew, what it was allowed to call, what message it received, what it emitted, and which policy or schema gate approved or blocked the action. Inspection does not grant extra privileges: attempts launched from the UI still pass through the same signed-envelope, policy, Lobster Trap, schema, A3, and P7 checks as normal traffic.

Minimum judge controls:

1. Start or reset a canonical scenario.
2. Step one mechanism at a time, or run until the next terminal artifact.
3. Open any agent turn and inspect prompt metadata, typed input, typed output, constraint results, and audit events.
4. Open any trust-domain node and inspect local LT/LiteLLM configuration, inboxes, route approvals, replay-cache status, and audit forwarding.
5. Open any bank silo and inspect A3 decisions, P7 primitive invocations, args hashes, rho debit, remaining budget, and refusal paths.
6. Launch safe negative probes: prompt injection, raw-name leakage, hallucinated hashes, MITM body tamper, replay, route mismatch, unsupported query shape, and budget exhaustion.
7. Export the run timeline, final SAR draft, and audit JSONL for judging or screencast backup.

### 7.3 Demo experience design

The demo is a 3-minute four-beat run:

1. **Setup (20s)** — three banks, 14 running agent instances, federation layer. Show audit panel cleared. Show the planted ring exists in pooled data (central analysis sees it).
2. **Single-bank attempt (40s)** — Bank Alpha's A1 flags suspicious activity. A2 investigates internally. Shows the alert is just below threshold; single-bank context can't escalate. *"This is what happens today."*
3. **Federation moment (90s)** — A2 declares §314(b) suspicion → F1 broadcasts anonymized query → peer A3 responders validate and answer through P7 → F2 assembles ring → F3 screens sanctions → F4 drafts SAR. Audit panel lights up at each step. *"This is what federation makes possible."*
4. **Close (10s)** — Verafin comp slide. Track 4 + Gemini award + Veea award framing.

---

## 8. System Design *(Design)*

### 8.1 Architecture

```
        ┌──────────────────────────────┐
        │  Analyst Console (Browser)   │
        │  Alerts • Federation         │
        │  Timeline • Audit Panel      │
        └──────────────┬───────────────┘
                       │ HTTPS / SSE
                       ▼
   ╔════════════════════════════════════════════╗
   ║      Federation Layer (assumed TEE)         ║
   ║   ┌──────────────────────────────────────┐  ║
   ║   │ F1 Cross-bank coordinator agent      │  ║
   ║   │ F2 Graph-analysis agent              │  ║
   ║   │ F3 Sanctions / PEP screening agent   │  ║
   ║   │ F4 SAR drafter agent                 │  ║
   ║   │ F5 Compliance auditor agent          │  ║
   ║   └────────────┬─────────────────────────┘  ║
   ║                ▼                            ║
   ║   ┌──────────────────────────────────────┐  ║
   ║   │ Lobster Trap → LiteLLM → Gemini      │  ║
   ║   └────────────┬─────────────────────────┘  ║
   ╚════════════════│════════════════════════════╝
                    │ structured messages
       ┌────────────┼────────────┐
       ▼            ▼            ▼
   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
   │  Bank α      │ │  Bank β      │ │  Bank γ      │
   │ A1 + A2 + A3 │ │ A1 + A2 + A3 │ │ A1 + A2 + A3 │
   │  (Gemini)    │ │  (Gemini)    │ │  (Gemini)    │
   │     ↕        │ │     ↕        │ │     ↕        │
   │  Stats       │ │  Stats       │ │  Stats       │
   │  primitives  │ │  primitives  │ │  primitives  │
   │  (DP + rho   │ │  (DP + rho   │ │  (DP + rho   │
   │   budget)    │ │   budget)    │ │   budget)    │
   │     ↕        │ │     ↕        │ │     ↕        │
   │  SQLite      │ │  SQLite      │ │  SQLite      │
   └──────────────┘ └──────────────┘ └──────────────┘
```

The diagram above is logical. For the cloud demo, do not read the single Lobster Trap/LiteLLM box as a shared central gateway. The deployment model below is the target: each trust domain owns its own policy, LLM-egress, signature, replay, and audit-forwarding stack.

Demo deployment topology, with explicit silos:

| Trust domain / node | Runs locally in that node | Does not run there |
|---|---|---|
| Bank Alpha silo node | `A3-alpha`, P7 stats primitives, `bank_alpha.db`, local Lobster Trap, local LiteLLM, local AML policy adapter, envelope signer/verifier, replay cache, audit forwarder | `F1-F5`, peer-bank data, outside-bank A2 |
| Bank Beta silo node | `A3-beta`, P7 stats primitives, `bank_beta.db`, local Lobster Trap, local LiteLLM, local AML policy adapter, envelope signer/verifier, replay cache, audit forwarder | `F1-F5`, peer-bank data, outside-bank A2 |
| Bank Gamma silo node | `A3-gamma`, P7 stats primitives, `bank_gamma.db`, local Lobster Trap, local LiteLLM, local AML policy adapter, envelope signer/verifier, replay cache, audit forwarder | `F1-F5`, peer-bank data, outside-bank A2 |
| Investigator nodes | One A2 per participating bank, local Lobster Trap, local LiteLLM, local AML policy adapter, envelope signer/verifier, replay cache | P7, raw bank databases, peer A3 responders |
| Federation node | F1-F5, federation Lobster Trap, federation LiteLLM, federation AML policy adapter, route-approval signer, aggregate audit stream, replay cache | Bank-local raw databases, P7 direct DB handles |

F1 is separate from every bank silo. It can be co-deployed with F2-F5 in the federation trust domain, but it is not part of any bank's silo stack. Each silo owns its own policy, LLM-egress, signature, replay, and data-access controls; F1 approval is necessary for a silo query, but A3 still independently decides whether the silo can answer.

Three wire paths inside each bank:

- **Per-domain LLM wire path:** `agent → local Lobster Trap → local LiteLLM → Gemini API`. Each trust domain has its own LT/LiteLLM stack; each running instance is identified by an agent_id and role in the LT request metadata.
- **Local monitoring data path:** `A1 → SQLite`. A1 reads local signals only to raise alerts for its own bank.
- **Cross-bank response data path:** `A3 → stats-primitives layer → SQLite`. Deterministic, non-LLM, raw-SQL inside the bank trusted boundary. The stats layer is the only component allowed to read raw transactions in service of a cross-bank response; A2 has no DB or P7 handle. Every cross-bank-response numeric value in a `Sec314bResponse` traces to a primitive call with a recorded privacy-budget debit (zero for non-DP primitives).

### 8.2 Message flow (canonical demo case)

```
[t=0] Bank α's A1 flags suspicious sub-$10K transfer pattern → alert to Bank α's A2
[t=1] Bank α's A2 evaluates alert; declares §314(b) suspicion; queries F1
       (AML adapter verifies §314(b) purpose declaration; LT inspects and logs)
[t=2] F1 broadcasts anonymized signal pattern to Banks β and γ A3 silo responders
       (AML policy adapter redacts customer names; LT logs and inspects the outbound query)
[t=3] Banks β and γ's A3 agents each respond with anonymized signals (matches found)
       (response schema and AML adapter enforce no raw transactions; LT inspects and logs)
[t=4] F1 forwards aggregated signals to F2 (graph analyst) for ring inference
[t=5] F2 returns: "high probability cross-bank structuring ring spanning 3 nodes"
[t=6] Investigators submit anonymized entity hashes to F3 (sanctions)
[t=7] F3 returns: "no direct sanctions match; one entity has PEP relation"
[t=8] Bank α's A2 synthesizes findings + invokes F4 to draft SAR
[t=9] F4 emits SAR draft with proper attribution to each bank's contribution
[t=10] F5 audits the full conversation; confirms §314(b) compliance; surfaces audit summary
```

Every NL arrow passes through Lobster Trap and the AML adapter. Every message is logged in the audit channel.
Every cross-boundary message is also assumed to need the security envelope from Section 8.5: authenticated transport, signed canonical payloads, freshness checks, request/response binding, replay protection, and audit hash-chain linkage.

### 8.3 Agent roles and instances

There are **8 agent roles** and **14 running instances**: three A1 monitors, three A2 investigators, three A3 silo responders, and one each of F1 through F5. A2 is the human-facing investigator outside the TEE. A3 is the bank-boundary responder inside each bank's trusted/TEE boundary. All roles are Gemini-backed LLM agents that reason about their inputs and decide what to output. Each agent's reasoning is wrapped in deterministic rule checks of two kinds:

- **Rule constraints** — hard checks that the LLM cannot override. If a constraint is violated, the agent refuses; the LLM doesn't get to argue.
- **Rule bypasses** — hard checks that override the LLM. Certain conditions force a specific output regardless of what the LLM would have said. The catalog below is the source of truth for trigger and action semantics.

This pattern mirrors how real bank investigators work: they exercise professional judgment, constrained by hard compliance rules, and occasionally overridden by mandatory reporting requirements. Encoding the same shape in the agent runtime gives the demo two valuable properties: (1) the LLMs have real agency on the gray-area decisions, (2) the demo is robust to LLM drift on the black-and-white ones.

#### Bypass rule catalog

These are the canonical bypass rules. Agent and phase sections below reference these IDs instead of restating the trigger logic. Do not define bypass triggers or forced outputs anywhere else in the plan.

| Rule ID | Agent | Trigger | Forced output or action | Build phase | Expected tests |
|---|---|---|---|---|---|
| A1-B1 | A1 | Transaction amount `>= 10000` | Emit a `Currency Transaction Report` alert to local A2 | P6 | `tests/test_a1.py` |
| A1-B2 | A1 | Counterparty hash matches a known SDN entry | Emit a `Sanctions Match` alert to local A2 | P6 | `tests/test_a1.py` |
| A1-B3 | A1 | At least 10 near-CTR transactions on one account within 24 hours | Emit a high-severity `Velocity Spike` alert to local A2 | P6 | `tests/test_a1.py` |
| A2-B1 | A2 | At least 3 correlated alerts on the same `name_hash` within 30 days | Send a `Sec314bQuery` to F1 | P8 | `tests/test_a2.py` |
| A2-B2 | A2 | Alert is tied to a known SDN match | Emit a deterministic `SARContribution` directly; later F3 evidence may supersede this path | P8 | `tests/test_a2.py` |
| A3-B1 | A3 | Missing or invalid `PurposeDeclaration` | Return a deterministic refusal before any P7 primitive or Gemini call | P8a | `tests/test_a3.py` |
| A3-B2 | A3 | Invalid signature, expired envelope, replayed nonce, missing route approval, or mismatched route approval | Return a deterministic security/routing refusal before any P7 primitive or Gemini call | P8a, P14 | `tests/test_a3.py`, `tests/test_aml_policy.py` |
| A3-B3 | A3 | P7 privacy budget is exhausted | Return `Sec314bResponse` with `refusal_reason="budget_exhausted"`, empty fields, and empty provenance; skip Gemini | P8a, P7 | `tests/test_a3.py`, `tests/test_budget.py` |
| F1-B1 | F1 | Missing or empty `PurposeDeclaration.suspicion_rationale` | Refuse the query before any LLM call | P9 | `tests/test_f1.py` |
| F1-B2 | F1 | Requester quota exceeded, such as more than 20 queries in 1 hour | Escalate to F5 for compliance review | P9, P14 | `tests/test_f1.py`, `tests/test_aml_policy.py` |
| F1-B3 | F1 | Query references a known SDN entity hash | Route through F3 in parallel | P9 | `tests/test_f1.py` |
| F2-B1 | F2 | Closed cycle with at least 3 entity hashes spanning at least 3 banks with elevated edge counts | Return `pattern_class="structuring_ring"` with `confidence >= 0.85` | P11 | `tests/test_f2.py` |
| F2-B2 | F2 | Fee-shaped layering chain with at least 4 hops and 2 to 5 percent attenuation per hop | Return `pattern_class="layering_chain"` with `confidence >= 0.85` | P11 | `tests/test_f2.py` |
| F3-B1 | F3 | Exact `name_hash` equality with an SDN entry | Set `sdn_match=True` | P10 | `tests/test_f3.py` |
| F3-B2 | F3 | Exact `name_hash` equality with the S1-D PEP entity | Set `pep_relation=True` | P10 | `tests/test_f3.py` |
| F4-B1 | F4 | Any contributor evidence references an SDN sanctions match or PEP relation | Set `sar_priority="high"` | P12 | `tests/test_f4.py` |
| F4-B2 | F4 | Input is missing data needed for a mandatory SAR field | Emit `SARContributionRequest` instead of an incomplete `SARDraft` | P12 | `tests/test_f4.py` |
| F5-B1 | F5 | More than 10 `Sec314bQuery` events from one investigator in 60 minutes | Emit a `rate_limit` `AuditEvent` | P13 | `tests/test_f5.py` |
| F5-B2 | F5 | `PurposeDeclaration.suspicion_rationale` lacks ML/TF keywords | Emit a `human_review` `AuditEvent` | P13 | `tests/test_f5.py` |

#### Bank-local and silo-boundary agents (×3 banks)

**Agent A1: Transaction-monitoring agent** (one per bank, identical role)

- **Role:** Reviews batches of suspicious-signal candidates from the bank's own transaction stream. Decides which to escalate to A2 as named alerts, what severity to assign, what rationale to attach.
- **Inputs:** Local `suspicious_signals` + correlating transaction rows
- **Outputs:** `Alert` messages to local A2
- **Reasoning:** Gemini call with structured output (JSON schema producing `Alert` records). The LLM sees the transaction context, customer KYC tier, channel, recent activity history. It can suppress noisy signals it judges to be legitimate business (most are) and elevate ones that pattern-match real concerns.
- **Rule constraints (LLM cannot override):**
  - Cannot emit any message addressed to anything other than local A2 (cross-bank channels are LT-blocked for A1 role)
  - Cannot modify transaction or signal data
  - Cannot suppress a signal that meets a hard-required criterion (`A1-B1` through `A1-B3`)
- **Rule bypasses:** `A1-B1` through `A1-B3` in the bypass rule catalog.

**Agent A2: Investigator agent** (one per bank, identical role; outside TEE; the protagonist)

- **Role:** Receives alerts from local A1. Decides whether to investigate, dismiss, or escalate cross-bank. When cross-bank, drafts §314(b) queries; receives peer-bank responses from F1; synthesizes investigation findings; recommends SAR / dismiss to F4 / F5. A2 does not answer peer queries and does not hold a raw DB or P7 stats-primitives handle.
- **Inputs:** `Alert` from local A1; aggregated `Sec314bResponse` from F1
- **Outputs:** `Sec314bQuery` to F1 (outbound to peers); `SARContribution` to F4; `DismissalRationale` to F5
- **Reasoning:** Gemini call. A2 reasons about alert credibility from the alert context it receives, decides what cross-bank signals would be informative, drafts queries that comply with §314(b) purpose declarations, and synthesizes responses. A2 is intentionally outside the bank data plane: if it needs peer evidence, it asks F1; if peer banks can answer, their A3 silo responders do the local data access inside their own trusted boundary.
- **Rule constraints (LLM cannot override):**
  - Cannot include customer names in outbound `Sec314bQuery` or SAR narrative fields (AML adapter redacts at egress; A2 cannot opt out)
  - Cannot send `Sec314bQuery` without a structured purpose declaration (rejected by F1 if missing)
  - Cannot escalate to SAR without a peer-bank corroborating signal (rule prevents single-bank speculation from becoming a SAR)
  - Cannot answer incoming peer `Sec314bQuery` messages; the policy adapter routes those only to local A3
  - Cannot call P7 or read raw transactions directly
- **Rule bypasses:** `A2-B1` and `A2-B2` in the bypass rule catalog.

**Agent A3: Silo responder agent** (one per bank, identical role; inside the bank trusted/TEE boundary)

- **Role:** Receives approved `Sec314bQuery` messages from F1, maps each query to declared P7 stats primitives, invokes those primitives over local bank data, and returns a `Sec314bResponse` with provenance. A3 is not human-facing and does not make SAR or dismissal decisions.
- **Inputs:** `Sec314bQuery` from F1 only.
- **Outputs:** `Sec314bResponse` to F1 only.
- **Reasoning:** Gemini call for primitive selection and response composition, surrounded by deterministic checks. P7 computes every value. The LLM can choose from allowed primitives and explain the response, but it cannot compute or fabricate values.
- **Rule constraints (LLM cannot override):**
  - Cannot include customer names in outbound `Sec314bResponse`.
  - Cannot answer a query unless the purpose declaration is present and was approved by F1.
  - Every numeric/list value in `Sec314bResponse.fields` must trace to a stats-primitives call.
  - Budget exhaustion behavior is handled by `A3-B3`; A3 cannot retry around it.
  - Cannot send messages to A2, A1, other banks, or F-agents other than F1.
- **Rule bypasses:** `A3-B1` through `A3-B3` in the bypass rule catalog.

#### Federation-layer agents (in assumed TEE)

**Agent F1: Cross-bank coordinator agent**

- **Role:** Receives `Sec314bQuery` from any bank's A2. Validates purpose declaration. Broadcasts the AML-adapter-redacted query to peer banks' A3 silo responders. Collects responses. Forwards anonymized aggregates to F2.
- **Reasoning:** Gemini call. F1 reasons about which peer banks the query is relevant to (not every query needs every bank), how to phrase the query for peer A3 responders, how to aggregate responses for the requesting A2.
- **Rule constraints (LLM cannot override):**
  - Cannot retain customer identifiers between queries (stateless by orchestrator design; adapter rejects identifier-bearing payloads)
  - Cannot forward a query without a valid `Sec314bQuery.purpose` field
  - Cannot send the same query body to peers that contains customer-name strings (AML adapter redacts at the channel)
- **Rule bypasses:** `F1-B1` through `F1-B3` in the bypass rule catalog.

**Agent F2: Graph-analysis agent**

- **Role:** Receives anonymized cross-bank transaction-pattern aggregates from F1. Identifies ring structures (closed cycles, structuring rings, layering chains). Returns suspected-pattern reports with confidence scores.
- **Reasoning:** Gemini call. F2 reasons about whether observed aggregate patterns are consistent with known typologies, what the most likely structure is, how confident to be.
- **Rule constraints (LLM cannot override):**
  - Cannot see raw transactions (input is DP-noised aggregates only; F2 has no DB handle)
  - Cannot output individual-customer identifiers (output schema restricts to entity-hash IDs)
- **Rule bypasses:** `F2-B1` and `F2-B2` in the bypass rule catalog.

**Agent F3: Sanctions / PEP screening agent**

- **Role:** Receives entity hashes from A2 or F1. Returns binary match flags against the (mock) SDN watchlist, plus PEP relation indicators when applicable.
- **Reasoning:** Gemini call. F3 reasons about fuzzy matches (similar name hashes, partial matches, transliteration variants in a real deployment). The mock list contains exact hashes for the demo's planted PEP entity plus ~10 well-known fictional names.
- **Rule constraints (LLM cannot override):**
  - Cannot return list contents (output is binary + relation type only)
  - Cannot retain queried entity hashes between requests
- **Rule bypasses:** `F3-B1` and `F3-B2` in the bypass rule catalog.

**Agent F4: SAR drafter agent**

- **Role:** Receives `SARContribution` messages from one or more A2 agents plus F2's pattern report and F3's sanctions findings. Synthesizes a Suspicious Activity Report draft with proper structured fields and narrative.
- **Reasoning:** Gemini call. F4 reasons about how to combine contributions into a coherent SAR narrative, what additional information to request from contributors, how to phrase regulatory-quality language.
- **Rule constraints (LLM cannot override):**
  - Must include `purpose_declaration` field linking back to §314(b) authority
  - Must include per-bank attribution for each piece of evidence
  - Cannot include customer-name strings (AML adapter redacts; uses `name_hash` references instead)
- **Rule bypasses:** `F4-B1` and `F4-B2` in the bypass rule catalog.

**Agent F5: Compliance auditor agent**

- **Role:** Subscribes to the normalized audit stream, including LT verdicts and AML adapter events. Reasons about whether each cross-agent message exceeds §314(b) authorization or pattern-matches a "fishing expedition." Emits compliance annotations to the audit panel.
- **Reasoning:** Gemini call. F5 reasons about whether a query series is investigating a legitimate suspicion or trolling for general information about a peer bank's customers. Flags anomalies in NL form.
- **Rule constraints (LLM cannot override):**
  - Read-only on the audit stream (cannot block or modify agent behavior)
  - Cannot suppress audit events from being logged
- **Rule bypasses:** `F5-B1` and `F5-B2` in the bypass rule catalog.

### 8.4 Threat model

| Trusted | Untrusted |
|---|---|
| Each bank's raw data + local A1/A3 inside the bank trusted boundary | Other banks' raw data (never shared) |
| A2 outside-TEE investigator process | Raw transaction data and P7 handles |
| Federation layer process (assumed in TEE) | Operator/cloud (production assumes TEE) |
| Lobster Trap (NL channel + role-auth) | Compromised bank agent (defended by schema + LT) |
| Schema validator (numerical channel) | Curious investigator at a peer bank (defended by DP + AML redaction adapter) |
| P7 privacy ledger | Malicious investigator running fishing expeditions (defended by §314(b) purpose checks + budget) |
| Message security envelope | Man-in-the-middle attacker on inter-agent network paths |

Defense mapping:
- **Lobster Trap + AML adapter** closes NL extraction (customer names in queries/responses), role abuse (A1 trying to act as A2), and injection
- **Schema validation** ensures no raw transactions leave a bank
- **Message signatures + replay protection** make cross-boundary messages tamper-evident and bind responses to the exact approved query
- **DP budget accounting** bounds how much an investigator can learn about peer-bank customers across many queries
- **§314(b) purpose declarations** create a per-query justification that's logged for regulator review

### 8.5 Security envelope and MITM controls

Lobster Trap is a content and policy layer. It is not the cryptographic integrity layer. The runtime should assume an attacker can observe, replay, delay, or modify network messages unless the transport and message envelope prove otherwise.

Required controls:

- **mTLS service identity:** A2, F1, A3, Lobster Trap, LiteLLM, and supporting services authenticate each other at the transport layer.
- **Signed message envelopes:** every cross-boundary `Sec314bQuery`, `Sec314bResponse`, SAR contribution, and audit event is signed over canonical JSON with a `signing_key_id`.
- **Request/response binding:** `Sec314bResponse` includes `in_reply_to`, the original `query_id`, the responding bank, and a hash of the exact F1-approved query body.
- **Route approval binding:** A3 verifies that the query was approved by F1 for this responding bank before it can invoke P7. F1 approval is necessary, not sufficient.
- **Replay protection:** every envelope has `message_id`, `nonce`, `created_at`, `expires_at`, and an idempotency cache keyed by sender and nonce.
- **Audit hash chain:** each audit event records the previous audit hash so deletion or mutation is detectable.
- **TEE attestation hook:** if the demo claims F1 or A3 runs inside a TEE, callers can verify the expected runtime measurement before trusting the channel.

The resulting message path is:

```text
User -> A2
A2 signs query -> LT/policy -> F1
F1 validates and signs route approval -> LT/policy -> A3
A3 verifies A2 origin, F1 approval, freshness, purpose, target, query shape, and DP budget
A3 calls P7
A3 signs response and provenance -> LT/policy -> F1
F1 verifies and aggregates
F1 signs aggregate -> LT/policy -> A2
A2 verifies and reports to the user
```

A3 can refuse with `invalid_purpose`, `route_violation`, `unsupported_query_shape`, `replay_detected`, `signature_invalid`, or `budget_exhausted`. It never returns raw rows as a negotiation fallback.

---

## 9. Data Layer *(Design)*

### 9.1 Synthetic data shape

Three SQLite databases, one per bank, each containing:

```
customers          (customer_id, name_hash, dob_year, kyc_risk_tier, account_open_date)
accounts           (account_id, customer_id, account_type, open_date, status)
transactions       (transaction_id, account_id, counterparty_account_id_hashed,
                    amount, currency, transaction_type, timestamp, channel)
suspicious_signals (signal_id, transaction_id, signal_type, severity, computed_at)
```

### 9.2 Volume

- **3 banks** (Bank Alpha, Bank Beta, Bank Gamma)
- **~5,000 customers per bank** (15,000 total; some cross-bank overlap)
- **~50,000 transactions per bank** over 12-month window (150,000 total)
- **~10–20 alerts per bank/day** generated by A1 (most false positives)

Total dataset ~50 MB across three SQLite files.

### 9.3 Planted ring scenario (the demo's hero)

A **5-entity structuring ring** spanning all three banks. Each entity holds an account at exactly two of the three banks. Over a 90-day window, the ring conducts ~200 sub-$10K transfers among each other, with the following properties:

- Per-bank, the activity looks like ordinary small-business transactions (each entity has a plausible cover business)
- Per-bank velocity is just below each bank's individual alert threshold
- **Cross-bank pattern** is the structuring tell: the ring's transfers form a closed cycle through all three banks
- Counterparty hashes match across banks (the federation can detect this if banks share anonymized hashes)
- One entity has a synthetic PEP (politically exposed person) relation that the sanctions agent flags

### 9.4 Calibration

For realism, we calibrate from public sources:

- FinCEN published SAR statistics (alert volumes, typologies)
- BSA Examination Manual (FFIEC) for what triggers a Currency Transaction Report
- Published structuring case summaries (DOJ press releases)

We deliberately do NOT use real bank data; the demo data is fully synthetic with planted typologies.

### 9.5 Checksum and reproducibility

Same pattern as the prior clinical data layer: deterministic seed (`SEED=20260512`), post-build canonical fingerprint hash baked into `tests/test_data_checksum.py`. The test confirms the planted ring is detectable centrally on the union of bank databases.

---

## 10. Validation Strategy *(Define)*

- **Federation correctness:** detection of the planted ring on the pooled data via central analysis must succeed (sanity check). No single bank can detect the ring from its own data alone (this is the federation pitch — must verify).
- **Agent message contracts:** each agent's input/output schema validated by Pydantic; mismatched messages fail loud.
- **Lobster Trap audit completeness:** every cross-bank message produces a structured audit-log entry; the audit log shows the canonical demo as 10–15 events with clear timestamps.
- **End-to-end smoke:** run the canonical demo flow 3 times in a row; all 3 produce identical (or DP-noise-similar) outcomes; total runtime stays under 3 minutes.
- **Per-agent unit tests:** Pydantic message round-trips; A1 produces alerts on known structuring patterns; F3 correctly returns "match" on the planted PEP entity.

---

## 11. Build Plan — granular parts *(Develop)*

Submission deadline: May 19, 2026. Target ship: May 17 (two days of buffer for rehearsal and polish before demo day).

Each part below has a single deliverable, an acceptance test, and an explicit dependency. The discipline is small enough that a part lands in a single coding session and the work can pause cleanly between parts. Status legend: **✓** done · **→** in progress · **·** not started.

### Current build state

The proxy chain (Lobster Trap → LiteLLM → Gemini/OpenRouter) is scaffolded. Lobster Trap policy behavior, blocked proxy ingress, and OpenRouter fallback pass-through are smoke-tested locally; direct Gemini pass-through still requires a valid Gemini API key. The pivot to AML preserves the generic proxy chain; what changes is the concrete agent code, the stats-primitives layer, and the AML policy adapter plus LT overlay. The AML data layer, shared message schemas, and base agent runtime are complete, with a schema follow-up still needed for signed security-envelope fields, `RouteApproval`, and the audit hash-chain introduced by the TEE/MITM separation.

- **P0** Repo scaffold + proxy chain smoke ✓
- **P1** Pivot migration (clinical → AML, plan and archives) ✓
- **P2** Bank data layer + planted scenarios ✓
- **P3** Bank data validation + checksum test ✓
- **P4** Shared message schemas ✓
- **P5** Agent runtime base class ✓
- **P6** A1 transaction-monitoring agent ✓
- **P7** Bank-local stats-primitives layer + DP ✓
- **P8** A2 investigator agent ✓
- **P8a** A3 silo responder agent ·
- **P9** F1 cross-bank coordinator ·
- **P10** F3 sanctions / PEP screening agent ·
- **P11** F2 graph-analysis agent ·
- **P12** F4 SAR drafter agent ·
- **P13** F5 compliance auditor agent ·
- **P14** AML policy adapter + Lobster Trap overlay ·
- **P15** Agent orchestrator / message bus + UI control API ·
- **P16** Canonical demo flow script ·
- **P17** End-to-end smoke test ·
- **P18** Interactive judge console ·
- **P19** README + mermaid diagrams for AML ·
- **P20** Pitch deck ·
- **P21** Demo dry-run × 3 + screencast ·
- **P22** Hackathon submission ·

---

### Done parts (P0–P8)

**P0 — Repo scaffold + proxy chain smoke** ✓

- *Goal:* repo skeleton, the governance proxy chain (Lobster Trap → LiteLLM → Gemini), and a local smoke harness that exercises LT policy and the blocked-prompt proxy path. Domain-agnostic governance substrate that survives the AML pivot unchanged.
- *Files:* `pyproject.toml` (uv-managed Python deps), `.env.example` (`GEMINI_API_KEY` and `OPENROUTER_API_KEY` placeholders), `.gitignore`, `infra/litellm_config.yaml` (OpenAI-compatible routing to `gemini/gemini-2.5-pro` and `gemini/gemini-2.5-flash`), `infra/litellm_openrouter_config.yaml` (OpenRouter fallback routing to Gemini models), `infra/docker-compose.yml` (LiteLLM + LT containers), `infra/lobstertrap/{Dockerfile,base_policy.yaml}` (universal LT policies: prompt injection, jailbreaks, obfuscation, private-data extraction, dangerous commands), `scripts/{start_litellm.ps1,start_lobstertrap.ps1,bootstrap_lobstertrap.ps1}` (Windows-native start scripts), `scripts/{smoke_proxy.py,smoke_openrouter.py,smoke_lobstertrap.py,p0_cases.py}` (P0 smoke harness), `tests/test_p0_cases.py` (pytest binding of the smoke cases).
- *What was built:* launch/config files for LiteLLM on port 4000 with OpenAI-shaped `/v1/chat/completions`; launch/config files for Lobster Trap on port 8080 with the base policy enforced; a P0 case file declaring known-allowed and known-blocked prompts; a blocked-prompt proxy smoke path that does not need a provider key; a benign pass-through case that calls live provider routing through the full chain when a valid provider key is available; an OpenRouter fallback smoke path that uses the same LT/LiteLLM chain with `OPENROUTER_API_KEY`.
- *Acceptance (current):* `uv run pytest tests/test_p0_cases.py` passes the offline cases; `scripts/smoke_lobstertrap.py` confirms LT blocks the negative cases; blocked prompts pass through the live LT proxy with `scripts/smoke_proxy.py --no-include-benign`; OpenRouter fallback pass-through passes with `scripts/smoke_openrouter.py`. Direct Gemini pass-through remains gated on a valid user-supplied `GEMINI_API_KEY`.
- *Notes for future readers:* The proxy chain is intentionally minimal. LT enforces the base policy. AML-specific routing, redaction, and purpose-declaration checks are handled in P14 by our Python policy adapter, with any LT YAML overlay limited to what current LT supports. LT runs as a sidecar to LiteLLM so swapping LLM providers primarily touches the LiteLLM config.

**P1 — Pivot migration (clinical → AML)** ✓

- *Goal:* Replace the clinical product framing with AML throughout the repo, while preserving the clinical work as an archived historical record. The pivot rationale (AI hackathon needs natively multi-agent texture; AML has it, clinical did not) is a reference document.
- *Files modified:* `plan.md` (entirely rewritten for AML — see Sections 1–16 above); `README.md` (top blurb rewritten + pivot note linking forward); `data/README.md` (rewritten as placeholder for the AML data layer).
- *Files moved:* original `plan.md` → `docs/clinical-archive/plan.md`; clinical data-pipeline scripts `download_synthea_omop.py`, `build_silos.py`, `feature_engineering.py`, `apply_scenarios.py`, `validate.py`, `vocab.py` → `data/scripts/clinical-archive/`.
- *What was built:* the AML product spec (the rest of this document); the clinical work preserved at archive paths; the README pivot note linking forward. The proxy chain, LiteLLM, the Gemini routing config, and the P0 smoke scripts were preserved unchanged — domain-agnostic governance substrate.
- *Acceptance:* clinical artifacts visible at archive paths; AML framing visible from repo root; nothing in `infra/`, `scripts/`, or the proxy chain was disturbed by the pivot; `pytest tests/test_p0_cases.py` still passes.
- *Notes for future readers:* the clinical plan and scripts remain as a real reference because the architecture (planner LLM + N silo statistical primitives + DP) maps directly to federated clinical research — the cross-vertical applicability slide in P20 leans on this.

**P2 — Bank data layer + planted scenarios** ✓

- *Goal:* Three SQLite bank databases with calibrated synthetic data plus four planted AML scenarios that are centrally detectable on the pooled data and locally invisible to any single bank.
- *Files:* `data/scripts/build_banks.py` (~580 lines), `data/scripts/plant_scenarios.py` (~550 lines), `data/silos/bank_alpha.db` (32 MB), `data/silos/bank_beta.db` (14 MB), `data/silos/bank_gamma.db` (7 MB).
- *Bank profiles (deliberately diverse, calibrated to industry norms):*
  - **Bank Alpha** (national): 8,000 customers · 14,043 accounts · 112,212 transactions · 1,969 baseline signals. KYC mix 60/30/10 retail/SB/commercial. Channels lean wire (30%) + electronic (45%). Alert sensitivity 0.6 (sophisticated AML = fewer FPs).
  - **Bank Beta** (regional community): 5,000 customers · 8,375 accounts · 46,743 transactions · 794 baseline signals. KYC mix 65/32/3. Channels are check + cash heavier (18% + 10%). Alert sensitivity 1.0 (baseline).
  - **Bank Gamma** (credit union): 3,000 customers · 4,836 accounts · 22,961 transactions · 313 baseline signals. KYC mix 85/13/2. Channels dominated by electronic (50%) + debit (30%). Alert sensitivity 1.4 (less-sophisticated monitoring = more FPs).
- *Tables per bank:* `customers (customer_id, name_hash, dob_year, kyc_tier, account_open_date)`, `accounts (account_id, customer_id, account_type, open_date, status)`, `transactions (transaction_id, account_id, counterparty_account_id_hashed, amount, currency, transaction_type, timestamp, channel)`, `suspicious_signals (signal_id, transaction_id, signal_type, severity, computed_at)`, `ground_truth_entities (entity_id, customer_id, name_hash, cover_business, scenario, role, is_pep)` — used only by the validator and tests; the federation runtime never reads it.
- *Determinism:* SHA-256-derived per-bank RNG seed (`base_seed + int(sha256(bank_id)[:8], 16) % 1_000_000`) so re-running produces bit-identical DBs across Python versions and operating systems. Python's built-in `hash()` is process-randomized and unfit for this; SHA-256 is stable.
- *Calibration sources:* FFIEC BSA/AML Examination Manual ($10K CTR threshold, $3K enhanced-recordkeeping threshold), FinCEN annual SAR statistics, published industry channel-mix distributions, lognormal amount distributions per KYC tier with industry-rough means.
- *Planted scenarios (all use stable `name_hash` for cross-bank linkage; each transfer dual-booked debit-at-sender + credit-at-receiver):*
  - **S1** — 5-entity structuring ring across all three banks. ~100 paired transfers ($795,152.42 total). Each entity holds accounts at exactly 2 of the 3 banks. Sub-CTR amounts ($5K–$9,999.99) weighted 70% toward the upper end (the structuring tell).
  - **S2** — 3-entity smaller structuring ring across Alpha + Beta only. ~40 transfers ($324,945.48). Proves federation handles partial-overlap (no Gamma presence).
  - **S3** — 4-entity layering chain Alpha→Beta→Gamma→Alpha (closes a loop). ~32 transfers ($2,818,737.92), 3% per-hop "fee" attenuation across 8 iterations.
  - **S4** — PEP marker on entity S1-D ("Delta Imports Ltd"). Single boolean column in `ground_truth_entities`; sanctioned-hash equivalent for F3.
- *Acceptance:* all three `.db` files produced and verified by `validate_banks.py` (P3); reproducibility tested by running the build twice and comparing the canonical fingerprint hash.
- *Notes for future readers:* baseline transactions in `build_banks.py` are *one-sided* (counterparties are hashed external IDs or other-account hashes without a matching record on the other side — like the real world). Only scenario-planted transactions in `plant_scenarios.py` are dual-booked. The validator's section 8 closure check (P3) explicitly relies on this distinction by joining transactions through `ground_truth_entities` to isolate scenario transfers.

**P3 — Bank data validation + checksum test** ✓

- *Goal:* Verify every planted property exists structurally; lock down the data layer with a content-based fingerprint hash that fails any future drift.
- *Files:* `data/scripts/validate_banks.py` (~290 lines, 8 check sections), `tests/test_data_checksum.py` (~275 lines).
- *Validator structure (8 sections, all PASS at the canonical hash):*
  1. Database files + schema (5 tables per bank, non-trivial size)
  2. Planted scenario ground truth (12 distinct shell entities; per-scenario counts 5/3/4; 1 PEP)
  3. Cross-bank entity presence via `name_hash` linkage (S1 entities at 2 banks each, S2 entities at Alpha+Beta only with 0 Gamma presence, S3 chain start at 1 bank with relays at 2)
  4. Federated detectability — recovery via cross-bank `name_hash` matching (11/11 multi-bank entities recovered; 344 pooled shell-entity transactions ≥ the 200 threshold)
  5. Single-bank invisibility — per-bank near-CTR alert counts ≥50 prove the FP haystack (actual: 1354 / 403 / 132)
  6. PEP marker confined to S1 (sanity check)
  7. Layering chain (S3) closes a loop at `bank_alpha`
  8. Dual-booking balance closure: per-scenario and pooled debit/credit count + amount parity (cents-exact); strict 1:1 mirror via multiset equality on `(sender_acct_hash, receiver_acct_hash, amount, timestamp)`; 0 unmatched across 172 transfers
- *Checksum fingerprint (`version = 3`):* per-bank `(n_customers, n_accounts, n_transactions, n_signals, n_shell_entities, n_pep, amount_sum_cents)` plus per-table SHA-256 row hashes (customers, accounts, transactions, signals, ground_truth) plus pooled aggregates. Canonical hash: `3a87870c1d58a50a6f0df69bf95e6b92a9cfe38297cba2c849e9297a4a13b45e`.
- *Acceptance:* `uv run python data/scripts/validate_banks.py` exits 0; `uv run pytest tests/test_data_checksum.py` matches the canonical hash.
- *Notes for future readers:* the section 8 dual-booking closure check is the strongest correctness invariant — it would catch a class of bug (a single-leg dropped transfer) that count/structural checks could miss. Use `python tests/test_data_checksum.py --update` to regenerate the hash after intentional data changes; commit the regenerated hash in the same PR.

---

### Next parts (P4–P13)

The agent build follows the canonical demo's call order: alert origination (A1) → investigator (A2) → coordinator (F1) → silo response (A3) → sanctions (F3) → graph analyst (F2) → SAR drafter (F4) → compliance auditor (F5). F3 ships before F2 because it's the simpler federation-layer agent and shakes out the agent base class first; F5 ships last because it depends on the live audit stream. P7 (stats-primitives layer) ships before A3 because A3's cross-bank response path calls into it. A2 no longer has a P7 handle.

**P4 — Shared message schemas** ✓

- *Goal:* Pydantic v2 boundary objects for every cross-agent message in the canonical flow. The schemas are the trust contract between agents — every cross-agent value lives inside a typed envelope. Gemini structured-output targets the JSON-schema export of each model.
- *Files:* `shared/__init__.py`, `shared/messages.py` (one module, all models), `shared/enums.py` (typology codes, query shapes, audit-event kinds), `tests/test_messages.py` (round-trip + invalid-example tests for every model).
- *Common header — every model inherits from a `Message` base with:*
  - `message_id: UUID` (UUID4, default-factory)
  - `sender_agent_id: str` (e.g., `"bank_alpha.A2"`)
  - `sender_role: Literal["A1","A2","A3","F1","F2","F3","F4","F5","orchestrator"]`
  - `sender_bank_id: str | Literal["federation"]`
  - `recipient_agent_id: str`
  - `created_at: datetime` (UTC)
  - `expires_at: datetime | None` (required on cross-boundary messages)
  - `nonce: str | None` (required on cross-boundary messages)
  - `body_hash: str | None` (SHA-256 over canonical JSON body; required on signed cross-boundary messages)
  - `signature: str | None` and `signing_key_id: str | None` (required on A2/F1/A3 boundary crossings)
- *Models to define:*
  - **`Alert`** (A1 → A2): `alert_id`, `transaction_id`, `account_id`, `signal_type` (enum), `severity ∈ [0,1]`, `rationale` (LLM-authored, ≤300 chars), `evidence` (list of correlated transaction summaries with hashed identifiers only — no customer names). Evidence separates local `account_hashes`/`transaction_hashes` from cross-bank `entity_hashes`/`counterparty_hashes`.
  - **Hash type convention:** `CrossBankHashToken` is a 16-character lowercase-hex token produced by the synthetic data builders for cross-bank linkage (`name_hash`, counterparty hash, sanctions entity hash). `Sha256Hex` is a full 64-character SHA-256 used for local identifiers and audit args hashes. `OpaqueHashToken` is only for mixed evidence fields where either shape can appear.
  - **`Sec314bQuery`** (A2 → F1 → peer A3): `query_id`, `requesting_investigator_id`, `requesting_bank_id`, `target_bank_ids` (default: all peers), `query_shape ∈ {"entity_presence","aggregate_activity","counterparty_linkage"}` (discriminated union), `query_payload` (typed by `query_shape`; entity/counterparty identifiers are `CrossBankHashToken`; counterparty linkage uses `counterparty_hashes`), `purpose_declaration: PurposeDeclaration`, `requested_rho_per_primitive: float`. `PurposeDeclaration` is a structured object: `{authority: "USA_PATRIOT_314b", typology_code: TypologyCode, suspicion_rationale: str (≤500 chars), supporting_alert_ids: list[UUID]}`.
  - **`Sec314bResponse`** (peer A3 → F1 → requesting A2): `in_reply_to: UUID` (the query_id), `responding_bank_id`, `fields: dict[str, ResponseValue]` (`ResponseValue` is a small union: `{"int":int}|{"float":float}|{"bool":bool}|{"histogram":list[int]}|{"hash_list":list[str]}`), `provenance: list[PrimitiveCallRecord]` (one entry per field), `rho_debited_total: float`, `refusal_reason: str | None`. **Invariant enforced by validator: each key in `fields` has a corresponding `PrimitiveCallRecord.field_name` in `provenance`.**
  - **`PrimitiveCallRecord`**: `field_name`, `primitive_name`, `args_hash` (SHA-256 of canonicalized args; for audit-replay), `privacy_unit` (`"transaction"` for the hackathon P7 build unless explicitly upgraded), `rho_debited` (0.0 for non-DP primitives), `eps_delta_display: tuple[float, float] | None`, `sigma_applied: float | None`, `sensitivity: float`, `returned_value_kind`, `timestamp`.
  - **`RouteApproval`** (F1 → A3, embedded or referenced by the routed query): `approval_id`, `query_id`, `approved_query_body_hash`, `requesting_bank_id`, `responding_bank_id`, `approved_by_agent_id`, `approved_at`, `expires_at`, `signature`. A3 verifies this before invoking P7.
  - **`SanctionsCheckRequest`** (A2 or F1 → F3): `entity_hashes: list[str]`, `requesting_context: str`.
  - **`SanctionsCheckResponse`** (F3 → caller): `results: dict[hash → {sdn_match: bool, pep_relation: bool}]`. **No list contents disclosed.**
  - **`GraphPatternRequest`** (F1 → F2): `pattern_aggregates: list[BankAggregate]` (per-bank DP-noised tuples: `bank_id`, `edge_count_distribution`, `bucketed_flow_histogram`), `window_start`, `window_end`.
  - **`GraphPatternResponse`** (F2 → caller): `pattern_class ∈ {"structuring_ring","layering_chain","none"}`, `confidence ∈ [0,1]`, `suspect_entity_hashes: list[str]`, `narrative: str (≤500 chars)`.
  - **`SARContribution`** (A2 → F4): `contributing_bank_id`, `contributing_investigator_id`, `contributed_evidence: list[EvidenceItem]` (hashed identifiers only), `local_rationale`, `related_query_ids: list[UUID]`.
  - **`SARDraft`** (F4 → orchestrator): `sar_id`, `filing_institution`, `suspicious_amount_range: tuple[int,int]` (cents), `typology_code: TypologyCode`, `narrative` (LLM-authored, regulator-quality), `contributors: list[ContributorAttribution]`, `sar_priority ∈ {"standard","high"}`, `mandatory_fields_complete: bool`, `related_query_ids: list[UUID]`.
  - **`AuditEvent`** (any → audit channel): signed wire-level audit record with `event_id`, `kind ∈ {"message_sent","lt_verdict","constraint_violation","bypass_triggered","rho_debited","budget_exhausted","human_review","rate_limit"}`, `actor_agent_id`, `payload: AuditPayload` (typed by `kind`), `prev_event_hash`, `event_hash`. This is separate from local `RuntimeAuditEvent` records emitted by the P5 agent base; P15 maps runtime events into wire-level audit envelopes.
  - **`DismissalRationale`** (A2 → F5): `alert_id`, `reason`, `evidence_considered`.
- *Approach:* Pydantic v2 `BaseModel` with strict mode and `model_config = ConfigDict(extra="forbid")`. Field validators where the constraint is structural: `Sec314bQuery.purpose_declaration.suspicion_rationale` non-empty; `Sec314bResponse.fields.keys()` ⊆ `{p.field_name for p in provenance}`; `SARDraft.mandatory_fields_complete=True` only if all of `filing_institution`, `suspicious_amount_range`, `typology_code`, `narrative` are populated; cross-boundary messages require `expires_at`, `nonce`, `body_hash`, `signature`, and `signing_key_id`. Discriminated unions on `query_shape` and `AuditEvent.kind` so Gemini's structured-output can target each variant.
- *Out of scope for this part:* no agent code, no LT integration, no DP arithmetic, no SQLite reads. Pure schema + tests.
- *What was built:* `shared/enums.py` defines the stable enum surface for roles, banks, query shapes, typologies, audit event kinds, privacy units, and response value kinds. `shared/messages.py` defines strict Pydantic v2 models for every P4 contract, including explicit hash-shape aliases (`CrossBankHashToken`, `Sha256Hex`, `OpaqueHashToken`), typed `Sec314bQuery` payload unions, `Sec314bResponse` provenance invariants, SAR completeness checks, customer-name guardrails for safe text fields, and normalized wire-level `AuditEvent` payload unions. `tests/test_messages.py` covers round trips, JSON-schema export, and invalid examples.
- *Follow-up after TEE/MITM split:* add `A3` to the role enum, add signed-envelope fields, add `RouteApproval`, add audit hash-chain fields, and update tests before P8a/P14/P15 rely on them.
- *Acceptance (current):* `uv run pytest tests/test_messages.py` passes 36 schema tests. Every public message model round-trips through JSON and exports JSON schema. Invalid cases fail for extra fields, missing purpose rationale, query-shape mismatch, response fields without matching provenance, response kind/rho mismatches, refusal responses with fields, customer-name strings in evidence, incomplete SAR drafts marked complete, audit kind/payload mismatch, federation-origin bank aggregates, and reversed date windows. Live Gemini schema generation remains optional and is not required for the local P4 contract gate.
- *Risks specific to this part:* (a) Pydantic v2's strict mode + discriminated unions can be finicky with Gemini's occasional JSON output drift — mitigation: write the schemas with Gemini JSON-mode quirks in mind (avoid deeply nested unions; document known Gemini-output limitations in module docstrings). (b) `Sec314bResponse.fields` is open-ended by design (different query shapes return different field sets); mitigation: schema permits arbitrary string keys but every key must have matching provenance.
- *Depends on:* P0.
- *Scope check:* one focused session — write models, write validators, write tests, run the opt-in Gemini round-trip. Stops at "schemas validated, no live agent code."

**P5 — Agent runtime base class**

- *Goal:* A single `Agent` base class that encapsulates the LLM call + the rule-constraint check + the rule-bypass check pattern that every agent follows. Centralizes Gemini calling, retry logic, audit emission, structured-output parsing, and constraint/bypass plumbing so every concrete agent just declares its prompt + schema + rules. The runtime must be node-aware: A2, F1, and each A3 silo can point at its own local Lobster Trap/LiteLLM stack instead of a single global proxy URL.
- *Files:* `backend/__init__.py`, `backend/agents/__init__.py`, `backend/agents/base.py`, `backend/agents/rules.py`, `backend/agents/llm_client.py` (thin wrapper around a node-local LT-proxied OpenAI-compatible Gemini endpoint), `backend/runtime/__init__.py`, `backend/runtime/context.py` (Pydantic config for node identity and local LLM endpoint), `tests/test_agent_base.py`, `tests/test_llm_client.py`.
- *Runtime config boundary objects:*
  - `LLMClientConfig`: `base_url`, `api_key_env`, `default_model`, `timeout_seconds`, `max_retries`, `stub_mode`, `node_id`. `base_url` defaults to `http://127.0.0.1:8080/v1/chat/completions` only for local mode; cloud-demo nodes pass their own local LT URL.
  - `AgentRuntimeContext`: `run_id`, `node_id`, `trust_domain`, `llm: LLMClientConfig`, `audit: AuditEmitter | None`, `metadata: dict[str, str] = {}`. This is passed into each agent at construction time.
  - `TrustDomain`: enum-like values `investigator`, `federation`, `bank_silo`. P15 later expands this into full node config, but P5 establishes the boundary.
- *Class shape:*
  ```python
  InT = TypeVar("InT", bound=BaseModel)
  OutT = TypeVar("OutT", bound=BaseModel)

  class Agent(Generic[InT, OutT]):
      role: AgentRole
      bank_id: str | Literal["federation"]
      system_prompt: str
      output_schema: type[OutT]
      bypass_rules: list[BypassRule[InT, OutT]]
      constraint_rules: list[ConstraintRule[InT, OutT]]
      llm: LLMClient
      audit: AuditEmitter
      runtime: AgentRuntimeContext
      def run(self, input: InT) -> OutT: ...
  ```
- *`run()` flow, in order:*
  1. **Input validation.** Validate `input` with Pydantic/`TypeAdapter` before any rule or LLM call. Emit `constraint_violation` and raise `InvalidAgentInput` if the caller passed the wrong boundary object.
  2. **Bypass check.** Iterate `bypass_rules`; if any triggers, emit `bypass_triggered`, build the forced `OutT`, validate it, emit `message_sent`, and return without calling Gemini.
  3. **Prompt assembly.** Load `system_prompt` from the concrete agent's prompt file or inline test fixture, serialize the validated input to canonical JSON, attach `_lobstertrap` metadata (`agent_id`, `role`, `bank_id`, `trust_domain`, `run_id`, declared intent), and prepare the structured-output schema from `output_schema.model_json_schema()`.
  4. **LLM call.** Send the request through `runtime.llm.base_url`, not a hardcoded global URL. In local mode this is the P0 localhost LT endpoint; in cloud-demo mode it is the node-local LT endpoint. The client uses OpenAI-compatible chat completions via LiteLLM.
  5. **Structured-output parse.** Parse the response content into `OutT` using `output_schema.model_validate_json()` or `model_validate()`. If JSON is malformed or schema validation fails, retry once with the schema and parse error included in the repair prompt. On second failure, emit `constraint_violation` and raise `LLMOutputUnparseable`.
  6. **Constraint check.** Iterate `constraint_rules`; on violation, emit `constraint_violation`. Retry the LLM once with the violation message appended. If the retry still violates a constraint, raise `ConstraintViolation`.
  7. **Audit emit.** Emit `message_sent` with `run_id`, `node_id`, `agent_id`, `role`, `input_schema`, `output_schema`, retry count, bypass name if applicable, model name, and status. Do not log raw customer names or secrets.
  8. **Return validated output.** Only a validated `OutT` leaves `run()`.
- *Bypass and constraint rule shape:*
  - `BypassRule`: `name`, `trigger(input) -> bool`, `force_output(input) -> OutT`, `reason` (human-readable).
  - `ConstraintRule`: `name`, `check(input, output) -> bool` (True = ok), `violation_msg(input, output) -> str`.
- *LLM client specifics:*
  - `LLMClient.chat_structured(prompt, input_model, output_schema, metadata) -> dict`.
  - Uses `LLMClientConfig.base_url`, so A2/F1/A3 nodes can each point at their own local LT/LiteLLM stack.
  - Carries agent role, bank, trust domain, node id, run id, and declared intent in the request body's `_lobstertrap` field because current LT reads declared metadata from that field.
  - The application-level message envelope still carries `sender_role`, `sender_bank_id`, and `recipient_agent_id`; P14's Python AML policy adapter uses those fields for role routing and redaction.
  - Falls back to a deterministic stub if `LLM_STUB_MODE=1` or `LLMClientConfig.stub_mode=True`.
  - Uses exponential backoff only for provider/proxy errors; constraint failures retry immediately once with a repair prompt.
  - Never reads API keys from code. The configured `api_key_env` names the env var to read.
- *Out of scope for this part:* no concrete agents yet, no Lobster Trap policy authoring (that's P14), no orchestrator (P15). The base class is exercised by a `TrivialEchoAgent` in the test.
- *Acceptance:* `tests/test_agent_base.py` defines a `TrivialEchoAgent` with one bypass rule (force-echo input if input contains `"FORCE"`) and one constraint rule (output length ≤ 100 chars), runs it against the LLM stub. Tests cover:
  - normal path returns Pydantic-valid output
  - bypass triggers without an LLM call and still emits audit
  - malformed JSON triggers one parse-repair retry
  - constraint violation triggers one repair retry
  - second constraint failure raises `ConstraintViolation`
  - audit channel records `bypass_triggered`, `constraint_violation`, and `message_sent` with `run_id`, `node_id`, `role`, `phase`, and `status`
  - `LLMClientConfig.base_url` is honored, so two test agents can point at different fake LT endpoints
  - `LLM_STUB_MODE=1` prevents network calls
- *What was built:* `backend/runtime/context.py` defines strict Pydantic runtime config objects (`TrustDomain`, `LLMClientConfig`, `AgentRuntimeContext`). `backend/agents/rules.py` defines typed `BypassRule` and `ConstraintRule` objects. `backend/agents/llm_client.py` defines the OpenAI-compatible structured-output client that sends `_lobstertrap` metadata, honors node-local `base_url`, supports provider retries, and has deterministic stub mode. `backend/agents/base.py` defines the generic `Agent` runtime, P5 exceptions, and in-memory audit sink. `shared/enums.py` now includes the `A3` role needed by the split silo-responder architecture.
- *Acceptance (current):* `uv run pytest tests/test_agent_base.py tests/test_llm_client.py` passes 10 focused P5 tests. `uv run pytest` passes the full 133-test suite. `uv run python -m compileall backend shared tests` passes. `git diff --check` reports only CRLF normalization warnings.
- *Risks specific to this part:* (a) Gemini's structured-output mode occasionally returns invalid JSON — mitigation: one retry with `response_format` re-asserted; on second failure raise rather than half-parse. (b) LT may rate-limit during retry storms — mitigation: exponential backoff on LLM-side errors, not on constraint-side errors. (c) The generics typing (`Agent[InT, OutT]`) needs Pydantic v2's `TypeAdapter` to validate at runtime — mitigation: explicit `output_schema.model_validate(raw_json)` rather than relying on TypeVar resolution.
- *Depends on:* P0, P4.
- *Scope check:* one focused session. Stops at "trivial echo agent works end-to-end against the stub; a single opt-in test confirms it also works against live Gemini."

**P6 — A1 transaction-monitoring agent**

- *Goal:* Full LLM agent that reviews a batch of `suspicious_signals` + correlated transaction rows for one bank and emits `Alert` messages to local A2. Constraints prevent any non-A2 destination; bypasses force-emit on hard-required regulatory criteria (CTR threshold, SDN, velocity spikes).
- *Files:* `backend/agents/a1_models.py`, `backend/agents/a1_monitoring.py`, `backend/agents/prompts/a1_system.md` (the system prompt, kept in Markdown rather than inline text), `backend/silos/__init__.py`, `backend/silos/local_reader.py`, `data/mock_sdn_list.json`, `tests/test_a1.py`. P6 creates a minimal `data/mock_sdn_list.json` test stub if P10 has not populated the full mock list yet.
- *Inputs:* a batch of `SignalCandidate` records read from local SQLite via `backend/silos/local_reader.py`. A1 reads only its own bank's raw data; only the cross-bank-response path is gated by P7. Each candidate carries: `signal_id`, `transaction_id`, `amount`, `transaction_type`, `channel`, `timestamp`, `account_id`, precomputed `account_id_hash`, `customer_name_hash`, `customer_kyc_tier`, precomputed `transaction_id_hash`, `recent_near_ctr_count_24h`, `counterparty_account_id_hashed`, plus a fetched `source_signal_type` and `source_severity` from the bank's pre-existing rule-based scorer. The hashes are supplied in the input so a live model copies them instead of attempting to compute SHA-256.
- *Output:* a list of `Alert` records or an empty list per candidate. The LLM returns a structured `A1BatchResult { decisions: list[A1Decision] }` where each `A1Decision = {signal_id, action: "emit"|"suppress", alert: Alert | None, llm_rationale: str, bypass_rule_id: A1-B1|A1-B2|A1-B3|None}`. The `A1Decision` Pydantic model carries a `model_validator` enforcing `action="emit" ↔ alert is not None` and `action="suppress" ↔ alert is None`; this is a boundary-schema invariant, not a deterministic `ConstraintRule`.
- *Rule bypasses:* implement `A1-B1` through `A1-B3` from the Section 8.3 bypass rule catalog. Bypass rules are materialized per candidate before the LLM call, then merged back with LLM decisions in the original input order. This prevents a mixed batch from letting the LLM alter a hard-required bypass decision. The A1-B1 (CTR threshold) bypass emits an `Alert` with `signal_type = SignalType.CTR_REPORT`, not `SignalType.STRUCTURING`. A Currency Transaction Report is the federal reporting obligation for transactions ≥ $10K; structuring is the opposite typology (sub-$10K splitting to evade the threshold). The mapper in `map_signal_type` enforces this.
- *Rule constraints (LLM cannot override) — implemented as `ConstraintRule` objects in `backend/agents/a1_monitoring.py`:*
  1. **`one_decision_per_candidate`** — output must contain exactly one `A1Decision` per input `signal_id`; no missing, duplicate, or invented signals.
  2. **`alert_routing`** — every emitted `Alert.recipient_agent_id` is the local A2's agent_id, `sender_agent_id` is the local A1, and `sender_bank_id` is the agent's bank.
  3. **`bypass_decisions_match_policy`** — any candidate matching `A1-B1`, `A1-B2`, or `A1-B3` MUST result in `action="emit"` with a populated `alert`, the expected `bypass_rule_id`, and the deterministic signal type and severity for that bypass. This is a final-output invariant for A1's deterministic bypass merge path, not an LLM-level filter.
  4. **`alert_matches_candidate`** — every emitted `Alert.transaction_id` and `Alert.account_id` matches the source candidate's IDs; the LLM cannot invent or cross-link.
  5. **`evidence_uses_hashed_identifiers`** — `Alert.evidence[*]` carries the expected entity hash, counterparty hash when available, plus SHA-256 hashes of the source account and transaction IDs. Raw account or transaction IDs must not appear in any evidence field, including `summary`, `entity_hashes`, `account_hashes`, `counterparty_hashes`, or `transaction_hashes`.
- *Approach (Gemini call):* system prompt declares A1's role and the bypass criteria from the catalog (so the LLM doesn't waste tokens reasoning about CTR-threshold cases that are already decided); user message is the batch of candidates as JSON; structured output is the `A1BatchResult` schema. Use `gemini-2.5-flash` (cheaper, fine for this volume); fallback to `gemini-2.5-pro` if structured-output parsing fails twice.
- *Out of scope for this part:* no cross-bank communication, no DP, no peer-A2 interaction. A1 is local-bank-only.
- *Demo hook:* P6 includes a stub-friendly local demo command:
  ```powershell
  uv run python -m backend.agents.a1_monitoring demo --bank bank_alpha --limit 50 --stub
  ```
  The command loads a deterministic Bank Alpha batch, runs A1, and prints a Rich table with `signal_id`, `amount`, source signal, A1 decision, bypass rule if any, and short rationale. The visible demo point is that A1 converts noisy local monitoring signals into structured `Alert` messages for local A2, while still having only single-bank visibility.
- *Demo examples shown by the command:*
  - **LLM judgment:** a normal sub-CTR signal where A1 decides to emit or suppress.
  - **Mandatory bypass:** a synthetic `>= $10K` transaction triggers `A1-B1` with no LLM call.
  - **Planted scenario:** at least one S1-related near-CTR signal is emitted, but A1 cannot know it is part of a three-bank ring.
- *Acceptance:* `tests/test_a1.py` runs A1 on a deterministic batch of 50 signals from `data/silos/bank_alpha.db`:
  - The local reader exposes ≥5 S1-related `amount_near_ctr_threshold` candidates to A1.
  - **Full LLM path on planted S1 candidates:** running A1 with a stub LLM that mirrors realistic triage emits Alerts for ≥5 S1-related candidates; every emitted Alert is addressed to local A2 with hashed evidence; `llm.call_count == 1` confirms the LLM path was exercised (not a bypass-only path).
  - A synthetic ≥$10K transaction triggers the CTR bypass (`A1-B1`) with `action="emit"` regardless of LLM judgment.
  - A synthetic SDN-hash-match transaction triggers the SDN bypass (`A1-B2`).
  - A synthetic account with ≥10 near-CTR transactions in 24h triggers the velocity bypass (`A1-B3`).
  - A mixed batch with one bypass candidate and one normal candidate materializes the bypass before the LLM call, calls the LLM only for the normal candidate, and preserves original decision order.
  - A normal non-bypass candidate path calls the P5 LLM stub and returns a valid `A1BatchResult`.
  - Malformed LLM output gets repaired by the P5 base runtime.
  - A bad alert recipient is caught by constraint retry or raises `ConstraintViolation`.
  - Raw local account or transaction IDs inside any evidence field are caught by constraint retry or raise `ConstraintViolation`.
  - Every emitted `Alert` passes Pydantic validation against P4 schemas.
  - No alert addressed to anything other than local A2.
  - The demo command runs in `--stub` mode and prints loaded, emitted, and suppressed counts plus visible bypass labels.
- *What was built:* `backend/agents/a1_models.py` defines strict A1 boundary models (`SignalCandidate`, `A1BatchInput`, `A1Decision`, `A1BatchResult`) with precomputed account and transaction hash fields plus a `model_validator` enforcing the `action ↔ alert` invariant. `backend/silos/local_reader.py` reads typed local suspicious-signal batches from each bank SQLite database and computes SHA-256 hashes for local account and transaction IDs. The 24h near-CTR velocity is computed via a single batched SQL (`SELECT ... WHERE account_id IN (...)`) over the candidate set, replacing the previous N+1 per-candidate pattern. `backend/agents/a1_monitoring.py` implements the A1 agent, per-candidate A1-B1/A1-B2/A1-B3 bypass materialization before LLM review, the five post-LLM `ConstraintRule` objects, safe evidence hashing, the `map_signal_type` mapper (CTR→`CTR_REPORT`, SDN→`SANCTIONS_MATCH`, velocity→`RAPID_MOVEMENT`), synthetic demo candidates, and the Rich/Typer demo command. `backend/agents/prompts/a1_system.md` stores the A1 system prompt and tells live models to copy precomputed evidence hashes rather than calculate them. `data/mock_sdn_list.json` provides the P6 SDN test fixture. `shared/enums.py` gains `SignalType.CTR_REPORT` with a docstring distinguishing it from `STRUCTURING`. `LLMClient.set_stub_responses(...)` is a public test-affordance setter that replaces the stub queue and resets the cursor (so tests no longer reach into the private `_stub_responses` list).
- *Acceptance (current):* `uv run pytest tests/test_a1.py` passes 12 focused P6 tests (8 originally + 1 end-to-end S1 LLM-path test + 3 review regressions for mixed-batch bypass, bypass-policy invariant naming, and evidence leakage). `uv run python -m backend.agents.a1_monitoring demo --bank bank_alpha --limit 10 --stub` runs and prints the local A1 table with LLM-judgment rows, an S1 local row, and A1-B1/A1-B2 bypass rows. `uv run pytest` passes the full 133-test suite. `uv run python -m compileall backend shared tests` passes. `git diff --check` reports only CRLF normalization warnings.
- *Risks specific to this part:* (a) the LLM may over-suppress to reduce alert volume — mitigation: the prompt explicitly says "the bank already runs a rule-based scorer; your job is to triage, not to second-guess obvious cases" and severity score is in the input. (b) Gemini latency on batches >50 — mitigation: cap batch at 50; orchestrator chunks larger inputs. (c) The 24h velocity SQL fans out to every candidate account in one query — for a 50-row batch this is one SQL hitting at most 50 accounts; if A1 ever needs larger batches or longer windows, revisit the query plan.
- *Depends on:* P3 (data), P5 (base class).
- *Scope check:* one to two focused sessions — prompt engineering takes longer than code here.

**P7 — Bank-local stats-primitives layer + DP**

- *Goal:* A deterministic (non-LLM) module per bank that exposes a fixed set of declared query primitives over the bank's SQLite database, applies Gaussian DP noise where appropriate, and tracks a per-(investigator, peer-bank) budget using one internally consistent zCDP ledger. **This is the structural enforcement of design principle #6** — the data plane is severed from the outside-investigator path. A3's `Sec314bResponse` can only quote numbers that come out of here.
- *Files:* `backend/silos/__init__.py`, `backend/silos/stats_primitives.py` (the five primitives), `backend/silos/dp.py` (light OpenDP-backed Gaussian calibration + zCDP accounting helpers), `backend/silos/budget.py` (per-investigator privacy ledger), `backend/silos/local_reader.py` (the bank's own DB connector, also reused by A1), `tests/test_stats_primitives.py`, `tests/test_dp_composition.py`, `tests/test_budget.py`.
- *Primitive return shape:* primitives return `PrimitiveResult { value, records, refusal_reason }`. Successful calls carry a typed value plus one or more `PrimitiveCallRecord` records. Budget exhaustion returns `value=None`, `records=[]`, and `refusal_reason="budget_exhausted"`. Refusal state is not overloaded into provenance.
- *Primitive signatures:*
  - `count_entities_by_name_hash(name_hashes: list[str], requester: RequesterKey, rho: float = 0.0) -> (int, rec)` — Binary presence ish (count over a small set). **No DP applied** by default (the value is sensitivity 1 with magnitude 1; DP would eat the signal). Routes through the layer for provenance and budget accounting only. Hash lookup is constant-time via the `name_hash` index.
  - `alert_count_for_entity(name_hash: str, window: tuple[date,date], signal_type: SignalType, requester: RequesterKey, rho: float = 0.02) -> (int, rec)` — **DP applied.** Hackathon privacy unit is a clipped transaction contribution, not a full customer-level guarantee. Sensitivity is 1 after enforcing the contribution cap for the queried entity/window. Gaussian mechanism uses σ = sensitivity / sqrt(2ρ). Provenance displays the equivalent ε for fixed δ = 1e-6.
  - `flow_histogram(name_hashes: list[str], window, buckets: list[tuple[float,float]], requester, rho: float = 0.03) -> (list[int], rec)` — **DP applied per bucket.** Each transaction lands in exactly one bucket after clipping. Parallel composition uses the full declared ρ per bucket, paying ρ total; σ per bucket is calibrated with sensitivity 1.0 and full ρ.
  - `counterparty_edge_existence(counterparty_hashes: list[str], window, requester, rho: float = 0.0) -> (dict[hash → bool], rec)` — Binary edge existence per hash. **No DP applied.** Hash lookup over `transactions.counterparty_account_id_hashed`.
  - `pattern_aggregate_for_f2(window, requester, rho: float = 0.04) -> (BankAggregate, rec)` — **DP applied.** Returns a `BankAggregate` of `edge_count_distribution` (histogram of edge counts on hashed counterparties) and `bucketed_flow_histogram`. ρ is split between edge and flow components because they share underlying transactions; within each component, parallel composition uses the full component ρ per bucket. Edge-count sensitivity is L2 `sqrt(2)`, and flow sensitivity is 1.0. This is the input to F2.
- *`RequesterKey`:* `{requesting_investigator_id, requesting_bank_id, responding_bank_id}`. The budget ledger keys debits by this triple so a single investigator can't drain budget across multiple peer banks' allowances independently.
- *Budget ledger:*
  - Internal budget unit is ρ, not ε. The default session cap is `rho_max` per `(requesting_investigator, this_bank, peer_bank_destination)` triple. The UI converts cumulative ρ to an approximate `(ε, δ)` display value using fixed δ = 1e-6.
  - Each Gaussian-mechanism call debits its declared ρ after the primitive's SQLite read and OpenDP calibration, but before drawing noise, so budget-refusal paths do not advance RNG state and audit replay remains deterministic. If the noise backend fails after a committed debit, the budget is spent. The ledger sums ρ values and refuses when cumulative ρ would exceed `rho_max`. Do not mix the approximate-DP σ formula with this ledger; the zCDP Gaussian calibration is σ = sensitivity / sqrt(2ρ).
  - On exhaustion: every DP primitive call from that requester returns `PrimitiveResult(refusal_reason="budget_exhausted")`. The refusal is structural; A3 cannot retry around it.
  - Budget is per-session by default (resets when the orchestrator restarts) but the ledger has a persistence hook for production use.
- *Provenance:* every `PrimitiveCallRecord` carries `field_name`, `primitive_name`, `args_hash` (SHA-256 of canonical JSON of the args — for audit-replay if needed), `privacy_unit`, `rho_debited`, approximate `(ε, δ)` display value, `sigma_applied` (None for non-DP primitives), `sensitivity`, `returned_value_kind`, `timestamp`. A3 attaches the records to its outbound `Sec314bResponse.provenance`.
- *Approach:* light OpenDP integration. `backend/silos/dp.py` uses OpenDP's Gaussian privacy map to validate the local `sigma = sensitivity / sqrt(2ρ)` calibration, while NumPy provides an injectable RNG so tests are deterministic. zCDP-to-approx-DP display conversion is explicit in code. The SQLite reads are plain parameterized SQL — never LLM-generated.
- *Out of scope for this part:* no LLM, no agent code, no LT integration, no cross-bank messaging. Pure deterministic primitives. The "binary presence" primitives still route through this layer because we want every cross-bank-bound numeric value to carry provenance.
- *Acceptance:*
  - **`tests/test_stats_primitives.py`** instantiates against `data/silos/bank_alpha.db`. For each primitive: call it with a known input 200 times; verify (a) the empirical mean of the noised output matches the analytical true value within 3 standard errors, (b) the empirical variance matches σ² within a statistically reasonable tolerance, (c) non-DP primitives return identical values across calls, (d) contribution clipping is enforced before noise is applied.
  - **`tests/test_dp_composition.py`** debits a fixed ρ across N primitive calls; verifies the ledger sums via zCDP composition; the (N+1)th call after budget exhaustion returns the refusal record.
  - **`tests/test_budget.py`** verifies (a) different `RequesterKey` values share no budget, (b) the same investigator querying two banks debits each bank's allowance independently, (c) persistence-hook is exercised by a round-trip serialize/deserialize.
- *Risks specific to this part:* (a) OpenDP installation can be heavy (compiles Rust); mitigation: pin to a binary wheel in pyproject; document the fallback to hand-rolled Gaussian + simple rho-counter (the "cut order" knob in Section 11). (b) Calibration mistakes (wrong sensitivity) silently leak privacy; mitigation: hardcode sensitivity per primitive, test it analytically rather than declaring it. (c) Float-precision drift in σ across calls makes audit-replay non-deterministic; mitigation: round σ to 6 decimal places for provenance records.
- *Depends on:* P3 (data), and the `opendp` Python package (new dependency, added to `pyproject.toml`).
- *Scope check:* one to two focused sessions. The DP arithmetic is short but the test suite is the bulk of the work — get the empirical-σ tolerances right.
- *What was built:* `backend/silos/budget.py` defines `RequesterKey`, `BudgetDebit`, `BudgetSnapshot`, and `PrivacyBudgetLedger` keyed by requesting investigator, requesting bank, and responding bank, with a thread lock around ledger reads/writes and a delimiter-safe stable key. `backend/silos/dp.py` implements zCDP Gaussian sigma math, approximate `(ε, δ)` display conversion, OpenDP privacy-map validation, and deterministic RNG injection. `backend/silos/stats_primitives.py` implements the five bank-local primitives over SQLite, `DateWindow`, and `PrimitiveResult`. DP primitives check budget before work, debit budget after SQLite reads and OpenDP calibration but before noise sampling, return structural refusals on exhaustion, and emit provenance records with args hashes, sensitivity, rho, sigma, and returned value kinds.
- *Acceptance (current):* `uv run pytest tests/test_budget.py tests/test_dp_composition.py tests/test_stats_primitives.py` passes 24 focused P7 tests. These cover rho composition and budget refusal, budget-key isolation and snapshot round-trip, delimiter-collision resistance, OpenDP Gaussian map agreement across the full rho range, explicit parallel-composition checks for histogram bucket accounting, serial composition between F2 aggregate components, empirical Gaussian mean/variance with seeded RNG, exact non-DP entity and counterparty primitives, DP metadata on alert counts and histograms, F2 bank aggregate shape, structural budget exhaustion refusal, runtime hash-list caps, database connection closure, stable args hashing, serialized concurrent DP primitive calls, no budget debit when a DP primitive fails before debit, no RNG advance on budget refusal, and budget-spent behavior when noise sampling fails after debit. `uv run pytest` passes the full 133-test suite.

**P8 - A2 investigator agent**

- *Goal:* The protagonist. Full LLM agent that consumes `Alert` from local A1, decides whether to investigate, dismiss, or escalate cross-bank, drafts `Sec314bQuery` messages with proper purpose declarations, and synthesizes peer responses into SAR or dismissal recommendations. A2 runs outside the TEE and has no raw DB or P7 handle.
- *Files:* `backend/agents/a2_investigator.py`, `backend/agents/prompts/a2_triage.md`, `backend/agents/prompts/a2_query.md`, `backend/agents/prompts/a2_synthesis.md`, `backend/agents/a2_states.py` (the explicit state machine), `tests/test_a2.py`.
- *State machine (each transition is a Gemini call with its own structured output target):*
  1. **`triage`** - input: incoming `Alert`. Output: `TriageDecision { action: "dismiss" | "escalate_cross_bank", reason }`. Uses only alert evidence and safe local summaries, not raw SQL.
  2. **`cross_bank_query`** - only entered when the LLM decides to escalate. Drafts a `Sec314bQuery` with a structured `PurposeDeclaration`. Picks one of the three query shapes from P4 (entity_presence, aggregate_activity, counterparty_linkage). The query draft is shape-specific: entity and aggregate queries use `name_hashes`; counterparty linkage uses `counterparty_hashes`. Sent to F1.
  3. **`synthesize`** - entered when the aggregated `Sec314bResponse` arrives from F1. Reasons about whether peer-bank signals corroborate the local suspicion. Decides between SAR-draft contribution and dismiss.
  4. **`recommend_sar_or_dismiss`** - emits either `SARContribution -> F4` or `DismissalRationale -> F5`.
- *Rule bypasses:* implement `A2-B1` and `A2-B2` from the Section 8.3 bypass rule catalog. `A2-B1` emits an aggregate-activity `Sec314bQuery` when the current alert plus safe alert-history summaries show at least three alerts on the same `name_hash` in 30 days. `A2-B2` treats `SANCTIONS_MATCH` as a hard escalation and emits a `SARContribution` directly unless later F3 evidence supersedes this path.
- *Rule constraints (LLM cannot override):*
  - Cannot include customer-name strings in `Sec314bQuery`, `SARContribution`, or `DismissalRationale`.
  - Cannot send `Sec314bQuery` without a populated `PurposeDeclaration`.
  - Cannot use a hash token unless it appears in the matching alert evidence field for the selected query shape.
  - Cannot synthesize a peer response unless the original query belongs to this A2, belongs to this bank, is bound to the same investigator, and lists the local alert id in `supporting_alert_ids`.
  - Cannot escalate to SAR without a peer-bank corroborating signal, unless the alert is a hard-bypass sanctions case.
  - Cannot answer incoming peer `Sec314bQuery` messages.
  - Cannot call P7 or read raw transactions directly.
- *Approach (Gemini calls):* `gemini-2.5-pro` for cross-bank-query drafting and synthesis (structured output reliability matters). Each state's system prompt is in a separate Markdown file under `backend/agents/prompts/`. The agent base class's retry plumbing handles structured-output JSON errors.
- *Out of scope for this part:* no F1 routing (P9), no A3 peer-response logic (P8a), no orchestrator state management (P15). A2 is a state machine that takes one input and returns one output per turn; the orchestrator drives state transitions.
- *Acceptance:* `tests/test_a2.py`:
  - **Test 1 (outbound query):** feed A2 a known S1-related alert; A2 emits a `Sec314bQuery` with a populated `PurposeDeclaration.typology_code = "structuring"`; the query passes a customer-name-redaction check; `target_bank_ids` includes the two peer banks.
  - **Test 2 (response synthesis):** feed A2 an aggregated `Sec314bResponse` with corroborating peer evidence; A2 emits a `SARContribution` that references the originating query id.
  - **Test 3 (dismissal path):** feed A2 an aggregated `Sec314bResponse` with no fields and no corroborating peer evidence; A2 emits a `DismissalRationale`.
  - **Test 4 (bypass test):** feed A2 an alert with 3 correlated `name_hash` history records; A2 emits a `Sec314bQuery` regardless of LLM judgment.
  - **Test 5 (separation guard):** attempting to route an incoming peer `Sec314bQuery` to A2 is rejected by the agent or policy adapter before any LLM call.
  - **Test 6 (shape guard):** counterparty-linkage drafts must use `counterparty_hashes`; entity and aggregate drafts must use `name_hashes`.
  - **Test 7 (lineage guard):** peer responses must bind to this A2's original query, investigator id, bank id, and supported local alert id before synthesis.
- *What was built:* `backend/agents/a2_states.py` defines strict Pydantic state models for alert turns, peer-response turns, rejected inbound-query turns, LLM triage decisions, shape-specific query drafts, synthesis decisions, and `A2TurnResult`. `backend/agents/a2_investigator.py` implements the A2 state machine, deterministic A2-B1/A2-B2 bypasses, one-repair structured-output handling for triage/query/synthesis calls, shape-aware construction of `Sec314bQuery`, strict construction of `SARContribution` and `DismissalRationale`, past-only correlated-alert bypass counting, response/query/alert lineage checks before peer-response synthesis, and deterministic rejection of inbound peer queries before any LLM call. `shared/messages.py` adds `SARContribution.related_query_ids` so A2 SAR contributions can reference the originating 314(b) query. The three A2 prompts live under `backend/agents/prompts/`.
- *Acceptance (current):* `uv run pytest tests/test_a2.py` passes 16 focused P8 tests: outbound aggregate query from an S1-style alert, counterparty-linkage query draft construction, query-draft shape validation, corroborating peer response to SAR contribution with `related_query_ids`, empty peer response to dismissal without an LLM call, A2-B1 correlated-alert bypass, future-correlated-alert suppression, inbound peer-query rejection before LLM, A2-B2 sanctions hard escalation, hallucinated name-hash retry/blocking, hallucinated counterparty-hash retry/blocking, response/query id mismatch blocking, original-query ownership blocking, supporting-alert lineage blocking, customer-name draft rejection, and malformed triage repair. `uv run pytest tests/test_messages.py tests/test_agent_base.py tests/test_a1.py tests/test_a2.py` passes 101 focused schema/runtime/A1/A2 tests. `uv run pytest` passes the full 133-test suite.
- *Risks specific to this part:* (a) A2 can overclaim based on thin evidence. Mitigation: SAR contribution requires at least one corroborating `Sec314bResponse`. (b) Keeping A2 outside the data plane makes local context thinner. Mitigation: A1 alert evidence carries safe summaries; richer local evidence can be added later through an explicit internal request to A3, not by giving A2 a DB handle.
- *Depends on:* P3 (data), P5 (base class), P6 (uses A1 alerts as input).
- *Scope check:* one to two focused sessions. The state machine is smaller after the A3 split.

**P8a - A3 silo responder agent**

- *Goal:* Full LLM agent inside each bank trusted boundary that answers approved peer `Sec314bQuery` messages by selecting P7 primitives, invoking them, and composing a provenance-backed `Sec314bResponse`. A3 is the only LLM-backed agent with a P7 handle.
- *Files:* `backend/agents/a3_silo_responder.py`, `backend/agents/prompts/a3_system.md`, `backend/agents/a3_states.py`, `tests/test_a3.py`.
- *State machine:*
  1. **`validate_inbound_query`** - deterministic guard. Requires F1 as sender, valid purpose declaration, target bank matching this bank, valid signed envelope, fresh nonce, matching `RouteApproval`, and no customer-name strings.
  2. **`select_primitives`** - Gemini maps the typed `query_shape` and payload to one or more allowed P7 primitive calls.
  3. **`invoke_primitives`** - deterministic code calls P7, handles budget refusal, and collects `(value, PrimitiveCallRecord)` tuples.
  4. **`compose_response`** - Gemini writes the minimal `Sec314bResponse` fields and rationale from the primitive results. The constraint layer rejects any field without matching provenance.
- *Rule bypasses:* implement `A3-B1` through `A3-B3` from the Section 8.3 bypass rule catalog.
- *Rule constraints (LLM cannot override):*
  - Cannot call primitives outside the allowlist for the query shape.
  - Cannot pass broad discovery arguments such as all known hashes; P7 caps list sizes and A3 checks them first.
  - Cannot return customer names, raw account ids, raw transactions, or unprovenanced values.
  - Cannot answer if the approved query body hash does not match the received query body.
  - Can only send `Sec314bResponse` to F1.
- *Approach (Gemini calls):* `gemini-2.5-flash` is enough for primitive selection and compact response composition. Deterministic code owns all value computation and budget checks.
- *Acceptance:* `tests/test_a3.py`:
  - **Test 1 (entity presence):** feed A3 an approved `entity_presence` query; A3 calls `count_entities_by_name_hash`; response fields and provenance match.
  - **Test 2 (budget exhaustion):** mock P7 budget exhaustion; A3 returns `refusal_reason="budget_exhausted"`, empty fields, empty provenance, and does not call Gemini.
  - **Test 3 (routing guard):** query from anything other than F1 is rejected before any primitive call.
  - **Test 4 (MITM guard):** tamper with the query body after F1 approval; A3 rejects the request before any primitive call.
  - **Test 5 (provenance guard):** mock Gemini adding an extra field; A3 retries once and then refuses if the field still lacks provenance.
- *Risks specific to this part:* (a) The LLM may try to broaden primitive arguments. Mitigation: hard argument caps in A3 plus P7. (b) The extra A3 role adds runtime plumbing. Mitigation: keep A3 stateless and only reachable through F1.
- *Depends on:* P4 (with A3 role added), P5, P7.
- *Scope check:* one focused session after P7.

**P9 — F1 cross-bank coordinator**

- *Goal:* Full LLM agent that receives `Sec314bQuery` from one bank's A2, validates the purpose declaration, broadcasts redacted queries to relevant peer banks' A3 silo responders, collects responses, and forwards an aggregated `Sec314bResponse` back to the requester. F1 is the gatekeeper: every cross-bank message passes through it.
- *Files:* `backend/agents/f1_coordinator.py`, `backend/agents/prompts/f1_system.md`, `tests/test_f1.py`.
- *Inputs:* `Sec314bQuery` from any bank's A2.
- *Outputs:* one redacted `Sec314bQuery` per target peer A3 (sent via orchestrator); one aggregated `Sec314bResponse` back to the original requester after peer responses come in; a `GraphPatternRequest` to F2 when the query shape indicates pattern detection; a `SanctionsCheckRequest` to F3 in parallel when the query references hashes that look like potential SDN matches.
- *Approach (Gemini calls):*
  1. **Purpose-declaration validation** — Gemini reads the `PurposeDeclaration` and returns `{valid: bool, reason}`. `F1-B1` short-circuits this before the LLM call.
  2. **Target-bank selection** — LLM reasons about which peer banks the query is relevant to (e.g., a S2-shaped query about Alpha+Beta need not broadcast to Gamma). Returns `target_bank_ids` (must be a subset of the requester's stated targets — constraint).
  3. **Route approval** — deterministic code signs a `RouteApproval` per responding bank, binding the responder, the original `query_id`, and the approved query body hash.
  4. **Redaction** — LLM rewrites the query body for peer consumption. Customer names should already be absent (constraint at A2 + LT redaction in transit); F1 also strips any `requesting_investigator_id` that isn't strictly necessary for the peer to answer.
  5. **Aggregation** — when peer responses arrive, F1 verifies response signatures and composes a single `Sec314bResponse` to the requester. Provenance from each peer is preserved verbatim; aggregate `rho_debited_total` is the sum across peer responses.
- *Rule bypasses:* implement `F1-B1` through `F1-B3` from the Section 8.3 bypass rule catalog.
- *Rule constraints:*
  - Cannot retain customer identifiers between queries (F1 is stateless across queries — enforced by clearing state per call).
  - Cannot forward a query without a valid `PurposeDeclaration`.
  - Cannot expand `target_bank_ids` beyond what the requester specified.
  - Cannot forward a query without a valid signed envelope and route approval.
- *State:* F1 has no persistent state between queries. The in-flight state (waiting for N peer responses to a given query) is held by the orchestrator (P15), not by F1.
- *Out of scope for this part:* no DP — F1 doesn't do statistics; it routes them. No SAR drafting. No live audit consumption (F5's job).
- *Acceptance:* `tests/test_f1.py`:
  - Given a valid `Sec314bQuery` from Bank Alpha targeting both peers, F1 emits two redacted queries (one each to Beta and Gamma) with the customer-name-redaction check passing on both.
  - Given a valid routed query, F1 attaches a `RouteApproval` whose approved query hash matches the canonical forwarded body.
  - Given a query with empty `PurposeDeclaration.suspicion_rationale`, F1 returns a refusal — LLM is never called.
  - Given a query referencing an SDN-equivalent hash, F1 emits a `SanctionsCheckRequest` to F3 in parallel (asserted via orchestrator stub).
  - Given two peer `Sec314bResponse` objects, F1 returns an aggregated `Sec314bResponse` whose `provenance` is the concatenation of the inputs' provenance and `rho_debited_total` is the sum.
- *Risks specific to this part:* (a) the LLM may broadcast more widely than needed ("when in doubt, ask everyone") — mitigation: prompt says minimize peers; constraint caps at requester-stated targets. (b) Aggregation logic could lose provenance — mitigation: strict Pydantic validation of the aggregated response.
- *Depends on:* P5, P8, P8a.
- *Scope check:* one focused session.

**P10 — F3 sanctions / PEP screening agent**

- *Goal:* Full LLM agent that receives entity hashes and returns binary match flags against a mock SDN watchlist + PEP relation indicators. Simple by design — this agent ships before F2 because it's the cleanest exercise of the agent base class on a federation-layer agent.
- *Files:* `backend/agents/f3_sanctions.py`, `backend/agents/prompts/f3_system.md`, `data/mock_sdn_list.json` (10 well-known fictional names + the S1-D PEP entity's hash), `tests/test_f3.py`.
- *Mock SDN list shape:* `{entities: [{name_hash, source: "SDN"|"PEP", notes}]}` — `notes` is a non-disclosed field (informational only; never returned). F3 only emits boolean flags.
- *Inputs:* `SanctionsCheckRequest { entity_hashes }` from A2 or F1.
- *Outputs:* `SanctionsCheckResponse { results: dict[hash → {sdn_match, pep_relation}] }`. No list contents leaked.
- *Approach (Gemini call):* the LLM's job is fuzzy-match reasoning — in production this would consider name variants, transliteration, alias chains. For the demo, the mock list is keyed by exact `name_hash` so the LLM is mostly confirming exact matches. The prompt instructs the LLM to also return uncertainty when a hash matches a known SDN root but with a relation indicator (parent company, beneficial owner, etc.). The structured output is the response schema.
- *Rule bypasses:* implement `F3-B1` and `F3-B2` from the Section 8.3 bypass rule catalog.
- *Rule constraints:*
  - Output schema strictly excludes list contents — `notes` and `source` from the mock list never appear in `SanctionsCheckResponse`.
  - Cannot retain queried entity hashes between requests (stateless).
- *Out of scope for this part:* no real OFAC integration; no fuzzy-match upgrade beyond exact hash + LLM judgment; no list update / refresh mechanism.
- *Acceptance:* `tests/test_f3.py`:
  - Querying the S1-D PEP entity's `name_hash` returns `pep_relation=True` via the bypass.
  - Querying a random non-list hash returns `sdn_match=False, pep_relation=False`.
  - Output schema verified to exclude `notes` and `source` fields from the mock list.
  - Querying a batch of 10 hashes returns results for all 10.
- *Risks specific to this part:* (a) the LLM may hallucinate a match if the prompt isn't tight — mitigation: explicit "only flag matches that exist in the provided list" instruction + structured output schema that's clear. (b) `mock_sdn_list.json` content should be obviously fictional to avoid any real-name collisions — mitigation: derive the names from a published "well-known fictional names" template.
- *Depends on:* P5.
- *Scope check:* one short focused session — F3 is the simplest federation-layer agent.

**P11 — F2 graph-analysis agent**

- *Goal:* Full LLM agent that consumes DP-noised cross-bank pattern aggregates from F1 and identifies ring structures. This is the agent that detects the planted S1 ring in the demo's hero moment.
- *Files:* `backend/agents/f2_graph_analysis.py`, `backend/agents/prompts/f2_system.md`, `backend/agents/f2_typologies.py` (typology pattern definitions — used by both the LLM prompt and the bypass rules), `tests/test_f2.py`.
- *Inputs:* `GraphPatternRequest { pattern_aggregates: list[BankAggregate], window_start, window_end }`. Each `BankAggregate` arrives already DP-noised (computed by the originating bank's P7 `pattern_aggregate_for_f2` primitive); F2 never sees raw transactions.
- *Outputs:* `GraphPatternResponse { pattern_class, confidence, suspect_entity_hashes, narrative }`.
- *Approach (Gemini call):*
  1. The LLM reasons over the three per-bank aggregates as JSON. Each aggregate has an `edge_count_distribution` (how many edges have how many transactions, keyed by hashed counterparty pair) and a `bucketed_flow_histogram`.
  2. Cross-bank pattern detection: the LLM looks for hashed counterparties that appear in multiple banks' aggregates with elevated edge counts and similar flow buckets — the structural fingerprint of a structuring ring.
  3. Returns `pattern_class`, `confidence`, the suspect hash set, and a regulator-quality narrative (≤500 chars).
- *Rule bypasses:* implement `F2-B1` and `F2-B2` from the Section 8.3 bypass rule catalog. These pattern matchers run on the DP-noised aggregates; calibration is loose enough to survive Gaussian noise at the planted-ring scale. (Verified by the data layer's structural design — ring's signal is much larger than σ at the default rho budget.)
- *Rule constraints:*
  - Cannot see raw transactions (input is DP-noised aggregates only; structurally enforced — F2 has no DB handle).
  - Cannot output customer-name strings (output schema is hash-only).
- *Approach to confidence calibration:* the bypass-surfaced patterns get `confidence ≥ 0.85`. The LLM-only path can return lower confidence for ambiguous patterns. Confidence < 0.4 means "no pattern detected"; ≥ 0.7 means high; in between means medium.
- *Out of scope for this part:* no GNN, no PSI, no per-edge raw-transaction inspection. F2 reasons over aggregates only. (Federated GNN ring detection is research-grade — listed in Section 14.2 future work.)
- *Acceptance:* `tests/test_f2.py`:
  - **Test 1 (S1 detection):** synthesize a `GraphPatternRequest` matching the planted S1 ring's actual aggregate shape (computed offline from the data layer); F2 returns `pattern_class="structuring_ring"`, `confidence >= 0.85`, with `suspect_entity_hashes` covering the 5 S1 entities.
  - **Test 2 (S3 layering):** synthesize S3's aggregate; F2 returns `pattern_class="layering_chain"`, `confidence >= 0.85`.
  - **Test 3 (negative):** synthesize a random-noise aggregate (no planted ring); F2 returns `pattern_class="none"` or `confidence < 0.4`.
  - **Test 4 (DP noise robustness):** run test 1 with 50 different DP-noise draws; ≥45 of 50 still detect the ring. (The planted ring's signal is well above σ at the default rho budget; if this test is flaky, the data-layer ring needs to be larger or rho needs to be relaxed.)
- *Risks specific to this part:* (a) the LLM may hallucinate patterns in pure noise — mitigation: explicit "if you don't see a clear cross-bank pattern, return none" instruction; bypass thresholds are conservative. (b) DP noise at low rho could mask the S2 smaller ring — mitigation: the data layer's S2 is sized so it survives default σ; if not, surface it only when targeted (S2 isn't the demo's hero — S1 is).
- *Depends on:* P5, P9.
- *Scope check:* one to two focused sessions — the typology matchers and the prompt engineering are the bulk of the work.

**P12 — F4 SAR drafter agent**

- *Goal:* Full LLM agent that synthesizes `SARContribution` messages from A2s + F2's pattern report + F3's sanctions findings into a structured Suspicious Activity Report draft. Per-bank contribution attribution and §314(b) authority references are mandatory.
- *Files:* `backend/agents/f4_sar_drafter.py`, `backend/agents/prompts/f4_system.md`, `shared/sar_template.py` (the mandatory-fields skeleton + FinCEN typology code enum), `tests/test_f4.py`.
- *Inputs:* one or more `SARContribution` records (from one or more A2s), an optional `GraphPatternResponse` from F2, an optional `SanctionsCheckResponse` from F3.
- *Outputs:* `SARDraft` with the schema from P4. The narrative is LLM-authored; the structured fields are deterministically computed from the contributions.
- *Mandatory structured fields (deterministic, not LLM-generated):*
  - `filing_institution` — the bank whose A2 first emitted the SARContribution
  - `suspicious_amount_range` — (min, max) in cents, computed from the contributing-evidence amounts
  - `typology_code` — derived from F2's `pattern_class` (`structuring_ring` → FinCEN typology "structuring"; `layering_chain` → "layering")
  - `contributors` — one entry per contributing bank with the bank_id, investigator_id (kept internal to the SAR, not exposed cross-bank), and a short summary of evidence contributed
  - `related_query_ids` — the §314(b) queries that produced the cross-bank evidence
- *LLM-authored narrative:* a 200–400 word account suitable for regulator review. Must reference: (a) the §314(b) authority underlying the cross-bank information sharing, (b) which evidence came from which bank (using bank_ids, not customer names), (c) the typology and confidence from F2, (d) any sanctions/PEP findings from F3.
- *Rule bypasses:* implement `F4-B1` and `F4-B2` from the Section 8.3 bypass rule catalog.
- *Rule constraints:*
  - Cannot include customer-name strings (uses hashes + bank_ids only).
  - Narrative must include the §314(b) authority phrase.
- *Approach (Gemini call):* `gemini-2.5-pro` for the narrative (regulator-quality language matters); deterministic Python for the structured fields. Single Gemini call per SAR draft.
- *Out of scope for this part:* no actual FinCEN submission API (we draft, not file); no per-state SAR variations; no SAR amendment workflow.
- *Acceptance:* `tests/test_f4.py`:
  - Given S1-flow contributions (3 contributing banks, $795K total flow) + F2 ring report + F3 PEP flag, F4 emits a `SARDraft` with all mandatory fields populated; `typology_code="structuring"`; `sar_priority="high"` (because of PEP); `contributors` has 3 entries; narrative references §314(b) and references each bank by bank_id.
  - Given a contribution missing the amount field, F4 emits a `SARContributionRequest` to the contributor rather than producing an incomplete SAR.
  - Narrative passes a customer-name-redaction check.
- *Risks specific to this part:* (a) the LLM may invent details for the narrative - mitigation: prompt constrains the LLM to only reference facts present in the inputs; constraint check rejects narratives that introduce values not in the structured fields. (b) The narrative is long enough that Gemini latency may be visible in the demo - mitigation: stream the response into the judge console; pre-generate during dry-runs as a fallback.
- *Depends on:* P5, P8, P10, P11.
- *Scope check:* one to two focused sessions. The narrative prompt engineering is the bulk.

**P13 — F5 compliance auditor agent**

- *Goal:* Full LLM agent that subscribes to the live audit stream and reasons about whether agent behavior pattern-matches a fishing expedition, a §314(b) purpose mismatch, or a sustained-abuse pattern. Emits compliance annotations and `HUMAN_REVIEW` escalations.
- *Files:* `backend/agents/f5_compliance_auditor.py`, `backend/agents/prompts/f5_system.md`, `tests/test_f5.py`.
- *Inputs:* a streaming sequence of `AuditEvent` records from any object implementing an `AuditSource` protocol (`subscribe() -> AsyncIterator[AuditEvent]`). Unit tests use an in-memory source; P15 later wires F5 to the orchestrator's real audit channel.
- *Outputs:* `AuditEvent` records of kind `human_review` or `rate_limit`, plus a periodic `AuditSummary` digest (every N events or every 30 seconds, whichever first).
- *Approach (Gemini call):*
  - F5 batches incoming events into windows (e.g., the last 60 seconds of activity). For each window, it sends the structured event list to Gemini with a prompt asking "does anything here exceed §314(b) authorization or pattern-match a fishing expedition?"
  - The structured output is `F5BatchResult { findings: list[F5Finding] }` where each finding has a kind, a referenced event_id, and a rationale.
  - F5 emits each finding as an `AuditEvent`.
- *Rule bypasses:* implement `F5-B1` and `F5-B2` from the Section 8.3 bypass rule catalog.
- *Rule constraints:*
  - Read-only on the audit stream (cannot block or modify agent behavior).
  - Cannot suppress audit events from being logged.
  - Cannot retain customer identifiers (they wouldn't be in the audit stream anyway — but the constraint is enforced for defense in depth).
- *Approach to "fishing expedition" detection:* the LLM looks for patterns like: many `Sec314bQuery` events from one investigator without any resulting `SARContribution`; a single investigator querying about many unrelated `name_hash` values in succession; queries with vague or boilerplate `suspicion_rationale` strings.
- *Out of scope for this part:* no automatic remediation — F5 only annotates; humans (or future tooling) act on the annotations. No persistent audit-history store beyond what the orchestrator keeps.
- *Acceptance:* `tests/test_f5.py`:
  - **Test 1 (rate limit):** synthesize a stream of 11 `Sec314bQuery` events from one investigator within 60 minutes; F5 emits a `rate_limit` AuditEvent referencing the 11th query.
  - **Test 2 (purpose mismatch):** synthesize a `Sec314bQuery` with `suspicion_rationale = "we're curious about this customer"`; F5 emits a `human_review` annotation regardless of LLM judgment.
  - **Test 3 (LLM-judgment fishing pattern):** synthesize 5 queries from one investigator referencing 5 unrelated `name_hash` values without any follow-up SAR contributions; F5 emits a `human_review` with the LLM-authored rationale.
  - **Test 4 (no false alarms):** synthesize a normal canonical-flow audit stream; F5 emits no `human_review` annotations.
- *Risks specific to this part:* (a) the LLM may over-flag (every query looks like a fishing expedition to a cautious model) — mitigation: prompt explicitly says "normal investigative behavior is not a fishing expedition; only flag specific anomalies." Test 4 catches over-flagging. (b) F5's batching window introduces latency in the demo; mitigation: tune window to 5–10 seconds for demo runs; document the tradeoff.
- *Depends on:* P4, P5. P15 later wires the already-built F5 listener into the live orchestrator audit channel.
- *Scope check:* one to two focused sessions.

---

### Integration parts (P14–P18)

**P14 — AML policy adapter + Lobster Trap overlay**

- *Goal:* Add AML-specific governance without assuming unsupported LT behavior. Current LT gives us generic prompt inspection, block/allow/HUMAN_REVIEW decisions, `_lobstertrap` response metadata, and JSONL audit logs. The AML-specific behavior lives in our Python policy adapter unless and until LT grows first-class support for that rule type.
- *Files:* `backend/policy/__init__.py`, `backend/policy/aml.py` (message-level policy adapter), `backend/policy/redaction.py` (demo-grade synthetic-name redactor), `backend/policy/dictionaries/aml_terms.json` (typology codes, ML/TF keywords, synthetic customer-name surface patterns), `infra/lobstertrap/aml_overlay_policy.yaml` (optional LT overlay limited to supported LT fields/actions), `scripts/aml_policy_smoke.py`, `tests/test_aml_policy.py`.
- *Division of responsibility:*
  - **Lobster Trap:** generic prompt injection, jailbreak, obfuscation, exfiltration, credential/PII leakage, sensitive path, and response metadata/audit logging.
  - **Python AML policy adapter:** role-based message routing, customer-name redaction, §314(b) purpose-declaration validation, signed-envelope verification, replay/idempotency checks, cross-bank rate-limit advisory events, and normalization of LT JSONL records into P4 `AuditEvent` objects.
- *Policy rules in the Python adapter:*
  - **Role-based routing:** an A1 message whose `recipient_agent_id` is anything other than the local A2 is rejected with `PolicyDecision(action="deny", reason="role_violation")`. A2 may send `Sec314bQuery` only to F1. F1 may send approved `Sec314bQuery` messages only to peer A3 responders. A3 may send `Sec314bResponse` only to F1. F-agents follow their declared message routes.
  - **Signed-envelope check:** cross-boundary messages must have a valid signature, body hash, signing key id, unexpired timestamp, and fresh nonce.
  - **Request/response binding:** `Sec314bResponse.in_reply_to` and approved query hashes must match the original `Sec314bQuery`; mismatches are denied as possible tampering.
  - **Customer-name redaction:** any outbound `Sec314bQuery`, `Sec314bResponse`, or SAR narrative field is scanned against the synthetic-name dictionary and simple organization-name patterns. Matches are replaced with `[REDACTED_NAME]`; the audit event records that redaction occurred but never logs the original substring.
  - **Purpose-declaration check:** outbound `Sec314bQuery` without non-empty `purpose_declaration.suspicion_rationale` or without a valid `typology_code` from the enum is denied before any LLM call.
  - **Audit normalization:** every cross-bank message, redaction, denial, LT verdict, and rate-limit advisory emits a P4 `AuditEvent`.
  - **Rate-limit advisory:** >20 `Sec314bQuery` events from one `requesting_investigator_id` in 1 hour emits a `rate_limit` advisory event. F1 still performs any deterministic blocking decision.
- *LT overlay:* if useful, add extra LT YAML rules for generic AML keyword logging or malformed-purpose prompts using currently supported fields/actions only. Do not depend on LT `MODIFY`, header-aware routing, `extends`, or audit-event templates unless those capabilities are verified in the checked-out LT version.
- *Out of scope for this part:* no upstream LT feature work; no production NER redactor; no automatic remediation (F5 annotates, humans act).
- *Acceptance:* `tests/test_aml_policy.py`:
  - Positive: a well-formed `Sec314bQuery` from A2 with valid purpose passes and emits a normalized audit event.
  - Negative (role): an A1 trying to send to a peer bank is denied by the Python adapter before the LLM/proxy call; audit event kind is `constraint_violation` or `role_violation`.
  - Negative (separation): an incoming peer `Sec314bQuery` addressed to A2 is denied; the same query addressed to that bank's A3 passes routing if the purpose is valid.
  - Negative (MITM): a signed query whose body is modified after signing is denied before any LLM or P7 call.
  - Negative (replay): a previously accepted nonce is denied on the second use.
  - Negative (redaction): a `Sec314bQuery` body containing the literal string `"Acme Holdings LLC"` is rewritten to `"[REDACTED_NAME]"`; the normalized audit event does not contain the original string.
  - Negative (purpose): a `Sec314bQuery` with empty `suspicion_rationale` is denied by the adapter.
  - LT normalization: a captured LT `_lobstertrap` response and a JSONL audit entry convert into P4 `AuditEvent` without losing request_id, verdict, action, or rule_name.
  - Rate limit: 21 `Sec314bQuery` events from one investigator within 60 minutes emits an advisory audit event on the 21st.
- *Risks specific to this part:* (a) name-pattern regex is fragile — too broad redacts legitimate text, too narrow misses names. Mitigation: keep the dictionary scoped to the synthetic dataset's exact fictional name forms; document this as demo-grade and name production NER as future work. (b) LT's native audit format may differ from P4's `AuditEvent` schema — mitigation: normalization lives in `backend/policy/aml.py` or `backend/audit.py`, not in the LT process.
- *Depends on:* P4 (message schemas).
- *Scope check:* one focused session.

**P15 - Agent orchestrator / message bus + UI control API**

- *Goal:* Runtime that can run in two modes: local deterministic mode for tests and cloud-demo mode with explicit nodes for each silo, investigator, and federation stack. Local mode instantiates all 14 agent instances in one process. Cloud-demo mode deploys separate service processes for the three A3 silo nodes, the A2 investigator nodes, and the F1-F5 federation node; messages cross service boundaries through signed envelopes and each node's local Lobster Trap/LiteLLM stack. The orchestrator also exposes a judge-safe control API so the UI can start, step, pause, inspect, and inject negative probes anywhere in the stack without bypassing policy.
- *Files:* `backend/orchestrator.py`, `backend/audit.py` (audit channel implementation, including AuditEvent ringbuffer + SSE-style subscriber API for the web UI), `backend/inbox.py` (per-agent inbox), `backend/runtime/node_config.py` (node identity, service URLs, trust-domain config), `backend/runtime/transport.py` (HTTP/gRPC transport abstraction), `backend/demo/state.py` (scenario/run snapshots for UI inspection), `backend/demo/control_api.py` (FastAPI or Typer-backed control facade), `tests/test_orchestrator.py`, `tests/test_demo_control_api.py`.
- *Architecture:*
  - **Local mode:** in-process message bus for fast tests and deterministic demo dry-runs. Each agent instance holds an inbox (`asyncio.Queue`); the bus has a routing table keyed by `recipient_agent_id`.
  - **Cloud-demo mode:** each trust domain runs as a service with a local policy/LLM/security stack. Bank silo nodes run `A3 + P7 + local DB + local LT/LiteLLM + policy adapter + envelope verifier + replay cache + audit forwarder`. Investigator nodes run `A2 + local LT/LiteLLM + policy adapter + envelope signer/verifier + replay cache`. The federation node runs `F1-F5 + federation LT/LiteLLM + policy adapter + route approval signer + aggregate audit stream + replay cache`.
  - `Orchestrator.__init__()` in local mode instantiates: 3 A1 instances (one per bank), 3 A2 instances (one per bank), 3 A3 instances (one per bank), one each of F1–F5. Wires each bank's A3 to its bank's stats-primitives layer handle.
  - `Orchestrator.step()` is the visible-progression entry point. Each call: pops one message off any non-empty inbox in priority order (alerts → cross-bank-queries → responses → SAR contributions → SAR drafts → audit annotations), routes it to the addressed agent, awaits the agent's return value, fans out any resulting messages to addressed inboxes, emits all AuditEvents to the audit channel, returns.
  - `Orchestrator.run_until_idle()` calls `step()` in a loop until all inboxes are empty (or until a terminal event like a `SARDraft` lands).
- *Judge-safe control API:*
  - `start_scenario(scenario_id, mode)` creates a `ScenarioRun` and returns a `run_id`. Modes: `stub`, `live`, and `live_with_stub_fallback`.
  - `step(run_id)`, `run_until_next_artifact(run_id)`, and `run_until_idle(run_id)` drive the same orchestrator transitions used by tests and scripts.
  - `inspect_component(run_id, component_id)` returns typed snapshots for A1, A2, A3, F1-F5, P7, LT, LiteLLM, policy adapter, inboxes, replay cache, route approvals, and audit channel.
  - `inspect_message(run_id, message_id)` returns envelope metadata, body hash, signature status, LT verdicts, schema validation result, and downstream provenance.
  - `inject_probe(run_id, probe_kind, target_component, payload_patch)` launches a safe negative test such as prompt injection, customer-name leakage, hallucinated hash, MITM body tamper, replay, route mismatch, unsupported query shape, or budget exhaustion.
  - Probe requests are never privileged. They enter through the same public boundary the real attacker would use, and success means a deterministic refusal or audited policy block.
  - `export_run(run_id)` writes timeline JSON, audit JSONL, final artifacts, and a compact human-readable summary.
- *Audit channel (in `audit.py`):*
  - Ringbuffer of `AuditEvent` records (default 10,000 entries).
  - Subscriber API (`audit.subscribe() -> AsyncIterator[AuditEvent]`) for the web UI to consume live.
  - Every message routed by the bus is copied to the audit channel as kind `message_sent`; constraint violations, bypass triggers, rho debits, LT verdicts, signature checks, replay rejections, and route approvals all produce additional events.
  - Audit events form a hash chain through `prev_event_hash` and `event_hash`; tests verify tampering changes the chain head.
- *Bank↔primitives wiring:* on init, the orchestrator constructs each bank's `StatsPrimitivesLayer` (from P7) and passes a handle to that bank's A3 only. A2 receives alert evidence and aggregated responses but no DB or P7 handle.
- *Cloud node wiring:* in cloud-demo mode, no process gets all handles. Each A3 service receives only its own P7 handle and bank database path. The federation service receives only service URLs and public verification keys for A2/A3 nodes. Investigator services receive only F1's URL and verification key.
- *F5 wiring:* F5 is optional at construction time. When enabled, it subscribes to the audit channel via `audit.subscribe()`. F5's findings are themselves AuditEvents (kind `human_review` or `rate_limit`). This avoids a build-order cycle: P13 is tested against an `AuditSource` protocol first, then P15 wires it into the real orchestrator.
- *Out of scope for this part:* no production-grade Kubernetes operator; no multi-region failover; no real bank network connectivity; no agent hot-reload. Cloud-demo mode is for visible trust boundaries, not production operations. The control API is demo-scoped and must not become a privileged bypass path.
- *Acceptance:* `tests/test_orchestrator.py`:
  - Instantiate the orchestrator (with stubbed LLM agents that return canned outputs for predictability); drop a hand-crafted `Alert` into Bank Alpha's A2 inbox; call `run_until_idle()`; verify the audit channel contains at least: the original alert routed, A2's `Sec314bQuery`, F1's broadcasts to peer A3 responders, peer A3s' responses, F1's aggregated response, A2's `SARContribution`, F4's `SARDraft`, and F5's audit annotations.
  - Verify each cross-bank message audit event includes the rho debit from the corresponding primitive call (chained correctly through provenance).
  - Verify tampering with an audit event breaks the audit hash-chain validation.
  - Verify replaying a previously accepted message id or nonce is rejected.
  - Verify cloud-demo node config cannot construct a service that has both `A2` and a P7 handle, or both `F1` and a bank database path.
  - Verify cloud-demo routing sends A2 queries to F1, F1 queries to peer A3 endpoints, A3 responses back to F1, and F1 aggregates back to A2.
  - Verify `step()` is deterministic given stubbed LLM outputs (same sequence of events across runs).
  - Verify UI inspection snapshots expose enough state for every major mechanism without exposing raw peer-bank transactions outside that bank's silo snapshot.
  - Verify every `inject_probe(...)` negative scenario is blocked or refused at the expected layer and emits an audit event.
- *Risks specific to this part:* (a) `asyncio` orchestration is easy to deadlock if priorities are wrong — mitigation: priority queue with explicit ordering; test exhaustively. (b) The audit channel's ringbuffer may overflow during long runs — mitigation: 10K entries is well over the demo's ~50 events; UI handles ringbuffer reads gracefully. (c) Wiring 14 agents + 3 primitives layers is mostly plumbing — keep `__init__` clean by extracting a `bank_setup(bank_id) -> BankRuntime` helper. (d) Cloud-demo mode can consume time fast — mitigation: keep service transport thin and fall back to local mode if deployment work runs hot.
- *Depends on:* P5, P7, P8, P8a, P9, P10, P11, P12, P14. P13 is optional for the first orchestrator pass; when present, it plugs into the `AuditSource` interface built here.
- *Scope check:* one to two focused sessions. Mostly plumbing once the agent contracts are stable.

**P16 — Canonical demo flow script**

- *Goal:* A reproducible script that drives the entire demo flow from a fixed seed without manual UI clicking — for dry-run, screen-recording, and verification.
- *Files:* `backend/demo/__init__.py`, `backend/demo/canonical_flow.py`, `backend/demo/seeds.py` (the deterministic starting-alert specification).
- *Approach:*
  1. Initialize the orchestrator (P15) against the canonical `data/silos/*.db` databases.
  2. Pick a deterministic S1-related starting alert from Bank Alpha — specifically, the alert with the highest severity score on the S1-A entity. (Choice is deterministic given the data layer's seeded RNG; encoded as a `transaction_id` constant in `seeds.py`.)
  3. Drop that alert into Bank Alpha's A2 inbox.
  4. Call `orchestrator.run_until_idle()` (or `step()` in a loop while subscribing to audit events for the UI).
  5. Expect terminal events: an `F4 SARDraft` emitted with `typology_code="structuring"`, `sar_priority="high"`, `contributors` length ≥ 2.
  6. Print the audit stream to stdout (formatted, color-coded) and the final SARDraft to a separate output file.
- *Determinism:* the script uses `LLM_STUB_MODE=1` env var or a `--stub` flag to swap in canned-LLM stub agents for fully-reproducible runs; `--live` uses real Gemini (DP noise still produces small variation in some fields, but high-level outcomes — pattern_class, sar_priority, contributors — are stable).
- *Out of scope for this part:* no interactive web UI (that's P18); no recording mechanics (P21); no test assertions beyond what the script prints (P17 binds the assertions).
- *Acceptance:* `uv run python -m backend.demo.canonical_flow --stub` produces:
  - A SARDraft printed to `out/sar_draft.json` with the expected typology code and contributors.
  - An audit stream of ~30–50 events to stdout (or `out/audit.jsonl` if `--out-file`).
  - Three consecutive runs produce identical outputs under `--stub`; under `--live`, the SARDraft's structured fields are identical, narrative wording may differ.
  - Total runtime under 3 minutes (typically <1 min under `--stub`, <2 min under `--live`).
- *Risks specific to this part:* (a) the chosen starting alert may not deterministically produce an S1 detection across DP-noise variability — mitigation: pick an alert whose evidence chain is robust under the default σ; verify in test 4 of P11. (b) Determinism under `--live` is bounded by Gemini's nondeterminism — mitigation: explicit caveat in the script docstring; structured fields are what matters for the demo's narrative.
- *Depends on:* P14, P15.
- *Scope check:* one focused session.

**P17 — End-to-end smoke test**

- *Goal:* Automated test that runs the canonical flow against live Gemini through the LT/LiteLLM proxy chain. The single test that verifies "everything works together with real LLMs."
- *Files:* `tests/test_e2e_demo.py`.
- *Approach:*
  - Opt-in: marked with `@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="requires live Gemini key")`.
  - Boots the orchestrator with live agents; runs the canonical-flow starting alert; awaits idle.
  - Asserts on the final SARDraft:
    - `typology_code == "structuring"`
    - `sar_priority == "high"` (because of the S1-D PEP)
    - `contributors` includes all three bank_ids
    - Suspect entity hashes overlap with S1's planted name_hashes (loaded from `ground_truth_entities` for the test)
  - Asserts on the audit stream:
    - At least 10 events
    - At least one `rho_debited` event with non-zero rho
    - At least one `lt_verdict` event with verdict=allow
    - Zero `constraint_violation` events on the happy path
    - Zero customer-name strings in any event payload (regex scan)
  - Asserts runtime < 3 minutes (`pytest.fail` otherwise).
- *Out of scope for this part:* no UI testing; no multi-iteration stability testing (that's P21's dry-run × 3); no failure-mode coverage (those are individual agent tests).
- *Acceptance:* `uv run pytest tests/test_e2e_demo.py` passes against live Gemini; full run completes in <180 seconds wall-clock.
- *Risks specific to this part:* (a) Gemini API rate limits could intermittently fail the test — mitigation: documented retry-with-backoff in the agent base class; this test runs once per CI pass. (b) Live Gemini's nondeterminism could flake assertions on edge fields — mitigation: assertions only target structured fields and event-presence checks, not narrative wording.
- *Depends on:* P16.
- *Scope check:* one short focused session.

**P18 - Interactive judge console**

- *Goal:* An interactive web console that lets judges drive, inspect, and safely attack every part of the mechanism. The console shows the federation timeline beat-by-beat with LT verdicts and privacy-budget debits overlaid, but it also exposes component inspectors and probe controls for A1, A2, A3, F1-F5, P7, policy adapters, LT, LiteLLM, inboxes, route approvals, replay cache, audit chain, and final SAR artifacts.
- *Files:* `backend/ui/__init__.py`, `backend/ui/server.py`, `backend/ui/api.py`, `backend/ui/static/` or `frontend/` (web app), `backend/ui/components.py` (shared view models: agent badge, message card, privacy-budget meter with epsilon display, policy verdict panel), `backend/demo/canonical_flow.py` (extended to support `--ui` flag).
- *Primary view layout (browser, 1080p target):*
  ```
  ┌────────────────────────────────────────────────────────────────────┐
  │ FEDERATED AML INVESTIGATION — Bank α / β / γ                        │
  │ Scenario: S1 structuring ring                                       │
  ├──────────────────────────────────┬─────────────────────────────────┤
  │  FEDERATION TIMELINE (60% width) │  AUDIT PANEL (40% width)        │
  │                                  │                                 │
  │  [00:00] α.A1 ──alert──> α.A2   │  Budget meters:                 │
  │  [00:01] α.A2 ──§314b──> F1     │   α→β: 0.4 / 1.0  ████░░░░░░    │
  │  [00:01] F1 ──redacted──> β.A3  │   α→γ: 0.2 / 1.0  ██░░░░░░░░    │
  │  [00:01] F1 ──redacted──> γ.A3  │                                 │
  │  [00:02] β.A3 ──response──> F1  │  LT verdicts (last 5):          │
  │  [00:02] γ.A3 ──response──> F1  │   00:01  allow   §314b purpose  │
  │  [00:02] F1 ──aggregate──> α.A2 │   00:01  redact  customer name  │
  │  [00:03] F1 ──pattern──> F2     │   00:02  allow   response       │
  │  [00:03] F2 ──ring──> F1        │                                 │
  │  [00:03] α.A2 ──sanc──> F3     │  Constraint violations: 0       │
  │  [00:04] F3 ──PEP=yes──> α.A2  │  Bypasses triggered: 0          │
  │  [00:04] α.A2 ──contrib──> F4  │                                 │
  │  [00:05] F4 ──SAR──> orch      │  Human-review flags: 0          │
  └──────────────────────────────────┴─────────────────────────────────┘
  ```
- The block above is a wireframe only. The implementation target is a browser dashboard with resizable panels, inspector drawers, and an attack-lab tab, not a Rich terminal renderer.
- *Implementation notes:* The web server subscribes to the audit channel via `audit.subscribe()` and calls the P15 control API for run, step, inspect, inject, and export actions. Privacy-budget meters display rho plus approximate epsilon values derived from the ledger. Message cards are color-coded by agent role (A1=cyan, A2=green, A3=teal, F1=yellow, F2=magenta, F3=red, F4=blue, F5=white). Long messages collapse by default, with full typed JSON visible in an inspector drawer.
- *Interaction model:*
  - **Run controls:** start scenario, reset, step once, run until next artifact, run until idle, switch stub/live/live-with-stub-fallback.
  - **Component inspectors:** A1 local monitoring, A2 investigation state, F1 routing, each A3 silo response, P7 primitive calls, F2 graph inference, F3 sanctions result, F4 SAR draft, F5 audit findings.
  - **Security probes:** prompt injection, customer-name leakage, hallucinated hash, MITM body tamper, replayed nonce, mismatched route approval, unsupported query shape, and budget exhaustion.
  - **Exports:** audit JSONL, timeline JSON, final SAR draft, and a compact run summary.
- *Out of scope for this part:* no production authentication, no multi-user collaboration, no arbitrary SQL explorer, no UI path that grants the judge privileges unavailable to the real actors. Raw bank transaction inspection is allowed only inside the owning bank silo inspector and is clearly labeled as synthetic demo data.
- *Acceptance:*
  - Running `uv run python -m backend.ui.server --live` starts the judge console and streams the canonical flow in real time; the canonical flow's ~30 events all surface in the correct panes within their actual timestamps.
  - Privacy-budget meter visibly debits per DP-applied query and stops debiting on non-DP primitives.
  - Every inspector is backed by a typed snapshot from P15, not by ad hoc scraping of logs.
  - Each security probe reaches the expected block/refusal layer and creates an audit event visible in the audit panel.
  - Layout readable at 1920×1080 resolution (the screen-recording target).
- *Risks specific to this part:* (a) The UI could sprawl because every layer is interesting. Mitigation: ship one primary run view, one inspector drawer, and one attack lab tab first. (b) The UI could accidentally bypass the architecture it is meant to demonstrate. Mitigation: all actions go through the P15 control API and normal policy checks. (c) Browser polish can consume time fast. Mitigation: use a restrained operational dashboard, no marketing page.
- *Depends on:* P16.
- *Scope check:* one focused session for the layout; another for the polish (colors, spacing, edge cases).

---

### Polish + submission (P19–P22)

**P19 — README + mermaid diagrams for AML**

- *Goal:* The README reads cleanly for someone landing on the repo for the first time; mermaid diagrams reflect the AML architecture; the run instructions reproduce the canonical demo from a fresh clone.
- *Files:* `README.md` (full rewrite of the still-clinical sections — top sections already AML-correct; bottom sections still legacy), `data/README.md`, `docs/aml_architecture.md` (longer-form architectural reference linked from the README).
- *Sections to write or rewrite in `README.md`:*
  - **Top blurb** — already AML-correct (from earlier framing work).
  - **What This Is** — already AML-correct.
  - **Why It Matters** — already AML-correct.
  - **Current Build State** — update to mark P0–P22 status accurately as of submission.
  - **Data** — already AML-correct.
  - **Architecture** — replace the legacy clinical mermaid diagram with AML diagrams. Four diagrams: (1) explicit cloud-demo node topology with one stack per trust domain, (2) high-level federation architecture (investigator nodes ↔ federation node ↔ bank silo nodes), (3) canonical-flow sequence diagram (the 10-step demo flow), (4) trust-boundary diagram (which mechanism polices which boundary).
  - **Privacy Model** — already AML-correct.
  - **P0 Proxy Chain** — already correct.
  - **Running the demo** - concrete commands: `uv sync && data/scripts/build_banks.py && data/scripts/plant_scenarios.py && data/scripts/validate_banks.py && uv run python -m backend.ui.server --live`. Document the `GEMINI_API_KEY` requirement and the offline-stub alternative.
  - **Tests** — `pytest tests/` summary + the opt-in live test.
  - **Project structure** — replace legacy clinical structure with the actual AML structure (backend/agents/, backend/silos/, shared/messages.py, infra/lobstertrap/packs/aml_pack.yaml, etc.).
  - **Cross-vertical applicability** — the slide-deck material as a brief section linking to `plan.md` Section 14.
  - **Acknowledgments** — Veea LT, Gemini, OpenDP, Lobster Trap policy framework, FinCEN published typologies, FFIEC BSA Examination Manual.
  - **License** — TBD likely MIT.
- *Mermaid diagrams (new):*
  - **Federation architecture** — explicit nodes: three bank silo boxes, each containing A3/P7/SQLite/local LT/local LiteLLM/local policy/envelope/replay stack; investigator boxes containing A2/local LT/local LiteLLM; federation box containing F1-F5/federation LT/federation LiteLLM/route signer/aggregate audit. Trust-boundary lines must make clear that F1 is separate from bank silos and that F2-F5 are federation agents, not silo agents.
  - **Canonical flow sequence** — 10-step sequence with the agents on swim-lanes and the LT verdicts as note annotations.
  - **Trust-boundary mapping** — table-style mermaid showing which mechanism polices which boundary (LT for NL channels, schemas for structure, P7 for data plane, DP for aggregate leakage).
- *Out of scope for this part:* no major restructuring beyond replacing the clinical sections; no fluff. The README is reference, not marketing.
- *Acceptance:*
  - A reader who's never seen the repo can run `git clone && uv sync && cp .env.example .env && ${EDITOR} .env && ./run_demo.sh` (or equivalent on Windows PowerShell) and get a working canonical-flow run in <10 minutes (excluding the API key setup).
  - All mermaid diagrams render on GitHub.
  - No remaining clinical references (CHF, OMOP, Synthea, hospitals) outside the explicit `clinical-archive` sections.
- *Risks specific to this part:* (a) the architecture diagrams are easy to over-detail — mitigation: the README diagrams are summary-level; full detail lives in `plan.md` Section 8 and `docs/aml_architecture.md`. (b) Mermaid syntax for the trust-boundary diagram is finicky — mitigation: keep it to subgraphs + arrows; no exotic shapes.
- *Depends on:* P17 (the demo flow must actually work for the run instructions to be honest).
- *Scope check:* one focused session.

**P20 — Pitch deck**

- *Goal:* An 8–10 slide deck for the hackathon submission. Sells the architecture honestly, names the friction stack, lands the Verafin comp, and aligns to partner awards (Gemini + Veea).
- *Files:* `docs/pitch_deck.md` (source-of-truth markdown), `docs/pitch_deck.pdf` (rendered, submitted), `docs/pitch_deck_speaker_notes.md` (notes for the live presenter — fits in the 3-minute slot).
- *Slide structure (9 slides):*
  1. **Title + framing** — "Federated Cross-Bank AML Investigation". Sub-line: "8 agent roles. 3 banks. 1 ring no single bank can see."
  2. **Problem** — §314(b) friction stack (4 frictions, ordered). One-line claim: "the statute has been law for 25 years; banks barely use it." Cite the four frictions visually.
  3. **What we built** — architecture diagram (same as README's Architecture mermaid, exported as PNG). Three explicit bank silo stacks (A3 + P7 + local DB + local LT/LiteLLM + policy/security), investigator stacks (A2 + local LT/LiteLLM), and one separate federation stack (F1-F5 + federation LT/LiteLLM + route signer + aggregate audit).
  4. **Demo walkthrough** - the 10-step canonical flow with screenshots from the interactive judge console (taken from P21's screencast). Show LT verdicts overlaying each step. Land the moment where F2 identifies the structuring ring.
  5. **Where DP fits (and where it doesn't)** — the per-query-shape table from the README. Note: "DP earns its keep on aggregate counts; binary presence relies on hash linkage; we're explicit about which is which."
  6. **What we address vs. don't** — the friction stack revisited. We address 3 of 4 (infrastructure, technical-not-contractual privacy, query-primitive ontology); we do not address legal-team risk aversion (the largest friction). Honest scoping.
  7. **Comp: Verafin → Nasdaq $2.75B** — the comp slide. Their privacy is contractual; ours is technical. Smaller competitive-paranoia barrier. Plausible buyer: top-tier banks or regulator-driven consortium.
  8. **Cross-vertical applicability** — same federation, different policy pack: cyber threat intel (ISACs), insurance loss pooling, clinical research (the project's archived prior framing). Two-line note that the architecture is general.
  9. **Partner alignment + ask** — Gemini powers all agents (Track 4 + Gemini award); Veea Lobster Trap is the policy substrate (Veea award). Repo is public-readable; submission complete.
- *Style:* clean, banking-credible, not buzzword-y. Two fonts (one display, one body). Two accent colors. No animations beyond pdf-native page transitions.
- *Out of scope for this part:* no separate investor deck; no fundraising material; no post-hackathon roadmap deck.
- *Acceptance:* PDF renders correctly; speaker can deliver the 9 slides in 3 minutes (≤20s per slide); the deck would pass a banking-experienced judge's credibility check (no overclaims, friction-stack named, DP scoped honestly).
- *Risks specific to this part:* (a) overclaiming — mitigation: every claim sourced (Verafin price, §314(b) text, FFIEC reference, FinCEN typology codes). (b) under-emphasizing the multi-agent story (judges score on that) — mitigation: slides 3, 4, 9 explicitly count agents and show their interactions. (c) deck production time — mitigation: author in markdown; convert to PDF via a simple pipeline (pandoc + LaTeX or a markdown-to-slide tool); template provided ahead of P20.
- *Depends on:* P18 (UI screenshots), P19 (architecture diagrams reusable).
- *Scope check:* one to two focused sessions. Writing is fast; converging on the deck's voice is the bottleneck.

**P21 — Demo dry-run × 3 + screencast**

- *Goal:* Three consecutive successful canonical-flow runs; a polished screencast recorded as the live-demo backup; a beat-by-beat demo script the presenter can rehearse from.
- *Files:* `docs/demo_script.md` (the spoken-words script for the 3-minute live demo), `docs/demo_screencast.mp4` (the recorded backup), `docs/demo_dry_run_log.md` (per-run outcomes, latencies, any anomalies — closed out after the third successful run).
- *Demo script (3-minute beat structure):*
  - **00:00–00:20 (Setup)** - "Three banks. Eight agent roles, fourteen running instances. A planted structuring ring spanning all three. Each bank sees only their slice." Show the judge console initial state with all panes cleared. Mention the dataset is synthetic and calibrated to FinCEN typologies.
  - **00:20–01:00 (Single-bank failure)** — Show Bank Alpha's A1 alert. Show A2 attempting internal investigation. Pause the story: "no cross-bank context; the ring is invisible to Bank Alpha alone." This is the friction the demo addresses.
  - **01:00–02:30 (Federation moment)** — Resume. A2 declares §314(b) suspicion; the AML adapter validates and LT logs; F1 broadcasts; peer banks respond; F2 detects the ring; F3 flags PEP; F4 drafts SAR. Audit panel updates visibly throughout. Call out the LT verdicts and the privacy-budget meter debiting.
  - **02:30–03:00 (Close)** — Final SAR draft visible. One-line market context: "Verafin → Nasdaq $2.75B for the contractual-trust version. We built the technical-trust version." End with partner alignment (Gemini + Veea).
- *Dry-run protocol:*
  - Three full runs in sequence: each timed to <3 minutes wall-clock; each producing the expected SAR draft (typology code, PEP flag, contributor count); each audit stream's event count within ±10% of the expected ~30.
  - Capture failures: if any run produces an unexpected outcome, log it in `demo_dry_run_log.md` with the diff vs. expected, and decide whether to (a) tune the data layer / DP rho / prompts, or (b) accept the variability and document it in the script.
  - The third successful run becomes the basis for the screencast.
- *Screencast specs:*
  - 1920×1080 resolution; 30 fps; H.264 mp4 codec; ≤50 MB target.
  - Open with a still frame showing the demo title for ~2 seconds.
  - End with a still frame showing the final SAR draft for ~3 seconds (so a viewer can pause and read it).
  - Voice-over optional; if included, follow the `demo_script.md` exactly.
- *Out of scope for this part:* no live web hosting (per Section 13.2); no per-judge customizations; no localized variants.
- *Acceptance:* Three consecutive successful dry-runs logged in `demo_dry_run_log.md`; screencast committed to `docs/demo_screencast.mp4`; demo script reviewed against the speaker notes from P20.
- *Risks specific to this part:* (a) Gemini latency spikes during recording — mitigation: record multiple takes; the canonical-flow script supports a `--seed` lock that hits cached LLM responses if pre-rendered. (b) DP-noise variability between runs could surface a different SAR narrative each time — mitigation: structured fields are stable; narrative wording differences are documented as expected. (c) Live-demo on stage is fragile — mitigation: screencast is the canonical backup; the presenter has the script + screencast ready to swap.
- *Depends on:* P18 (UI), P20 (deck context — the demo references slides).
- *Scope check:* one to two focused sessions, mostly rehearsal + recording.

**P22 — Hackathon submission**

- *Goal:* Submission form filled, repo set to public-readable, all required artifacts linked and accessible. Submission deadline: May 19, 2026 (TechEx).
- *Files:* `docs/submission_checklist.md` (closed out the morning of May 19).
- *Submission checklist:*
  - [ ] Repo set to public-readable on GitHub.
  - [ ] `README.md` includes a "Run the demo" quickstart.
  - [ ] `LICENSE` file added (MIT or equivalent).
  - [ ] `docs/pitch_deck.pdf` is the linked deck.
  - [ ] `docs/demo_screencast.mp4` is the linked screencast.
  - [ ] TechEx submission form filled with: project title, one-line description, team members, repo URL, screencast URL, primary track (Track 4 — Data & Intelligence), partner-award selections (Gemini + Veea Lobster Trap).
  - [ ] Final `pytest tests/` run passes (all P0 + P3 tests at minimum; P17 e2e if API key available).
  - [ ] Final demo cleanup: remove or convert temporary P6 hash-evidence scaffolding tests once the canonical evidence-construction path is locked. The final architecture should not require the live model to compute SHA-256 hashes; hash fields can remain documented as the expected data/evidence shape, while deterministic code constructs or verifies them outside the model.
  - [ ] `plan.md` `Current build state` reflects the actual ship state — anything in the cut order that was actually cut is marked as cut, not done.
  - [ ] `docs/cut_list.md` (if anything was cut) — short post-mortem of what was cut and why.
  - [ ] Submission confirmation email received from TechEx.
- *Out of scope for this part:* no on-site travel logistics; no live-demo slot scheduling (that's TechEx's process); no post-submission follow-up activities (those are Section 13.3).
- *Acceptance:* All checklist items ticked; submission confirmation email received before May 19 23:59 ET.
- *Risks specific to this part:* (a) submission form may have unexpected fields — mitigation: review the form at least 48 hours before deadline; populate placeholders. (b) Repo set to private accidentally — mitigation: explicit "verify on a logged-out browser" step in the checklist. (c) Last-minute regressions break the demo — mitigation: P21's screencast is the canonical version; live demo is a bonus.
- *Depends on:* P21 (screencast must exist before the form is submitted).
- *Scope check:* a few hours of focused checklist execution on the morning of May 19; the work compounds from earlier parts.

---

### Cut order if something runs hot

In rough priority order, the things that can drop without killing the demo:

1. **P13 (F5 compliance auditor)** -> replace with a simpler audit-log dump in the judge console
2. **P12 (F4 SAR drafter)** -> pre-draft a SAR for the demo and present it as agent output (annotate the slide)
3. **S2 / S3 secondary scenarios in P2 data** → already built; cost nothing to keep. If something downstream breaks because of them, narrow the demo to S1 + S4 (the headline + PEP) only
4. **Advanced P18 polish** -> keep the basic interactive judge console, but cut replay scrubbing, exports, and the full probe library down to three probes: prompt injection, MITM tamper, and budget exhaustion
5. **DP scope on P7** -> fall back from OpenDP helpers to hand-rolled Gaussian + simple rho-counter if OpenDP integration eats more time than expected. The primitives layer itself stays; only the DP-rigor knob moves.

Do not cut: A1, A2, A3, F1, F2, F3, the **stats-primitives layer (P7)** (the architecture's structural privacy claim depends on it), the AML policy adapter plus LT overlay (P14), the orchestrator/control API (P15), the canonical flow (P16), and the basic interactive judge console (P18). These are the demo's spine.

---

## 12. Risks & Mitigations

- **Synthetic transaction data not realistic enough** — judges with banking experience may probe. Mitigation: cite published typologies (FinCEN, FFIEC) explicitly in the README; declare the dataset synthetic on stage; focus the demo on the federation mechanic rather than the realism of any single bank's transaction stream.
- **§314(b) framing inaccurate** — minor legal mischaracterization could be a credibility hit. Mitigation: the README cites the statute correctly and frames our claims modestly ("we built primitives that would make §314(b) easier to operationalize," not "we are §314(b)-compliant").
- **Agent surface too complex for 3 days** — the agent surface area is real. Cut order if Day 3 runs hot: F5 (compliance auditor) first — replace with a simpler audit-log dump UI. Then F4 (SAR drafter) — pre-draft a SAR for the demo and present it as agent output. Do not cut F1, F2, F3, A1, A2, or A3 because these are the federation spine.
- **Demo latency** — multiple agent calls per query times network round trips may produce visible delays. Mitigation: parallelize where possible; pre-stage canonical demo queries with deterministic seeds so timing is predictable.
- **Gemini structured-output reliability for agent messages** — Gemini's JSON-schema mode is good but not perfect. Mitigation: include retry logic on malformed agent outputs; use `flash` for narrative steps and `pro` for structured-output steps.
- **No real sanctions list** — F3's mock list is obviously fake. Mitigation: cite OFAC SDN list as the production target; the mock list contains ~10 well-known fictional names + the one PEP entity from the planted ring.

---

## 13. Launch Plan

### 13.1 Submission requirements (May 19 deadline)

- Live demo (or screencast backup) — 3 minutes
- README with run instructions
- Pitch deck (8–10 slides) including the Verafin $2.75B comp slide and the cross-vertical applicability slide
- GitHub repo public-readable
- Hackathon submission form

### 13.2 Stage demo

- Local laptop, all-localhost
- Synthetic data pre-loaded (avoid live generation during demo)
- Backup laptop running the same stack
- Pre-recorded screencast as final fallback

### 13.3 Post-stage

- Repo stays public
- Brief write-up of what was built + what was cut
- Decide whether to pursue post-hackathon (design-partner conversations with regional banks, ISACs, or AML vendors)

---

## 14. Future Work *(post-hackathon)*

### 14.1 Cross-vertical applicability (slide-deck material)

The same multi-agent + federation architecture extends to:

| Vertical | Use case | What changes |
|---|---|---|
| Cyber threat intel sharing (ISACs) | Cross-org incident pattern detection | Agent roles: SOC analyst, threat-intel coordinator, IOC sharer. TLP-flavored policies. |
| Cyber insurance loss pooling | Cross-carrier loss data for pricing | Agent roles: underwriter, actuary, claims-data aggregator. Carrier-confidential policies. |
| Healthcare federated research | Cross-hospital outcomes analytics | Agent roles: researcher, biostatistician, IRB liaison. HIPAA Safe Harbor policies. (Original project framing — archived in `docs/clinical-archive/`.) |
| Cross-bank credit risk benchmarking | Industry-wide loss-rate benchmarks | Same federation, different policy pack. |
| Antitrust-safe rate benchmarking | DP-protected pricing comparison across competitors | Same federation, different policy pack. |

### 14.2 Technical extensions

- Real OFAC SDN list integration with proper licensing
- MPC-based exact intersection of customer identifiers (vs. our hash-based approximate intersection)
- Federated GNN ring detection (research-grade)
- Per-bank policy customization beyond §314(b) (state-level AML laws)

---

## 15. Open Questions

- **3 banks vs 5 banks?** Default: 3. Adequate for the ring scenario; cuts build time. Can scale to 5 in Day 4 if buffer allows.
- **Ring scenario specificity:** structuring (default) vs layering vs sanctions-evasion. Structuring is the most-recognized typology and easiest to plant. Default: structuring.
- **Frontend stack:** Next.js (visual polish, ~1.5 days more) vs. Streamlit (faster, less polished). Decide Day 1.
- **Hosting:** localhost (safest) vs. live URL (strengthens pitch). Decide Day 6.
- **Veea Lobster Trap track award alignment:** the AML pivot retains LT as the policy substrate. The Veea track award framing actually gets *stronger* in this pivot because cross-bank governance is more securityish than HIPAA-ish.

---

## 16. Migration history

This project pivoted from clinical federated stats (Synthea-OMOP, CHF cohort, 5 hospital silos) to cross-bank AML mid-build. The clinical work is preserved in:

- `docs/clinical-archive/plan.md` — original clinical product design doc
- `data/scripts/clinical-archive/` — Synthea-OMOP data pipeline scripts (build_silos.py, feature_engineering.py, apply_scenarios.py, validate.py, vocab.py, download_synthea_omop.py)
- Git history before commit `<pivot-commit-sha>` — full clinical-build state

The pivot rationale (multi-agent fit for AI hackathon framing) is in `.claude/plans/hi-i-would-like-replicated-pelican.md` (local pivot plan, not committed to repo).
