# Federated Cross-Bank AML Multi-Agent System — Product Design Doc

> *This document follows a standard product spec structure. **Discovery** sections (Problem, Users, Market) establish what's true about the world. **Define** sections (Goals, Principles) commit to what we're optimizing. **Design** sections (Solution, UX, System) commit to how. **Build / Validate / Launch** sections turn the design into action. **Risks** and **Open Questions** are honest about what we don't yet know.*
>
> *This project pivoted from a clinical federated-stats design (Synthea-OMOP, CHF cohort) to cross-bank AML mid-build. The pivot plan and reasoning are preserved in [`.claude/plans/hi-i-would-like-replicated-pelican.md`](../.claude/plans/) and the clinical plan in [`docs/clinical-archive/plan.md`](docs/clinical-archive/plan.md). The pivot was motivated by the AI-hackathon framing: AML is natively multi-agent while clinical federated stats was structurally single-agent.*

---

## 0. TL;DR

A multi-agent cross-bank Anti-Money-Laundering investigation system. Three synthetic banks each run a transaction-monitoring agent and an investigator agent. When suspicious activity surfaces at one bank, the investigator agent coordinates with peer-bank investigators through a federation layer in an assumed TEE. Specialist agents (graph analyst, sanctions screener, SAR drafter, compliance auditor) compose investigations across the network. **Every cross-bank conversation is policed by Lobster Trap; aggregate transaction patterns are shared under differential privacy; no customer data ever crosses bank boundaries.**

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

1. Demonstrate **6 agents talking to each other** across an enforced trust boundary.
2. Demonstrate **federated detection of a planted cross-bank ring** that no single bank could surface alone.
3. Demonstrate **Lobster Trap policing every cross-bank message** (no customer names leaking, sanctions hits not exposing list details, audit trail complete).
4. Demonstrate **layered silo privacy**: (a) hash-based cross-bank entity linkage as the primary mechanism, (b) a deterministic stats-primitives layer in each bank enforcing data-plane isolation, (c) differential privacy applied to aggregate-count primitives via OpenDP with per-investigator ε budget tracked via zCDP composition. DP is scoped where it earns its keep (aggregate counts and histograms); binary presence queries rely on hash linkage instead.
5. Win or place at TechEx (Track 4 + Gemini partner award + Veea partner award).

### 4.2 Non-goals

1. **Production-grade AML detection.** The patterns are demoable, not state-of-the-art.
2. **Real banking regulatory certification.** We claim §314(b) authorization framing, not actual approval from a regulator.
3. **Heavy graph-ML.** Federated graph analytics is a research area; we'll do aggregate-graph-statistics, not deep GNN inference.
4. **Real-time / streaming.** Batch query model only.
5. **Sanctions list maintenance.** We use a small mock list with publicly-known typologies; not a real OFAC integration.

### 4.3 Success metrics

- All 6 agents wired and exchanging structured messages through the LT proxy
- A live demo successfully detects the planted ring within 3 minutes
- Every cross-bank message passes through LT policy enforcement and lands in the audit log
- Single-bank investigation of the same ring fails (the federation is what makes detection possible)
- Submission complete by May 19 with README + pitch deck + screencast

---

## 5. Solution Thesis *(Ideate → Design)*

Three banks each run two persistent agents (transaction-monitoring + investigator). A central federation layer in an assumed TEE hosts four cross-cutting specialist agents (graph analyst, sanctions screener, SAR drafter, compliance auditor). Five layered privacy mechanisms, in rough order of how much privacy work each does:

- **Hash-based cross-bank entity linkage.** Banks share stable `name_hash` tokens, never customer identifiers. This is the primary privacy mechanism — it's what makes the federation work at all. Same input, same hash, everywhere; different banks holding accounts for the same shell entity can correlate without disclosing identity.
- **Bank-local stats-primitives layer.** A deterministic, non-LLM module in each bank that exposes a fixed set of declared query shapes over local data (e.g., `count_entities_by_name_hash`, `alert_count_for_entity`, `flow_histogram`). Every cross-bank-bound numeric value traces to a primitive call with recorded provenance. The LLM has no syscall to raw transactions on the cross-bank-response path; data-plane isolation is structural, not policy-based. This is the structural enforcement of design principle #6 ("agents reason about signals, not transactions").
- **Lobster Trap on NL channels.** What one agent can say to another about a third party's customers: customer-name redaction at egress, role-based authorization (A1 cannot send to peer-bank channels; only A2 and F-agents can), purpose-declaration enforcement on every §314(b) query, audit-event emission on every cross-bank message.
- **Schema validation.** Only pre-declared message shapes leave a bank; the schema is the trust contract.
- **Differential privacy on aggregate-count primitives.** Gaussian mechanism with σ calibrated to sensitivity; per-(investigator, peer-bank) ε budget tracked via zCDP composition; the channel refuses when the budget is exhausted. Applied where it earns its keep (alert counts, flow histograms, F2 input aggregates) — not applied to binary presence queries where noise would eat the signal (those rely on hash linkage instead). DP's specific job here is bounding sustained insider-abuse leakage: an authorized investigator using the channel for routine surveillance is bounded to ε bits of information per peer bank, then the channel closes.

