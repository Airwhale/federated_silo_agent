# federated_silo_agent

**Multi-agent cross-bank AML investigation system with privacy-preserving federation.**

Three synthetic banks each run a transaction-monitoring agent and an investigator agent. When suspicious activity surfaces at one bank, the investigator agent coordinates with peer-bank investigators through a federation layer in an assumed TEE. Specialist agents (graph analyst, sanctions screener, SAR drafter, compliance auditor) compose investigations across the network. **Every cross-bank conversation is policed by Veea Lobster Trap. Aggregate transaction patterns are shared under differential privacy. No customer data ever crosses bank boundaries.**

Built for the [TechEx Intelligent Enterprise Solutions Hackathon](https://lablab.ai/ai-hackathons/techex-intelligent-enterprise-solutions-hackathon), May 11–19, 2026. Primary submission track: **Track 4, Data & Intelligence**. Partner-award strategy: **Gemini** powers all six agents (Google partner award); **Veea Lobster Trap** is the policy substrate (Veea partner award). Pitch comp: **Verafin → Nasdaq $2.75B (2020)** for the non-private version of exactly this. See [`plan.md`](./plan.md) for the full product design doc.

> **Pivot note (May 12, 2026):** this project pivoted from clinical federated stats (Synthea-OMOP, CHF cohort) to cross-bank AML mid-build, when the AI-hackathon framing made the multi-agent texture of AML the better fit. Clinical work is preserved in [`docs/clinical-archive/`](docs/clinical-archive/) and [`data/scripts/clinical-archive/`](data/scripts/clinical-archive/). Mermaid diagrams below still reflect the prior clinical architecture and will be replaced with AML versions during Day 3 of the new build.

---

## What this is

A multi-agent federated AML investigation platform. Three layers:

1. **Six agents talking to each other.** Two bank-local agents (transaction monitoring + investigator) at each of three banks, plus four federation-layer agents (cross-bank coordinator, graph analyst, sanctions screener, SAR drafter, compliance auditor) in an assumed TEE. All agents are powered by Gemini.
2. **Lobster Trap polices every inter-agent message.** §314(b) purpose-declaration enforcement, customer-name redaction on cross-bank queries, role-based authorization (only investigator agents can send cross-bank queries; transaction-monitoring agents can't).
3. **Privacy enforcement at silo egress.** Calibrated Gaussian noise via [OpenDP](https://github.com/opendp/opendp) on aggregate pattern signals. Per-user privacy budget tracked across queries. Schema validation prevents structural leakage of raw transactions.

**The demo scenario:** a 5-entity structuring ring spanning all three banks (Bank Alpha, Bank Beta, Bank Gamma). Each entity holds accounts at exactly two of the three banks. Sub-$10K transfers cycle through the ring over a 90-day window. Per-bank velocity stays just below each bank's individual alert threshold, so the ring is invisible to any single bank. **Federated agent coordination surfaces the ring in a 3-minute demo.** One entity has a PEP relation that the sanctions agent flags.

---

## Who it's designed for

| Persona | What they do | What this gives them |
|---|---|---|
| **AML investigator** at a participating bank | BSA/AML-certified specialist clearing a daily docket of alerts, most of which are false positives | Cross-bank investigation in minutes via §314(b)-authorized agent coordination, without exposing customer identities unless mutual leads warrant escalation |
| **BSA officer / Chief Compliance Officer** | Accountable for the bank's AML compliance posture; signs SARs; faces personal liability | Audit trail demonstrating every cross-bank disclosure was within §314(b) bounds — regulator-readable record |
| **AML consortium operator** (e.g., what Verafin built for credit unions) | Runs federation infrastructure on behalf of member banks | Privacy-preserving primitives that make §314(b) actually usable — without raw customer-data exchange |

**Not for** banks wanting full customer-data sharing (out of scope by design — the federation's value is *not* sharing raw data), single-bank AML tooling, or real-time payment authorization. We're investigative, not authorization-time.

---

## Project structure

```
federated_silo_agent/
├── frontend/                # Researcher UI (Next.js + Tailwind, or Streamlit fallback)
│   └── app/
│       ├── page.tsx         # Chat panel + result renderer
│       ├── hospitals/       # Per-silo metadata + ε meter
│       └── audit/           # Live SSE feed of all governance events
│
├── backend/
│   ├── main.py              # FastAPI entrypoint
│   ├── aggregator/          # The central coordinator (runs in assumed TEE)
│   │   ├── planner.py       # NL → ComputationPlan (Gemini structured JSON)
│   │   ├── dispatcher.py    # Parallel + iterative fan-out to silos
│   │   ├── combine/         # Per-primitive numerical combiners (deterministic)
│   │   └── narrator.py      # Structured result → English summary
│   │
│   ├── silos/               # Per-hospital runtime (one process per silo)
│   │   ├── runner.py        # Generic silo agent
│   │   ├── stats/           # Per-primitive sufficient-statistic computers
│   │   ├── dp.py            # OpenDP Gaussian noise calibration
│   │   ├── budget.py        # Per-user ε ledger via zCDP/RDP composition
│   │   ├── schema.py        # Pydantic egress validator
│   │   └── filter_resolver.py  # Fuzzy NL filter → structured SQL (schema only)
│   │
│   ├── audit/
│   │   ├── tail.py          # Merge Lobster Trap JSONL + DP + schema events
│   │   ├── differencing.py  # Pattern auditor for differencing-attack sequences
│   │   └── api.py           # SSE stream to frontend
│   │
│   └── data/                    # Runtime data access helpers (future)
│
├── shared/
│   └── plans.py             # Pydantic ComputationPlan + SufficientStats schemas
│                            # (single source of truth, used by aggregator and silos)
│
├── infra/
│   ├── lobstertrap/
│   │   ├── base_policy.yaml          # Universal injection + off-scope rules
│   │   ├── packs/
│   │   │   └── hipaa_pack.yaml       # HIPAA Safe Harbor identifier rules
│   │   └── compose-policy.py         # Merge base + pack → effective policy
│   ├── litellm_config.yaml           # OpenAI-compatible routing to Gemini
│   └── docker-compose.yml            # litellm + N×lobstertrap + backend
│
├── tests/                   # pytest suite (equivalence, DP correctness, defense tests)
├── docs/
│   ├── demo_script.md       # Beat-by-beat demo timing
│   └── demo_screencast.mp4  # Live-demo backup
│
├── plan.md                  # Full product design doc + 40-part build plan
└── README.md                # This file
```

---

## Architecture

A researcher's question flows through three trust zones, each policed by a different mechanism.

```mermaid
flowchart TB
    subgraph Browser["Researcher's Browser"]
        Chat["Chat panel"]
        Hosp["Hospital view"]
        Aud["Audit panel"]
    end

    subgraph TEE["Aggregator (assumed in TEE)"]
        Planner["Planner LLM<br/>(NL → ComputationPlan)"]
        Disp["Dispatcher"]
        Comb["Combiner<br/>(deterministic math)"]
        Narr["Narrator LLM<br/>(result → English)"]
        LT_A["Lobster Trap<br/>(NL channel policy)"]
    end

    subgraph Silos["Five Hospital Silos (private, isolated) — 363 cardiac patients each, ~50 synthetic CHF"]
        S1["Riverside General<br/>(academic)"]
        S2["Lakeside Medical<br/>(regional)"]
        S3["Summit Community<br/>(community)"]
        S4["Fairview Regional<br/>(mid-size)"]
        S5["Coastal Medical Ctr<br/>(suburban)"]
    end

    Chat -->|NL query| Planner
    Planner -->|plan| Disp
    Disp -->|plan| S1
    Disp -->|plan| S2
    Disp -->|plan| S3
    Disp -->|plan| S4
    Disp -->|plan| S5
    S1 -->|DP-noised stats| Comb
    S2 -->|DP-noised stats| Comb
    S3 -->|DP-noised stats| Comb
    S4 -->|DP-noised stats| Comb
    S5 -->|DP-noised stats| Comb
    Comb --> Narr
    Narr -->|summary| Chat
    LT_A -.polices.- Planner
    LT_A -.polices.- Narr
    Comb -.audit events.- Aud
```

---

## The statistical pipeline

A single query's lifecycle. **Privacy is paid once, at silo egress (step 5–7).** Combine, finalize, and narrate are post-processing — free under DP closure.

```mermaid
flowchart LR
    Q["NL query"] --> P["1. Plan<br/>(LLM)"]
    P --> D["2. Dispatch<br/>(parallel<br/>or iterative)"]
    D --> LC["3. Local<br/>compute<br/>per silo"]
    LC --> DP["4. DP noise<br/>(calibrated to<br/>sensitivity)"]
    DP --> SV["5. Schema<br/>validate"]
    SV --> BG["6. Budget<br/>debit ε"]
    BG --> EG["7. Egress<br/>(structured JSON)"]
    EG --> CB["8. Combine<br/>(sum across silos)"]
    CB --> FN["9. Finalize<br/>(invert, iterate,<br/>compute SEs)"]
    FN --> NR["10. Narrate<br/>(LLM, policed)"]
    NR --> R["Result<br/>+ audit trail"]
```

For iterative methods (logistic, mixed-effects, Poisson), steps 2–7 repeat per Newton/REML iteration with each iteration debiting its own ε increment from the budget ledger.

---

## Trust mechanisms (defense in depth)

Three orthogonal mechanisms, each doing what it's best at:

```mermaid
flowchart TB
    subgraph NL["NL channels — policed by Lobster Trap"]
        direction TB
        AI["Analyst input"] -->|"injection? PHI<br/>extraction? off-scope?"| LT1["block / allow"]
        NO["Narrator output"] -->|"mentions individuals?<br/>names hospitals? cites<br/>numbers not in result?"| LT2["block / allow"]
    end

    subgraph NUM["Numerical channel — schema + DP + budget"]
        direction TB
        SUM["Silo sufficient stats"] --> SC["Schema validator:<br/>only known shapes pass<br/>(fails closed)"]
        SC --> NOISE["OpenDP Gaussian noise:<br/>calibrated to L2 sensitivity<br/>from declared clip ranges"]
        NOISE --> LEDG["Per-user ε ledger:<br/>zCDP/RDP composition<br/>across queries"]
    end

    subgraph DET["Audit & detection"]
        direction TB
        DA["Differencing-pattern auditor:<br/>flags suspect query sequences<br/>(e.g., cohort-of-11 then<br/>cohort-of-10-excluding-X)"]
        LOG["JSONL audit log:<br/>every plan, every emission,<br/>every block — replayable"]
    end
```

**Mapping attacks → defenses:**

| Attack | Defended by |
|---|---|
| Plain-English request for individual records | Lobster Trap (HIPAA Safe Harbor identifier rules) |
| Prompt injection ("ignore previous instructions...") | Lobster Trap (injection patterns) |
| LLM hallucinated numbers in narration | Lobster Trap (narrator egress: only cite structured-result numbers) |
| Compromised silo agent embeds raw rows | Schema validator (fails closed if shape mismatch) |
| Trivially-small cohort (n < k) | Schema validator (k-anonymity floor) |
| Single-query reconstruction / membership inference | DP Gaussian noise calibrated to sensitivity |
| Differencing attack (n vs n−1 cohort) | Differencing-pattern auditor + DP composition makes residual smaller than noise |
| Multi-query inference (repeat to average out noise) | Per-user ε budget exhausts; queries refused |

---

## A query in detail

Here's what happens when a researcher asks for a federated logistic regression — the demo's hero query:

```mermaid
sequenceDiagram
    actor R as Researcher
    participant A as Aggregator
    participant LT as Lobster Trap
    participant S1 as Riverside silo
    participant S2 as Lakeside silo
    participant S3 as Summit silo
    participant AU as Audit panel

    R->>A: "Logistic regression of 30-day<br/>readmission on age, BMI, EF,<br/>prior admits, DM, CKD"
    A->>LT: Analyst input check
    LT-->>A: ✓ allow
    A->>A: Planner LLM → ComputationPlan
    A->>AU: plan_emitted

    loop Newton iterations (typically 5–7)
        par parallel dispatch
            A->>S1: plan + current β_t
            A->>S2: plan + current β_t
            A->>S3: plan + current β_t
        end
        S1->>S1: compute g, H over filter,<br/>clip covariates, add DP noise,<br/>schema-validate, debit ε
        S2->>S2: same
        S3->>S3: same
        S1-->>A: (g₁, H₁, n₁) + DP params
        S2-->>A: (g₂, H₂, n₂) + DP params
        S3-->>A: (g₃, H₃, n₃) + DP params
        A->>A: G = Σgᵢ, H = ΣHᵢ
        A->>A: β_{t+1} = β_t − H⁻¹G
        A->>AU: epsilon_debit × 3 (one per silo)
    end

    A->>A: Compute SEs from final Hessian
    A->>A: Narrator LLM (structured → English)
    A->>LT: Narrator output check
    LT-->>A: ✓ allow (no PHI, only cited numbers)
    A-->>R: Coefficient table + CIs + English summary
    A->>AU: query_complete
```

Total ε consumed for this query: ~6 iterations × per-iteration ε = ~0.3 typically (out of a default 1.0 budget per session). The researcher sees the meter tick down per iteration on the audit panel.

---

## Statistical primitives supported

The engine ships with a comprehensive clinical-research toolkit. Every primitive is provably equivalent to centralized computation when DP is off; DP noise is calibrated to the primitive's L2 sensitivity given the plan's declared clip ranges.

### Descriptive

| Primitive | What it produces |
|---|---|
| `count` | Cohort size |
| `mean(x)` | Mean ± SEM |
| `variance(x)` / `stddev(x)` | Pooled variance and standard deviation |
| `proportion(num, den)` | Proportion with Wilson + Clopper-Pearson CIs |
| `quantile(x, q)` | Median, IQR, percentiles, min (`q=0`), max (`q=100`) |
| `histogram(x, bins)` | Distribution; mode and CDF derivable |
| `skewness(x)` / `kurtosis(x)` | Normality screening |
| `incidence_rate(events, person_time)` | Events per person-time with Garwood Poisson CI |

### Comparative

| Primitive | What it produces |
|---|---|
| `pearson(x, y)` | Pearson correlation r with CI |
| `t_test(x ~ group)` | Welch's two-sample t-test |
| `chi_square(var1, var2)` | χ² / Fisher's exact for contingency tables |
| `mann_whitney_u(x ~ group)` | Non-parametric two-sample comparison |

### Regression family

| Primitive | What it produces |
|---|---|
| `ols(y ~ X)` | Linear regression with coefficient CIs |
| `logistic(y ~ X)` | Binary classification with predicted probabilities |
| `poisson(y ~ X)` | Count regression |
| `negative_binomial(y ~ X)` | Overdispersed count regression |
| `mixed_effects(y ~ X + (1|hospital))` | Linear mixed model with random hospital intercept |
| `+ cluster_se` modifier | Sandwich estimator for cluster-robust standard errors |

### Model diagnostics

| Primitive | What it produces |
|---|---|
| `auc_roc(model, threshold_bins)` | ROC curve + AUC for binary classifiers |

### Compositional features

- **Multi-step plans** — DAG of primitives where later steps reference earlier results (`"top 3 comorbidities by readmission rate, then logistic within the top one"`).
- **Fuzzy filter resolution** — silos resolve NL filters like `"diabetic CHF patients over 65 on guideline therapy"` against schema metadata (never against rows) into structured WHERE clauses.

What's not supported, and why:
- **Cox proportional hazards / Kaplan-Meier survival** — partial likelihood and rank-based statistics don't decompose into clean sufficient statistics across silos.
- **Decision trees / random forests / GBT** — federated versions are research-heavyweight, out of scope for an 8-day build.
- **Arbitrary SQL** — silos do not run LLM-generated SQL. The set of primitives is the trust contract between aggregator and silos.

---

## Build status

In progress. The plan is decomposed into 40 self-contained build parts (`P0`–`P40`). See [`plan.md`](./plan.md) for the full specification and dependency graph.

| Phase | Parts | Status |
|---|---|---|
| Foundation (scaffold, schemas, silo runtime, closed-form stats) | P0–P11 | ☐ |
| Privacy stack (DP, budget, differencing auditor) | P12–P14 | ☐ |
| GLM family (OLS, logistic, DP variants) | P15–P19 | ☐ |
| Frontend (chat, audit, hospitals) | P20–P22 | ☐ |
| Validation + polish + submission | P23–P27 | ☐ |
| LLM-side extensions (multi-step, fuzzy filters) | P28–P29 | ☐ |
| Descriptive primitives | P30, P38, P39, P31, P40 | ☐ |
| Comparative & inferential primitives | P32, P33, P34, P35, P36, P37 | ☐ |

---

## Configuring the API key

The planner and narrator (and the benign smoke-test case) call Gemini through LiteLLM. You need a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) — free tier is generous, no credit card required.

```bash
# From the repo root
cp .env.example .env
# Then edit .env and set GEMINI_API_KEY=<your-key>
```

`.env` is gitignored. Three entry points read it:

| Entry point | How it picks up `.env` |
|---|---|
| `uv run python scripts/smoke_proxy.py` | `python-dotenv` loads `.env` automatically |
| `docker compose up` (from repo root) | Docker Compose auto-loads `.env` for `${GEMINI_API_KEY}` substitution |
| `scripts/start_litellm.ps1` (native Windows) | Parses `.env` and sets `$env:GEMINI_API_KEY` before launching LiteLLM |

If you'd rather set the key in your shell directly: `export GEMINI_API_KEY=...` (bash) or `$env:GEMINI_API_KEY = "..."` (PowerShell) also works for any entry point.

---

## How to use

> **Not yet runnable end-to-end.** P0 (proxy chain) is wired and the LT side is verified; the benign Gemini round-trip requires the API key above. Downstream parts (P1 schemas, P3 silo runtime, etc.) will fill out this section as they land.
>
> P0 proxy-chain notes live in [`docs/p0_proxy_chain.md`](docs/p0_proxy_chain.md).
>
> Expected sections, once built:
>
> - **Prerequisites** — Python 3.11+, Go 1.22+ for Lobster Trap, Node 20+ (or Streamlit-only path), a Gemini API key, and Docker if using the compose path.
> - **Installation** — `uv sync` for Python deps, `pnpm install` for the frontend, `docker compose up` for LiteLLM + Lobster Trap where Docker is available.
> - **Generating synthetic hospital data** — `uv run python data/scripts/download_synthea_omop.py`, then `build_silos.py`, `feature_engineering.py`, `apply_scenarios.py`, and `validate.py`.
> - **Running the demo** — `docker compose up`, navigate to `http://localhost:3000`, sign in as a researcher, ask a question.
> - **Example queries** — a curated set of NL queries demonstrating each primitive.
> - **Configuration** — per-silo `epsilon` caps, `k`-anonymity floor, policy pack selection.
> - **Tests** — `pytest` for the equivalence + DP correctness + defense suites.

---

## Acknowledgments

- [**Veea Lobster Trap**](https://github.com/veeainc/lobstertrap) — the open-source policy proxy that makes the LLM-channel governance story possible.
- [**OpenDP**](https://github.com/opendp/opendp) — Harvard / Microsoft / NSF differential privacy library.
- [**Synthea**](https://synthetichealth.github.io/synthea/) — MITRE's synthetic patient generator.
- [**Google Gemini**](https://ai.google.dev/) — the planner and narrator LLM provider for Track 4 and Gemini award alignment.
- [**LiteLLM**](https://github.com/BerriAI/litellm) — OpenAI-compatible routing from Lobster Trap to Gemini.

## License

TBD (likely MIT to match the underlying open-source stack).
