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

The 2001 USA PATRIOT Act §314(b) explicitly authorizes financial institutions to share information about suspected money laundering and terrorist financing. In practice, banks barely use §314(b) because of (a) legal-team risk aversion ("what if the disclosure isn't actually authorized?"), (b) lack of standardized infrastructure for safe sharing, (c) fear of customer privacy lawsuits if anonymization fails.

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
4. Demonstrate **DP-protected aggregate pattern signals** — banks share aggregated transaction-pattern statistics, not transactions.
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

Three banks each run two persistent agents (transaction-monitoring + investigator). A central federation layer in an assumed TEE hosts four cross-cutting specialist agents (graph analyst, sanctions screener, SAR drafter, compliance auditor). All inter-agent communication flows through Lobster Trap, which enforces §314(b)-style information-sharing rules. Aggregate transaction-pattern statistics are shared under differential privacy; raw transactions never cross bank boundaries.

Four orthogonal mechanisms:

- **Lobster Trap polices NL agent-to-agent channels** — what one agent can say to another about a third party's customers
- **Schema validation polices the structured-aggregate channel** — only pre-declared sufficient-statistic shapes can leave a bank
- **Differential privacy polices aggregate leakage** — pattern signals shared across banks are DP-noised with per-bank budgets
- **Agent-role authentication** — each agent's outbound message includes role metadata that LT verifies against policy (e.g., a transaction-monitoring agent can emit alerts but cannot directly query peer banks; only investigator agents can cross trust boundaries)

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
   ┌────────┐  ┌────────┐  ┌────────┐
   │Bank α  │  │Bank β  │  │Bank γ  │
   │A1 + A2 │  │A1 + A2 │  │A1 + A2 │
   │ SQLite │  │ SQLite │  │ SQLite │
   └────────┘  └────────┘  └────────┘
```

LLM wire path: `agent → Lobster Trap (port 8080) → LiteLLM (port 4000) → Gemini API`. All six agents share the same wire path; each is identified by an agent_id and role in the LT request metadata.

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

#### Bank-local agents (×3 banks)

**Agent A1: Transaction-monitoring agent** (one per bank, identical role)

- **Role:** Watches transaction stream; flags suspicious patterns (structuring, unusual velocity, round-dollar transfers near reporting thresholds, transfers to/from sanctioned-corridor jurisdictions).
- **Inputs:** Bank's local transaction log
- **Outputs:** Alerts (typed: alert_id, alert_type, severity, involved_accounts_hashed, supporting_signals)
- **LT policy:** Can only emit alerts to local investigator agent; cannot communicate cross-bank
- **Implementation:** Rule-based + light LLM scoring for ambiguous cases

**Agent A2: Investigator agent** (one per bank, identical role; the protagonist)

- **Role:** Picks up alerts; decides what to chase; can query the cross-bank coordinator under §314(b) authorization; synthesizes findings.
- **Inputs:** Alerts from local A1; responses from F1 (cross-bank coordinator)
- **Outputs:** Internal triage decisions; cross-bank coordination requests; SAR-draft contributions
- **LT policy:** Authorized to send §314(b) queries; cannot expose customer names in outbound messages (LT redacts); receives only anonymized peer-bank signals

#### Federation-layer agents (in assumed TEE)

**Agent F1: Cross-bank coordinator agent**

- **Role:** Receives §314(b)-flagged queries from bank investigators; broadcasts to peer banks' investigators; aggregates responses; mediates the conversation.
- **LT policy:** Cannot retain customer identifiers; must log every query/response in the audit channel; enforces purpose-declaration on every relayed message

**Agent F2: Graph-analysis agent**

- **Role:** Receives anonymized transaction-pattern aggregates from multiple banks; assembles cross-bank transaction graphs; identifies ring structure via community detection.
- **LT policy:** Only operates on DP-noised aggregates; never sees raw transactions

**Agent F3: Sanctions / PEP screening agent**

- **Role:** When investigators submit anonymized entity hashes, checks against watchlists; returns binary "on list" or "PEP relation" without exposing list details.
- **LT policy:** Cannot return list contents; only binary match signal

**Agent F4: SAR drafter agent**

- **Role:** Synthesizes findings from one or more investigators into a regulatory-filing draft (Suspicious Activity Report).
- **LT policy:** Final SAR draft is filing-quality; outputs must include declared-purpose justifications

**Agent F5: Compliance auditor agent**

- **Role:** Watches the multi-agent conversation stream; flags any communications that exceed §314(b) authorization or that look like fishing expeditions; presents human-readable audit summary.
- **LT policy:** Read-only; cannot suppress audit events

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

## 11. Build Plan — 3-day execution *(Develop)*

### Day 1: Data layer + agent scaffolding

| Hour | Task |
|---|---|
| 0–2 | Plan/README migration ✓ (done as part of the pivot) |
| 2–4 | Write `data/scripts/build_banks.py` — generate 3 banks with ~5K customers + 50K transactions each |
| 4–6 | Write `data/scripts/plant_ring.py` — embed the 5-entity structuring ring |
| 6–8 | Write `data/scripts/validate_banks.py` + new checksum test; verify ring is centrally detectable |

### Day 2: Agent implementation

| Hour | Task |
|---|---|
| 0–2 | Define Pydantic message schemas in `shared/messages.py` (Alert, Sec314bQuery, Sec314bResponse, GraphPatternRequest, SanctionsCheckRequest, SARDraft, AuditEvent) |
| 2–4 | Implement A1 (transaction monitoring) — rule-based + LLM-scoring helper |
| 4–6 | Implement A2 (investigator) — orchestrates §314(b) queries |
| 6–8 | Implement F1 (coordinator) + F3 (sanctions) — the simpler federation agents |

### Day 3: Federation + demo + polish

| Hour | Task |
|---|---|
| 0–2 | Implement F2 (graph analysis) — aggregate-only ring detection |
| 2–4 | Implement F4 (SAR drafter) + F5 (compliance auditor) |
| 4–5 | AML-specific Lobster Trap policy pack — §314(b) rules, role authentication, customer-name redaction |
| 5–7 | End-to-end demo dry-run; record screencast |
| 7–8 | Update README + pitch deck |

### Buffer

Day 4 is the explicit buffer day before May 18 onsite + May 19 demo. Day 3 should end with a working demo; Day 4 is for polish, slipped tasks, and rehearsal.

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