Honest note on what DP doesn't do: it doesn't protect entity-presence binary queries (sensitivity-1 question with magnitude-1 answer means noise eats the signal); it isn't the protagonist of the headline demo (the protagonist is the cross-bank graph cycle that no single bank can see); it isn't what Verafin uses (Verafin's privacy model is contractual). DP earns its keep against a specific threat — multi-query inference about aggregate activity — and that's the role it plays here.

---

## 6. Design Principles *(Define)*

1. **Privacy-by-default.** No raw transactions leave a bank. Schema validation enforces this structurally.
2. **§314(b)-shaped disclosure rules.** Cross-bank information sharing is allowed for suspected ML/TF only; LT policy enforces declared-purpose checks.
3. **Honest about guarantees.** The federation provides bounded leakage and full audit; it does not provide perfect anonymity (a determined adversary could potentially infer individual customers from many queries; DP budget bounds this).
4. **Agent roles are typed and enforced.** Each agent has a declared role; LT enforces what messages each role can send and receive.
5. **Audit is product.** Every cross-bank message lands in a structured, regulator-readable audit log. SAR drafts are auditable down to which agent contributed which finding.
6. **No LLM in the transaction data plane.** Agents reason about *signals*, not *transactions*. Transaction-level access is deterministic SQL at the bank's local agent; aggregate signals are what travel.
7. **Reproducibility.** Deterministic seeds in synthetic data + structured agent message schemas = bit-equivalent reruns for the canonical demo.

---

## 7. User Experience Design *(Design)*

### 7.1 Primary flow

1. AML analyst opens the investigation console.
2. A1 (transaction-monitoring agent) at their bank shows recent alerts.
3. Analyst selects an alert; A2 (investigator) takes it from there.
4. A2 reasons about the alert; if it has cross-bank signal, A2 asks the federation coordinator (F1) to query peer banks.
5. F1 routes anonymized queries to peer banks' A2 agents through Lobster Trap.
6. Peer A2 agents respond with anonymized signals (if they have matches).
7. F2 (graph analyst) assembles cross-bank pattern; F3 (sanctions) screens entities.
8. F4 drafts a SAR; F5 audits the entire conversation; analyst signs off.

### 7.2 Key UI surfaces

| Surface | What it shows | Why it matters |
|---|---|---|
| Bank investigator console | A1 alerts, A2 reasoning, cross-bank query status | Primary operational surface |
| Federation timeline | Live agent-to-agent conversation with LT verdicts overlaid | The multi-agent demo's signature visual |
| Audit panel | Every LT decision, every DP debit, every schema violation | The compliance dashboard |
| SAR draft viewer | Structured form + attributed contributions | Regulatory artifact |

### 7.3 Demo experience design

The demo is a 3-minute four-beat run:

1. **Setup (20s)** — three banks, six agents, federation layer. Show audit panel cleared. Show the planted ring exists in pooled data (central analysis sees it).
2. **Single-bank attempt (40s)** — Bank Alpha's A1 flags suspicious activity. A2 investigates internally. Shows the alert is just below threshold; single-bank context can't escalate. *"This is what happens today."*
3. **Federation moment (90s)** — A2 declares §314(b) suspicion → F1 broadcasts anonymized query → peer banks respond → F2 assembles ring → F3 screens sanctions → F4 drafts SAR. Audit panel lights up at each step. *"This is what federation makes possible."*
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
   │   A1 + A2    │ │   A1 + A2    │ │   A1 + A2    │
   │  (Gemini)    │ │  (Gemini)    │ │  (Gemini)    │
   │     ↕        │ │     ↕        │ │     ↕        │
   │  Stats       │ │  Stats       │ │  Stats       │
   │  primitives  │ │  primitives  │ │  primitives  │
   │  (DP + ε     │ │  (DP + ε     │ │  (DP + ε     │
   │   budget)    │ │   budget)    │ │   budget)    │
   │     ↕        │ │     ↕        │ │     ↕        │
   │  SQLite      │ │  SQLite      │ │  SQLite      │
   └──────────────┘ └──────────────┘ └──────────────┘
```

Two wire paths inside each bank:

- **LLM wire path:** `agent → Lobster Trap (port 8080) → LiteLLM (port 4000) → Gemini API`. All six agents share this path; each is identified by an agent_id and role in the LT request metadata.
- **Data wire path:** `A2 → stats-primitives layer → SQLite`. Deterministic, non-LLM, raw-SQL inside the bank. The stats layer is the only component allowed to read raw transactions in service of a cross-bank response; A1 reads raw signals for *local* monitoring only. Every cross-bank-response numeric value in a `Sec314bResponse` traces to a primitive call with a recorded ε debit (zero for non-DP primitives).

### 8.2 Message flow (canonical demo case)

```
[t=0] Bank α's A1 flags suspicious sub-$10K transfer pattern → alert to Bank α's A2
[t=1] Bank α's A2 evaluates alert; declares §314(b) suspicion; queries F1
       (LT: verifies §314(b) purpose declaration is valid; passes)
[t=2] F1 broadcasts anonymized signal pattern to Banks β and γ investigators
       (LT: enforces customer-name redaction in outbound query)
[t=3] Banks β and γ's A2 agents each respond with anonymized signals (matches found)
       (LT: enforces no raw transactions in response)
[t=4] F1 forwards aggregated signals to F2 (graph analyst) for ring inference
[t=5] F2 returns: "high probability cross-bank structuring ring spanning 3 nodes"
[t=6] Investigators submit anonymized entity hashes to F3 (sanctions)
[t=7] F3 returns: "no direct sanctions match; one entity has PEP relation"
[t=8] Bank α's A2 synthesizes findings + invokes F4 to draft SAR
[t=9] F4 emits SAR draft with proper attribution to each bank's contribution
[t=10] F5 audits the full conversation; confirms §314(b) compliance; surfaces audit summary
```

Every arrow is policed by Lobster Trap. Every message is logged in the audit channel.

### 8.3 The six agents

**All six are full LLM agents (Gemini)** that reason about their inputs and decide what to output. Each agent's reasoning is wrapped in deterministic rule checks of two kinds:

- **Rule constraints** — hard checks that the LLM cannot override. If a constraint is violated, the agent refuses; the LLM doesn't get to argue.
- **Rule bypasses** — hard checks that override the LLM. Certain conditions force a specific output regardless of what the LLM would have said. (E.g., a transaction ≥ $10K MUST emit a CTR alert; that's federal law, not a judgment call.)

This pattern mirrors how real bank investigators work: they exercise professional judgment, constrained by hard compliance rules, and occasionally overridden by mandatory reporting requirements. Encoding the same shape in the agent runtime gives the demo two valuable properties: (1) the LLMs have real agency on the gray-area decisions, (2) the demo is robust to LLM drift on the black-and-white ones.

#### Bank-local agents (×3 banks)

**Agent A1: Transaction-monitoring agent** (one per bank, identical role)

- **Role:** Reviews batches of suspicious-signal candidates from the bank's own transaction stream. Decides which to escalate to A2 as named alerts, what severity to assign, what rationale to attach.
- **Inputs:** Local `suspicious_signals` + correlating transaction rows
- **Outputs:** `Alert` messages to local A2
- **Reasoning:** Gemini call with structured output (JSON schema producing `Alert` records). The LLM sees the transaction context, customer KYC tier, channel, recent activity history. It can suppress noisy signals it judges to be legitimate business (most are) and elevate ones that pattern-match real concerns.
- **Rule constraints (LLM cannot override):**
  - Cannot emit any message addressed to anything other than local A2 (cross-bank channels are LT-blocked for A1 role)
  - Cannot modify transaction or signal data
  - Cannot suppress a signal that meets a hard-required criterion (see bypasses)
- **Rule bypasses (override LLM):**
  - Transaction amount ≥ $10,000 → MUST emit a `Currency Transaction Report` alert (federal law; LLM cannot dismiss)
  - Counterparty hash matches a known SDN entry → MUST emit a `Sanctions Match` alert
  - Velocity spike (e.g., 10+ near-CTR transactions on one account within 24h) → MUST emit a high-severity alert

**Agent A2: Investigator agent** (one per bank, identical role; the protagonist)

- **Role:** Receives alerts from local A1. Decides whether to investigate, dismiss, or escalate cross-bank. When cross-bank, drafts §314(b) queries; receives peer-bank responses; synthesizes investigation findings; recommends SAR / dismiss to F4 / F5. **Also receives incoming `Sec314bQuery` from F1 originating at other banks, and answers via the local stats-primitives layer.**
- **Inputs:** `Alert` from local A1; `Sec314bResponse` from F1; incoming `Sec314bQuery` relayed by F1 from peer banks
- **Outputs:** `Sec314bQuery` to F1 (outbound to peers); `Sec314bResponse` to F1 (answering incoming peer queries); `SARContribution` to F4; `DismissalRationale` to F5
- **Reasoning:** Gemini call. A2 reasons about alert credibility given local context, decides what cross-bank signals would be informative, drafts queries that comply with §314(b) purpose declarations. When answering an *incoming* peer query, A2 reasons about credibility ("is this a credible federation cue or a fishing expedition?") and decides which stats-primitives to invoke; it never reads raw transactions in service of the cross-bank-response path. All numeric/list fields in an outbound `Sec314bResponse` come from primitive calls (with recorded provenance and ε debits where applicable); the LLM's role is to compose, not to compute.
- **Rule constraints (LLM cannot override):**
  - Cannot include customer names in outbound `Sec314bQuery` or `Sec314bResponse` (LT redacts at egress; A2 cannot opt out)
  - Cannot send `Sec314bQuery` without a structured purpose declaration (rejected by F1 if missing)
  - Cannot escalate to SAR without a peer-bank corroborating signal (rule prevents single-bank speculation from becoming a SAR)
  - **Every numeric/list value in an outbound `Sec314bResponse` must trace to a stats-primitives call** (provenance enforced structurally; LLM cannot fabricate aggregate values)
  - **Cannot answer a `Sec314bResponse` when the per-(investigator, peer-bank) ε budget for the requesting investigator is exhausted** (deterministic refusal; LLM cannot override)
- **Rule bypasses (override LLM):**
  - 3+ correlated alerts on the same `name_hash` within 30 days → MUST send `Sec314bQuery` regardless of LLM judgment
  - Alert tied to a known SDN match → MUST escalate to SAR

#### Federation-layer agents (in assumed TEE)

**Agent F1: Cross-bank coordinator agent**

- **Role:** Receives `Sec314bQuery` from any bank's A2. Validates purpose declaration. Broadcasts the (LT-redacted) query to peer banks' A2 agents. Collects responses. Forwards anonymized aggregates to F2.
- **Reasoning:** Gemini call. F1 reasons about which peer banks the query is relevant to (not every query needs every bank), how to phrase the query for peer A2s, how to aggregate responses for the requesting A2.
- **Rule constraints (LLM cannot override):**
  - Cannot retain customer identifiers between queries (stateless; LT-enforced)
  - Cannot forward a query without a valid `Sec314bQuery.purpose` field
  - Cannot send the same query body to peers that contains customer-name strings (LT redacts at the channel)
- **Rule bypasses (override LLM):**
  - Quota exceeded (e.g., 20+ queries from one investigator in 1 hour) → MUST escalate to F5 for compliance review
  - Query references a known SDN entity → MUST also route through F3 in parallel

**Agent F2: Graph-analysis agent**

- **Role:** Receives anonymized cross-bank transaction-pattern aggregates from F1. Identifies ring structures (closed cycles, structuring rings, layering chains). Returns suspected-pattern reports with confidence scores.
- **Reasoning:** Gemini call. F2 reasons about whether observed aggregate patterns are consistent with known typologies, what the most likely structure is, how confident to be.
- **Rule constraints (LLM cannot override):**
  - Cannot see raw transactions (input is DP-noised aggregates only; LT-enforced)
  - Cannot output individual-customer identifiers (output schema restricts to entity-hash IDs)
- **Rule bypasses (override LLM):**
  - Closed cycle with ≥3 entities spanning ≥3 banks → MUST surface as high-confidence structuring ring (regardless of LLM uncertainty)
  - Loop in transfer graph with ≥4 hops and per-hop fees ≈ 2–5% → MUST surface as high-confidence layering

**Agent F3: Sanctions / PEP screening agent**

- **Role:** Receives entity hashes from A2 or F1. Returns binary match flags against the (mock) SDN watchlist, plus PEP relation indicators when applicable.
- **Reasoning:** Gemini call. F3 reasons about fuzzy matches (similar name hashes, partial matches, transliteration variants in a real deployment). The mock list contains exact hashes for the demo's planted PEP entity plus ~10 well-known fictional names.
- **Rule constraints (LLM cannot override):**
  - Cannot return list contents (output is binary + relation type only)
  - Cannot retain queried entity hashes between requests
- **Rule bypasses (override LLM):**
  - Exact hash equality with SDN entry → MUST flag as match regardless of LLM judgment
  - Hash equality with planted PEP entity → MUST flag as PEP-related

**Agent F4: SAR drafter agent**

- **Role:** Receives `SARContribution` messages from one or more A2 agents plus F2's pattern report and F3's sanctions findings. Synthesizes a Suspicious Activity Report draft with proper structured fields and narrative.
- **Reasoning:** Gemini call. F4 reasons about how to combine contributions into a coherent SAR narrative, what additional information to request from contributors, how to phrase regulatory-quality language.
- **Rule constraints (LLM cannot override):**
  - Must include `purpose_declaration` field linking back to §314(b) authority
  - Must include per-bank attribution for each piece of evidence
  - Cannot include customer-name strings (LT redacts; uses `name_hash` references instead)
- **Rule bypasses (override LLM):**
  - Mandatory SAR fields (filing-institution, filing-date, suspicious-amount-range, typology-code) MUST be populated — LLM can word them but cannot omit them
  - If any contributor included a sanctions match → MUST set `sar_priority = high` regardless of LLM judgment

**Agent F5: Compliance auditor agent**

- **Role:** Subscribes to the live LT audit stream. Reasons about whether each cross-agent message exceeds §314(b) authorization or pattern-matches a "fishing expedition." Emits compliance annotations to the audit panel.
- **Reasoning:** Gemini call. F5 reasons about whether a query series is investigating a legitimate suspicion or trolling for general information about a peer bank's customers. Flags anomalies in NL form.
- **Rule constraints (LLM cannot override):**
  - Read-only on the audit stream (cannot block or modify agent behavior)
  - Cannot suppress audit events from being logged
- **Rule bypasses (override LLM):**
  - Single `Sec314bQuery` with a purpose declaration that doesn't reference suspected ML/TF activity → MUST emit `HUMAN_REVIEW` annotation regardless of LLM judgment
  - >10 §314(b) queries from one investigator in 60 minutes → MUST emit rate-limit warning

### 8.4 Threat model

| Trusted | Untrusted |
|---|---|
| Each bank's own data + local A1/A2 agents | Other banks' raw data (never shared) |
| Federation layer process (assumed in TEE) | Operator/cloud (production assumes TEE) |
| Lobster Trap (NL channel + role-auth) | Compromised bank agent (defended by schema + LT) |
| Schema validator (numerical channel) | Curious investigator at a peer bank (defended by DP + LT redaction) |
| OpenDP composition | Malicious investigator running fishing expeditions (defended by §314(b) purpose checks + budget) |

Defense mapping:
- **Lobster Trap** closes NL extraction (customer names in queries/responses) + role abuse (A1 trying to act as A2) + injection
- **Schema validation** ensures no raw transactions leave a bank
- **DP composition** bounds how much an investigator can learn about peer-bank customers across many queries
- **§314(b) purpose declarations** create a per-query justification that's logged for regulator review

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

The proxy chain (Lobster Trap → LiteLLM → Gemini) is up and smoke-tested under the clinical configuration. The pivot to AML preserves the proxy chain unchanged; what changes is the data layer, the agent code, the stats-primitives layer, and the LT policy pack. The data layer for AML is complete.

- **P0** Repo scaffold + proxy chain smoke ✓
- **P1** Pivot migration (clinical → AML, plan and archives) ✓
- **P2** Bank data layer + planted scenarios ✓
- **P3** Bank data validation + checksum test ✓
- **P4** Shared message schemas →
- **P5** Agent runtime base class ·
- **P6** A1 transaction-monitoring agent ·
- **P7** Bank-local stats-primitives layer + DP ·
- **P8** A2 investigator agent ·
- **P9** F1 cross-bank coordinator ·
- **P10** F3 sanctions / PEP screening agent ·
- **P11** F2 graph-analysis agent ·
- **P12** F4 SAR drafter agent ·
- **P13** F5 compliance auditor agent ·
- **P14** AML Lobster Trap policy pack ·
- **P15** Agent orchestrator / message bus ·
- **P16** Canonical demo flow script ·
- **P17** End-to-end smoke test ·
- **P18** Federation timeline + audit panel (terminal UI) ·
- **P19** README + mermaid diagrams for AML ·
- **P20** Pitch deck ·
- **P21** Demo dry-run × 3 + screencast ·
- **P22** Hackathon submission ·

---

### Done parts (P0–P3)

**P0 — Repo scaffold + proxy chain smoke** ✓

- *Goal:* repo skeleton (`infra/`, `scripts/`, `tests/`), Lobster Trap container, LiteLLM container, Gemini routing, P0 smoke test passes against Gemini through both proxies.
- *Status:* done before the AML pivot. Preserved unchanged.

**P1 — Pivot migration (clinical → AML)** ✓

- *Goal:* clinical plan and data scripts archived; AML plan in place; README reframed.
- *Files:* `docs/clinical-archive/plan.md`, `data/scripts/clinical-archive/`, top of `README.md`, top of `data/README.md`, this `plan.md`.
- *Acceptance:* clinical artifacts preserved in archive paths; AML framing visible from repo root.

**P2 — Bank data layer + planted scenarios** ✓

- *Goal:* three SQLite bank databases with calibrated synthetic data + four planted scenarios.
- *Files:* `data/scripts/build_banks.py`, `data/scripts/plant_scenarios.py`, `data/silos/{bank_alpha,bank_beta,bank_gamma}.db`.
- *Approach:* SHA-256-seeded RNG per bank for reproducibility; FFIEC-threshold and FinCEN-typology-calibrated transaction patterns; cross-bank entity linkage via stable `name_hash`; four scenarios planted (S1 5-entity ring across all three banks, S2 3-entity ring across Alpha+Beta, S3 4-entity layering chain Alpha→Beta→Gamma→Alpha, S4 PEP marker on S1-D).
- *Acceptance:* all three `.db` files produced; `ground_truth_entities` table populated per bank; reproducible across processes.

**P3 — Bank data validation + checksum test** ✓

- *Goal:* every planted property verified; canonical fingerprint hash baked into the test suite.
- *Files:* `data/scripts/validate_banks.py`, `tests/test_data_checksum.py`.
- *Acceptance:* `validate_banks.py` runs 30+ checks and exits 0 (federated-detectable yes, single-bank-detectable no); `pytest tests/test_data_checksum.py` matches the canonical hash `3a87870c1d58a50a6f0df69bf95e6b92a9cfe38297cba2c849e9297a4a13b45e`.

---

### Next parts (P4–P13)

The agent build follows the canonical demo's call order: alert origination (A1) → investigator (A2) → coordinator (F1) → sanctions (F3) → graph analyst (F2) → SAR drafter (F4) → compliance auditor (F5). F3 ships before F2 because it's the simpler agent and shakes out the agent base class first; F5 ships last because it depends on the live audit stream. P7 (stats-primitives layer) ships before A2 because A2's cross-bank response path calls into it.

**P4 — Shared message schemas**

- *Goal:* Pydantic v2 boundary objects for every cross-agent message in the canonical flow.
- *Files:* `shared/messages.py`.
- *Approach:* one model per message type (`Alert`, `Sec314bQuery`, `Sec314bResponse`, `SanctionsCheckRequest`, `SanctionsCheckResponse`, `GraphPatternRequest`, `GraphPatternResponse`, `SARContribution`, `SARDraft`, `AuditEvent`, `DismissalRationale`). Each model has: `message_id`, `sender_agent_id`, `sender_bank_id` (or `federation` for F-agents), `recipient`, `purpose_declaration` where §314(b) applies, payload-specific fields, and a `created_at` timestamp. `Sec314bResponse` carries a `provenance` field linking each numeric/list value to a primitive-call record (populated by P7).
- *Acceptance:* Pydantic round-trip works for every model; JSON-schema for each is exportable (so Gemini structured-output can target it); unit tests cover at least one valid + one invalid example per message type.
- *Depends on:* P0.

**P5 — Agent runtime base class**

- *Goal:* a single `Agent` base that encapsulates the LLM call, the rule-constraint check, and the rule-bypass check pattern that every agent follows.
- *Files:* `backend/agents/base.py`, `backend/agents/__init__.py`.
- *Approach:* `Agent.run(input)` calls (1) `bypass_check(input)` first — if a bypass triggers, return the forced output without calling Gemini; (2) otherwise call Gemini with structured output targeting the agent's output schema; (3) then `constraint_check(input, output)` — if a constraint is violated, raise `ConstraintViolation` (which the orchestrator turns into an audit event + the agent retries or refuses). Single LLM call site = one place to plumb in retries, logging, audit emission.
- *Acceptance:* the base class can be subclassed with just a system prompt, an output schema, and lists of bypass-rules and constraint-rules; a trivial test agent works end-to-end against the proxy chain.
- *Depends on:* P0, P4.

**P6 — A1 transaction-monitoring agent**

- *Goal:* full LLM agent that reads `suspicious_signals` + correlated transaction rows for one bank and produces `Alert` messages for local A2, with rule constraints and bypasses per Section 8.3.
- *Files:* `backend/agents/a1_monitoring.py`, `backend/agents/prompts/a1_system.md`.
- *Approach:* batch input = N candidate signals at one bank. Gemini call returns one `Alert` decision per candidate. Bypasses (CTR ≥ $10K, SDN match, velocity spike) force-emit alerts. Constraints block any outbound message not addressed to local A2.
- *Acceptance:* unit test: run A1 on a deterministic batch from `data/silos/bank_alpha.db`; the planted S1 transactions yield at least the expected near-CTR alerts; CTR-threshold bypass triggers on a synthetic ≥$10K transaction; output passes Pydantic validation.
- *Depends on:* P3, P5.

**P7 — Bank-local stats-primitives layer + DP**

- *Goal:* a deterministic (non-LLM) module per bank that exposes a fixed set of declared query primitives over the bank's SQLite database, applies Gaussian DP noise where appropriate, and tracks a per-(investigator, peer-bank) ε budget via zCDP composition. This is the structural enforcement of design principle #6 — the data plane is severed from the cross-bank-LLM path.
- *Files:* `backend/silos/stats_primitives.py`, `backend/silos/dp.py` (Gaussian mechanism + zCDP composition wrappers around [OpenDP](https://github.com/opendp/opendp)), `backend/silos/budget.py` (per-investigator ε ledger, persistent within a session).
- *Approach:* expose five-ish hard-coded primitives — `count_entities_by_name_hash`, `alert_count_for_entity`, `flow_histogram`, `counterparty_edge_existence`, `pattern_aggregate_for_f2`. Each declares its L2 sensitivity. DP-applicable primitives (aggregate counts and histograms) apply Gaussian noise with σ calibrated to the requested ε and debit the budget; non-DP primitives (binary presence, edge existence) route through the layer for provenance only. Budget ledger keyed by `(requesting_investigator_id, requesting_bank_id)`; default total ε = 1.0 per pair; exhaustion is a deterministic refusal (no LLM judgment).
- *Acceptance:* `tests/test_stats_primitives.py` instantiates the layer against `data/silos/bank_alpha.db`, calls each primitive against a known query 20 times, verifies (a) noise calibration matches analytical σ within tolerance over many trials, (b) budget ledger debits correctly with zCDP composition, (c) the (N+1)th call after budget exhaustion refuses deterministically, (d) every primitive returns a provenance record (primitive name, ε debited, timestamp).
- *Depends on:* P3.
- *Adds dependency:* `opendp` in `pyproject.toml`.

**P8 — A2 investigator agent**

- *Goal:* full LLM agent that consumes `Alert` from local A1, decides whether to investigate, dismiss, or escalate cross-bank, drafts `Sec314bQuery` messages with proper purpose declarations, **and answers incoming peer queries via the stats-primitives layer (never directly from SQL).**
- *Files:* `backend/agents/a2_investigator.py`, `backend/agents/prompts/a2_system.md`.
- *Approach:* state machine inside the agent: `triage → investigate-locally → cross-bank-query → synthesize → recommend-SAR-or-dismiss`, plus an `answer-incoming-peer-query` branch. Each state is a Gemini call. The answer-incoming branch decides which P7 primitives to invoke; the LLM composes the `Sec314bResponse` but every numeric/list value comes from a primitive call with attached provenance. Bypasses force §314(b) queries for repeated alerts on the same `name_hash` and force SAR escalation on SDN-tagged alerts. Constraints prevent customer-name leakage, prevent SAR escalation without peer-bank corroboration, and block any `Sec314bResponse` field whose value isn't a primitive-call result.
- *Acceptance:* unit test: feed A2 a known S1-related alert; A2 emits a `Sec314bQuery` with a structured purpose declaration; LT-style redaction check passes. Second unit test: feed A2 an incoming peer `Sec314bQuery`; A2 returns a `Sec314bResponse` whose every numeric value has a matching primitive-call provenance entry and whose ε debits are recorded against the requesting investigator.
- *Depends on:* P3, P5, P6, P7.

**P9 — F1 cross-bank coordinator**

- *Goal:* full LLM agent that receives `Sec314bQuery` from one bank's A2, validates purpose, broadcasts redacted queries to peer banks' A2s, and aggregates responses.
- *Files:* `backend/agents/f1_coordinator.py`, `backend/agents/prompts/f1_system.md`.
- *Approach:* F1 is stateless across queries (constraint enforced); LLM decides which peer banks the query is relevant to and how to phrase the broadcast. Bypasses force F5-escalation on quota-exceeded and force parallel F3 routing on SDN-referencing queries.
- *Acceptance:* given a valid `Sec314bQuery` from one bank, F1 emits redacted queries to the other two banks and returns an aggregated `Sec314bResponse` to the requester; rejects queries missing the purpose declaration; an invalid SDN reference triggers the F3 parallel-route bypass.
- *Depends on:* P5, P8.

**P10 — F3 sanctions / PEP screening agent**

- *Goal:* full LLM agent that receives entity hashes and returns binary match flags against a mock SDN watchlist + PEP relation indicators.
- *Files:* `backend/agents/f3_sanctions.py`, `backend/agents/prompts/f3_system.md`, `data/mock_sdn_list.json`.
- *Approach:* mock list ≈10 well-known fictional names + the S1-D PEP entity's hash. LLM reasons about fuzzy matches; bypasses force exact-hash flags regardless of LLM judgment.
- *Acceptance:* exact-hash match returns `match=True`; PEP entity from S1 returns `pep_relation=True`; output schema strictly excludes list contents.
- *Depends on:* P5.

**P11 — F2 graph-analysis agent**

- *Goal:* full LLM agent that consumes DP-noised cross-bank pattern aggregates and identifies ring structures.
- *Files:* `backend/agents/f2_graph_analysis.py`, `backend/agents/prompts/f2_system.md`.
- *Approach:* input is pre-computed aggregate (edge-count distribution over hashed-counterparty pairs, summed per bank, DP-noised at each bank's stats-primitives layer via the `pattern_aggregate_for_f2` primitive). LLM reasons about structure consistency with structuring/layering typologies; bypasses force high-confidence surfacing for closed-cycle-on-3+-banks and for 4-hop fee-shaped layering.
- *Acceptance:* given the S1 aggregate signal pattern, F2 emits a `GraphPatternResponse` flagging a structuring ring with high confidence; given a random-noise input, F2 returns low confidence.
- *Depends on:* P5, P9.

**P12 — F4 SAR drafter agent**

- *Goal:* full LLM agent that synthesizes `SARContribution` messages + F2's pattern report + F3's sanctions findings into a structured SAR draft.
- *Files:* `backend/agents/f4_sar_drafter.py`, `backend/agents/prompts/f4_system.md`, `shared/sar_template.py`.
- *Approach:* fixed structured fields (filing institution, suspicious-amount-range, typology code, etc.) + LLM-generated narrative + per-contribution attribution. Bypasses force `sar_priority = high` on any sanctions match and force mandatory-field population.
- *Acceptance:* given S1-flow contributions + F2 ring report + F3 PEP flag, F4 emits a `SARDraft` with populated mandatory fields, per-bank attribution, and a narrative that references the §314(b) authority.
- *Depends on:* P5, P8, P10, P11.

**P13 — F5 compliance auditor agent**

- *Goal:* full LLM agent that subscribes to the live audit stream and emits compliance annotations + `HUMAN_REVIEW` escalations.
- *Files:* `backend/agents/f5_compliance_auditor.py`, `backend/agents/prompts/f5_system.md`.
- *Approach:* F5 reads `AuditEvent`s as they're written and decides whether anything looks like a fishing expedition or a §314(b) purpose mismatch. Bypasses force rate-limit warnings and force HUMAN_REVIEW on purpose-declaration mismatches.
- *Acceptance:* given a synthetic stream of 11 §314(b) queries from one investigator in 60 minutes, F5 emits a rate-limit warning; given a query whose stated purpose isn't ML/TF-shaped, F5 emits HUMAN_REVIEW.
- *Depends on:* P5, P15.

---

### Integration parts (P14–P18)

**P14 — AML Lobster Trap policy pack**

- *Goal:* LT policy that enforces the cross-agent rules declared in Section 8.3.
- *Files:* `infra/lobstertrap/packs/aml_pack.yaml`.
- *Approach:* role-authentication rules (A1 cannot send to peer-bank channels; only A2 and F-agents can); customer-name redaction at egress from any bank's A2; purpose-declaration requirement on every `Sec314bQuery`; audit-event emission on every cross-bank message.
- *Acceptance:* a P0-style test suite (`tests/test_aml_lt_pack.py`) drives positive cases (allowed messages pass) and negative cases (a customer name in a query body gets redacted; an A1 trying to send cross-bank gets blocked).
- *Depends on:* P4.

**P15 — Agent orchestrator / message bus**

- *Goal:* a single process that instantiates all 8 agent instances (3×A1, 3×A2, F1–F5), wires each bank's A2 to its local P7 stats-primitives layer, routes messages between them, and writes the audit stream.
- *Files:* `backend/orchestrator.py`, `backend/audit.py`.
- *Approach:* in-process message bus (no external broker needed for the demo); each agent has an inbox; the bus copies routed messages to the audit channel; orchestrator exposes a `step()` entry point that advances the next agent's turn (so the demo UI can drive the flow visibly). Each bank's A2 holds a handle to its own P7 layer; cross-bank `Sec314bResponse` provenance + ε debits surface in the audit stream.
- *Acceptance:* synthetic end-to-end test: drop a hand-crafted `Alert` into Bank Alpha's A2 inbox and watch the full canonical flow execute; audit channel records every hop including ε debits.
- *Depends on:* P5, P7, P12, P13.

**P16 — Canonical demo flow script**

- *Goal:* a reproducible script that drives the demo flow from a fixed seed without manual UI clicking.
- *Files:* `backend/demo/canonical_flow.py`.
- *Approach:* picks the deterministic S1 starting alert from Bank Alpha, calls `orchestrator.step()` in a loop until F4 emits a SAR draft, prints the audit stream to stdout.
- *Acceptance:* `uv run python -m backend.demo.canonical_flow` produces a SAR draft and an audit stream identical (modulo DP noise) across three consecutive runs.
- *Depends on:* P14, P15.

**P17 — End-to-end smoke test**

- *Goal:* automated test that runs the canonical flow against live Gemini through the LT/LiteLLM proxy chain.
- *Files:* `tests/test_e2e_demo.py`.
- *Approach:* opt-in test (skipped if `GEMINI_API_KEY` missing); asserts the SAR draft contains the expected typology code, the S1 entity hashes, the PEP flag, and at least 10 audit events including at least one ε debit.
- *Acceptance:* test passes against live Gemini; runtime < 3 minutes.
- *Depends on:* P16.

**P18 — Federation timeline + audit panel (terminal UI)**

- *Goal:* a terminal UI that shows the federation timeline beat-by-beat with LT verdicts and ε debits overlaid.
- *Files:* `backend/ui/timeline.py`.
- *Approach:* Rich-based two-pane layout: left = federation timeline (agent → agent message list with timestamps), right = audit-panel rolling log including ε meter per (investigator, peer-bank) pair. Driven by the orchestrator's audit stream. Designed for the screen-recording aspect ratio.
- *Acceptance:* visually clear during the canonical flow; readable at 1080p screen-recording resolution; ε meter visibly debits per DP-applied query.
- *Depends on:* P16.

---

### Polish + submission (P19–P22)

**P19 — README + mermaid diagrams for AML**

- *Goal:* README reads cleanly for someone who's never seen the repo; mermaid diagrams reflect AML architecture, not the legacy clinical one.
- *Files:* `README.md`, `data/README.md`.
- *Acceptance:* run instructions reproduce the canonical demo from a fresh clone in < 10 minutes (excluding API key setup).
- *Depends on:* P17.

**P20 — Pitch deck**

- *Goal:* 8–10 slide deck for the hackathon submission.
- *Files:* `docs/pitch_deck.pdf` (built from `docs/pitch_deck.md` if using a markdown-to-slide tool, or directly authored in a slide tool).
- *Slides:* (1) problem framing + §314(b) friction stack, (2) architecture with stats-primitives layer called out, (3) demo walkthrough, (4) where DP fits (and where it doesn't), (5) Verafin $2.75B comp + technical-vs-contractual-trust differentiation, (6) cross-vertical applicability, (7) Gemini + Lobster Trap partner alignment, (8) team + ask.
- *Depends on:* P18.

**P21 — Demo dry-run × 3 + screencast**

- *Goal:* three consecutive successful dry-runs; screencast recorded as live-demo backup.
- *Files:* `docs/demo_screencast.mp4`, `docs/demo_script.md`.
- *Acceptance:* three runs complete in < 3 minutes each with consistent outcomes; screencast is the canonical version.
- *Depends on:* P18, P20.

**P22 — Hackathon submission**

- *Goal:* submission form filled, repo public, all artifacts linked.
- *Acceptance:* confirmation email from TechEx received before May 19 23:59.
- *Depends on:* P21.

---

### Cut order if something runs hot

In rough priority order, the things that can drop without killing the demo:

1. **P13 (F5 compliance auditor)** → replace with a simpler audit-log dump in the terminal UI
2. **P12 (F4 SAR drafter)** → pre-draft a SAR for the demo and present it as agent output (annotate the slide)
3. **S2 / S3 secondary scenarios in P2 data** → already built; cost nothing to keep. If something downstream breaks because of them, narrow the demo to S1 + S4 (the headline + PEP) only
4. **P18 terminal UI** → fall back to plain stdout printing of the audit stream
5. **DP scope on P7** → fall back from real OpenDP composition to hand-rolled Gaussian + simple ε-counter if OpenDP integration eats more time than expected. The primitives layer itself stays; only the DP-rigor knob moves.

Do not cut: A1, A2, F1, F2, F3, the **stats-primitives layer (P7)** (the architecture's structural privacy claim depends on it), the AML LT policy pack (P14), the orchestrator (P15), the canonical flow (P16). These are the demo's spine.

---

## 12. Risks & Mitigations

- **Synthetic transaction data not realistic enough** — judges with banking experience may probe. Mitigation: cite published typologies (FinCEN, FFIEC) explicitly in the README; declare the dataset synthetic on stage; focus the demo on the federation mechanic rather than the realism of any single bank's transaction stream.
- **§314(b) framing inaccurate** — minor legal mischaracterization could be a credibility hit. Mitigation: the README cites the statute correctly and frames our claims modestly ("we built primitives that would make §314(b) easier to operationalize," not "we are §314(b)-compliant").
- **6 agents too complex for 3 days** — the agent surface area is real. Cut order if Day 3 runs hot: F5 (compliance auditor) first — replace with a simpler audit-log dump UI. Then F4 (SAR drafter) — pre-draft a SAR for the demo and present it as agent output. Don't cut F1, F2, F3, A1, A2 — these are the federation spine.
- **Demo latency** — 6 agents per query × network round trips may produce visible delays. Mitigation: parallelize where possible; pre-stage canonical demo queries with deterministic seeds so timing is predictable.
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
