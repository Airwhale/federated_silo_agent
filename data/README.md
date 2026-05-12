# `data/` — Hospital Silo Datasets and Build Scripts

This folder contains everything related to the demo's hospital silo data: build scripts, raw downloads, and the per-silo SQLite OMOP CDM databases that the federated computation system queries against.

> **For the agent picking up the data-layer task:** this README is your self-contained guide. Read [`../plan.md`](../plan.md) Sections 0, 9, and 11.2 (P2) first for context, then follow this doc step-by-step. You don't need any of the other parts of the project in your head — the data layer is independent of the LLM, Lobster Trap, and federated-stats stack.

---

## What this folder will contain

```
data/
├── README.md             # This file
├── scripts/              # Build pipeline (Python, committed)
│   ├── __init__.py
│   ├── download_synthea_omop.py
│   ├── split_silos.py
│   ├── feature_engineering.py
│   ├── apply_scenarios.py
│   └── validate.py
├── raw/                  # Downloaded Synthea-OMOP CSVs (gitignored)
└── silos/                # Five SQLite OMOP CDM databases (gitignored)
    ├── riverside.db
    ├── lakeside.db
    ├── summit.db
    ├── fairview.db
    └── coastal.db
```

Only `README.md` and `scripts/` are committed to git. Raw downloads and per-silo databases are produced reproducibly from a fixed seed; only the scripts are versioned.

---

## End state (what success looks like)

Five SQLite databases sitting at `data/silos/{silo}.db`, each containing:

- **OMOP CDM v5.4 tables** (`person`, `observation_period`, `visit_occurrence`, `condition_occurrence`, `drug_exposure`, `measurement`, `procedure_occurrence`, `death`, plus vocabulary tables) — see [OMOP CDM v5.4 spec](https://ohdsi.github.io/CommonDataModel/cdm54.html)
- **A derived `chf_cohort_features` table** with engineered analytical features per CHF patient
- **The four planted demo scenarios applied** as deterministic post-processing

### Per-silo composition

Each silo holds **1,000 cardiac patients** drawn from the AWS Synthea-OMOP 100K dataset. The 1,000 are restricted to patients with at least one cardiac diagnosis (CHF, CAD, AFib, post-MI, hypertensive heart disease, or valve disease). Within those 1,000:

- **~50 CHF patients** — the study cohort (ICD-10 I50.x / SNOMED 84114007)
- **~950 other heart disease** — the comparison group
- **~2 cardiac amyloidosis patients** synthetically labeled within the 50 CHF — rare subtype

### Pooled across all five silos

- ~250 CHF cases (enough for credible federated logistic with ~5 predictors)
- ~10 amyloid CHF cases (rare-subtype demonstration)
- ~4,750 other heart disease patients
- ~5,000 total patients

The 1,000-per-silo / 50-CHF-per-silo number is **deliberate, not a side effect of dataset size.** Single-silo logistic regression on ~10 readmission events is underpowered; pooled ~50 events is borderline-adequate for 5 predictors. The **visible CI shrinkage from single-site → federated is the demo's headline AI/stats moment for an AI-judge audience.**

### Silo identities

| Silo | Profile |
|---|---|
| `riverside` | Riverside General — academic medical center; older + higher acuity tilt |
| `lakeside` | Lakeside Medical — regional referral; balanced |
| `summit` | Summit Community Health — community hospital; younger + lower acuity |
| `fairview` | Fairview Regional — mid-size regional; slightly elevated diabetes prevalence |
| `coastal` | Coastal Medical Center — suburban; slightly higher BMI distribution |

The demographic/acuity tilts are intentionally small. They give the demo a believable "diverse hospital network" story without requiring the cohorts to be wildly different.

---

## Step 0: Orient yourself (5 minutes)

Read in order:

1. [`../README.md`](../README.md) — what the project is, architecture, primitives
2. [`../plan.md`](../plan.md) — full design doc; **specifically read Sections 0, 9 (Synthetic Data Strategy), and 11.2 P2**
3. This file — keep open as the step-by-step guide

Do not start coding before you've read the plan's Section 9. It defines the planted scenarios, cohort definitions, and target effect sizes that everything below operationalizes.

---

## Step 1: Verify prerequisites (10 minutes)

| Tool | Version | Verify | Install |
|---|---|---|---|
| Python | 3.11+ | `python --version` | https://www.python.org/downloads/ |
| `uv` (package manager) | latest | `uv --version` | `pip install uv` or https://github.com/astral-sh/uv |
| `gh` CLI | any | `gh auth status` | Already authenticated as `Airwhale` |
| `sqlite3` CLI | 3.x | `sqlite3 --version` | Comes with Python |

**You do NOT need:** Java, R, Docker, raw Synthea, OHDSI/ETL-Synthea. The pre-built AWS Synthea-OMOP dataset eliminates that whole pipeline.

---

## Step 2: Project Python environment (10 minutes)

From the repo root:

```bash
cd "C:/Users/scgee/OneDrive/Documents/Projects/federated_silo_agent"
uv init --python 3.11    # if pyproject.toml doesn't exist
uv add pandas numpy duckdb sqlite-utils requests tqdm pyarrow
uv add --dev pytest
```

Verify imports:

```bash
uv run python -c "import pandas, numpy, duckdb, sqlite_utils, requests; print('ok')"
```

Update `.gitignore` to exclude the data outputs (the actual `.db` files and raw downloads should not be committed):

```bash
cat >> .gitignore <<'EOF'

# Data layer outputs (reproducible from data/scripts/)
data/raw/
data/silos/*.db
data/silos/*.db-journal
data/silos/*.db-wal
data/silos/*.db-shm
EOF
```

Commit:

```bash
git add pyproject.toml uv.lock .gitignore
git -c "user.email=noreply@anthropic.com" -c "user.name=federated_silo_agent" commit -m "Add Python project + data-layer .gitignore

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

---

## Step 3: Download the Synthea-OMOP dataset (30–60 minutes wall-clock)

The AWS Open Data registry hosts pre-built Synthea-OMOP datasets in S3. Reference: https://registry.opendata.aws/synthea-omop/

Create `data/scripts/download_synthea_omop.py` that:

1. Downloads the **100K-patient Synthea-OMOP dataset** from its S3 public location (no AWS credentials required — use HTTPS public URLs).
2. Stores CSVs under `data/raw/synthea_omop_100k/`.
3. Verifies each expected OMOP CDM v5.4 table file is present and non-empty.
4. Prints rows per table + total disk usage.

**Expected OMOP tables (v5.4):**

Clinical tables: `person`, `observation_period`, `visit_occurrence`, `condition_occurrence`, `drug_exposure`, `measurement`, `procedure_occurrence`, `observation`, `death`.

Vocabulary tables: `concept`, `concept_relationship`, `concept_ancestor`, `vocabulary`, `domain`, `concept_class`, `relationship`, `drug_strength`.

Reference tables: `care_site`, `location`, `provider`.

**Fallback** if AWS URL has moved: use [Eunomia](https://github.com/OHDSI/Eunomia) (OHDSI's R package bundling small OMOP demo datasets). The underlying ZIPs are downloadable at `https://github.com/OHDSI/EunomiaDatasets/raw/main/datasets/...`. Eunomia's bundled Synthea-OMOP is smaller (~2,500 patients) — if you fall back, adjust patient-count targets proportionally and document in this README.

Run:

```bash
uv run python data/scripts/download_synthea_omop.py
```

Acceptance: `person.csv` shows ~100,000 rows; total raw download under 5 GB.

---

## Step 4: Filter + split into five silos (1 hour)

Create `data/scripts/split_silos.py` that:

1. Reads the raw 100K-patient OMOP CSVs (use `duckdb.read_csv` — much faster than pandas for these sizes).
2. **Filters to cardiac patients** — patients with at least one `condition_occurrence` row matching:
   - CHF: SNOMED concept_ids descending from 84114007, OR ICD-10 source values matching `I50%`
   - CAD: ICD-10 `I25%`
   - AFib: ICD-10 `I48%`
   - Post-MI: ICD-10 `I21%`/`I22%`/`Z86.7%`
   - Hypertensive heart disease: ICD-10 `I11%`
   - Valve disease: ICD-10 `I34%`–`I39%`
3. **Deterministically assigns cardiac patients to five silos** using `numpy.random.default_rng(seed=20260512)`.
4. For each silo, samples patients to hit the target composition:
   - Target total: 1,000 patients
   - Of which: 50 CHF + 950 other-cardiac
   - If the sample size is off by ±10%, adjust the seed-based sampling. Document the actual counts in the manifest.
5. Applies the demographic/acuity tilts per silo (see table above) — light touch via age and BMI biasing during the per-silo sampling, not a complete reshuffle.
6. **Builds five SQLite databases** at `data/silos/{silo_id}.db`, each containing:
   - Filtered OMOP clinical tables (`person`, `observation_period`, `visit_occurrence`, `condition_occurrence`, `drug_exposure`, `measurement`, `procedure_occurrence`, `observation`, `death`) — only the rows for that silo's 1,000 patients.
   - Vocabulary tables (`concept`, `concept_relationship`, `concept_ancestor`, `vocabulary`, `domain`, `concept_class`, `relationship`, `drug_strength`) — copied in full to every silo (reference data, not patient-specific).
   - Appropriate indexes on `person_id`, `concept_id`, and key date columns.
7. Prints per-silo summary: total patients, CHF count, other-cardiac count, encounter count.

Run:

```bash
uv run python data/scripts/split_silos.py
```

Acceptance: five `.db` files exist under `data/silos/`, each ~10–50 MB. Per-silo CHF count is 45–55; total cardiac count is 950–1050.

---

## Step 5: Derive the CHF cohort features (1 hour)

Create `data/scripts/feature_engineering.py` that, for each silo:

1. Identifies the **CHF cohort** — patients matching the CHF concept definition (SNOMED descendants of 84114007 + ICD-10 I50.x).
2. For each CHF patient, identifies a single **index encounter** (first CHF-related inpatient visit; if none, first CHF condition occurrence).
3. Computes features per CHF patient:

| Feature | Definition |
|---|---|
| `age_at_index` | Integer years at index encounter |
| `sex` | From `person.gender_concept_id` (M / F / Unknown) |
| `race` | From `person.race_concept_id` |
| `index_bmi` | Most recent BMI measurement within 90 days of index (LOINC 39156-5) |
| `index_ef` | Most recent ejection fraction within 180 days of index (LOINC 10230-1 / 8806-2 / 18043-0); range typically 5–80% |
| `prior_chf_admissions_12mo` | Count of CHF-coded inpatient visits in 12 months before index |
| `has_diabetes` | Any condition_occurrence matching ICD-10 E10%/E11% |
| `has_ckd` | Any condition_occurrence matching ICD-10 N18% |
| `gdmt_adherence` | Binary: at least one drug_exposure of (ACE/ARB) AND (beta-blocker) AND (diuretic) on or before discharge of index encounter. Starter RxNorm ingredient list: ACE/ARB — lisinopril, enalapril, losartan, valsartan; β-blockers — carvedilol, metoprolol, bisoprolol; diuretics — furosemide, spironolactone |
| `has_amyloid` | Initialized to 0 here; populated by `apply_scenarios.py` for the planted amyloid cohort |
| `readmit_30d` | Any inpatient visit_occurrence starting within 30 days after index encounter discharge |
| `los_index` | `visit_end_date − visit_start_date` for index, in days |

4. Writes the result to a `chf_cohort_features` table inside each silo's SQLite database (same `.db` file — NOT a separate file).

Run:

```bash
uv run python data/scripts/feature_engineering.py
```

Acceptance: each silo's `chf_cohort_features` table has 45–55 rows (one per CHF patient). All 12 columns populated (NULLs acceptable for missing measurements like `index_ef` when patients didn't have an echo).

Sanity check the totals:

```sql
SELECT 'riverside' AS silo, COUNT(*) AS chf_n FROM riverside.chf_cohort_features
UNION ALL SELECT 'lakeside', COUNT(*) FROM lakeside.chf_cohort_features
UNION ALL SELECT 'summit', COUNT(*) FROM summit.chf_cohort_features
UNION ALL SELECT 'fairview', COUNT(*) FROM fairview.chf_cohort_features
UNION ALL SELECT 'coastal', COUNT(*) FROM coastal.chf_cohort_features;
-- Expected: 45-55 per silo, ~250 total
```

---

## Step 6: Apply the four planted scenarios (2 hours)

Create `data/scripts/apply_scenarios.py`. The plan's Section 9.6 specifies four scenarios. Each is implemented as a deterministic modification of `chf_cohort_features` (and where appropriate, the underlying OMOP tables). Use the same fixed seed.

### Scenario 1: GDMT effect on readmission

**Effect:** patients with `gdmt_adherence = 1` have ~30% lower 30-day readmission rate vs non-adherent, controlling for everything else.

**Implementation:** for each CHF patient currently flagged `gdmt_adherence = 1 AND readmit_30d = 1`, flip `readmit_30d` to 0 with probability 0.30 (deterministic seed). Document this as "we artificially induce a 30% protective effect of GDMT adherence on readmission."

### Scenario 2: Diabetes + CKD heterogeneity

**Effect:** CHF + DM + CKD patients have *supra-additive* readmission risk. In a logistic regression `readmit ~ diabetes + ckd + diabetes:ckd`, the interaction term coefficient is positive and statistically distinguishable when pooled across silos.

**Implementation:** among CHF + DM + CKD patients currently flagged `readmit_30d = 0`, flip a fraction (e.g., 25%) to `readmit_30d = 1`. Result: the joint group's readmission rate is meaningfully higher than the additive prediction from DM-only and CKD-only rates.

**Important:** verify that no single silo has so few CHF+DM+CKD cases that the effect is detectable within that silo alone (the demo point is that *federation* is what unlocks this).

### Scenario 3: Hospital-level LOS variation

**Effect:** Riverside has ~1.3-day longer median index LOS than other silos, for matched acuity.

**Implementation:** update `los_index` in Riverside's `chf_cohort_features` by adding `1.3 + uniform(-0.5, 0.5)` days per CHF patient. Optionally also update the underlying `visit_occurrence.visit_end_date` for index encounters to keep tables consistent. Document.

### Scenario 4: Cardiac amyloidosis (the headline)

**Effect:** ~10 cardiac amyloidosis patients distributed across the 5 silos (~2 per silo). `has_amyloid = 1` is associated with ~1.8× elevated readmission risk. Per silo: useless sample size. Pooled: directional finding.

**Implementation:**
1. For each silo, randomly select ~2 CHF patients and flag `has_amyloid = 1` in `chf_cohort_features` (deterministic seed).
2. Insert a `condition_occurrence` row for each flagged patient with an amyloidosis concept_id (SNOMED 17552002 "Amyloid cardiomyopathy" or similar; if the exact concept isn't in the vocabulary tables, use a placeholder concept_id and document it).
3. For the flagged patients currently `readmit_30d = 0`, flip to `readmit_30d = 1` with probability 0.30 — net effect: amyloid patients have ~1.8× the baseline readmission rate (calibrated, document precisely).

### Outputs from apply_scenarios.py

Print a summary table:

```
Scenario                       | Expected effect      | Pooled actual | Pooled n
GDMT effect on readmission     | ~30% reduction       |   X%          |  N
DM+CKD heterogeneity           | supra-additive       |   OR=X        |  N triple-pos
Hospital LOS variation         | Riverside +1.3d      |   X.X days    |  Riverside CHF n
Amyloid rare cohort            | ~1.8× readmit ratio  |   X.X         |  ~10 amyloid
```

The summary IS the validation for scenario application. If any line is off, fix it before proceeding.

Run:

```bash
uv run python data/scripts/apply_scenarios.py
```

---

## Step 7: Validate everything (30 minutes)

Create `data/scripts/validate.py` that runs PASS/FAIL checks and prints results. Use pytest-style assertions but make it executable as a script.

Checks:

1. **All five databases exist** at `data/silos/{silo}.db` and are queryable.
2. **Each silo has ~1,000 patients** in `person` (within ±10%).
3. **Per-silo CHF cohort sizes** are 45–55.
4. **Per-silo other-cardiac counts** are ~950 (within ±10%).
5. **`chf_cohort_features` table** has the expected 12 columns with non-degenerate cardinality.
6. **Scenarios are recoverable centrally** on the pooled (union of all 5 silos) cohort:
   - GDMT-adherent readmission rate is meaningfully lower than non-adherent (>20% relative reduction)
   - CHF+DM+CKD readmission rate is supra-additive (logistic interaction term positive)
   - Riverside median LOS > Lakeside median LOS by ~1 day
   - Amyloid pooled count is 8–12; amyloid pooled readmit rate is ~1.5–2.5× baseline
7. **Scenarios 2 and 4 are NOT credibly recoverable from any single silo alone** (CIs wide enough that the effect isn't statistically distinguishable per-silo) — this confirms the federation power story.
8. **Indexes are present** on `person_id` and key date columns in each silo.

Run:

```bash
uv run python data/scripts/validate.py
```

Acceptance: all checks PASS. **Do not proceed to commit without all PASS.**

---

## Step 8: Update this README with actuals (15 minutes)

After validate.py passes, update the `## Run summary` section at the bottom of this file with:

- Date of last successful regeneration
- Random seed used
- Actual per-silo counts (CHF, other-cardiac, total)
- Actual scenario effect sizes from validate.py output
- Total disk usage of `data/silos/*.db`

---

## Step 9: Commit and push (10 minutes)

**Make sure no `.db` files or raw downloads are staged.** From the repo root:

```bash
git status        # confirm: no *.db, no data/raw/
git add data/scripts/ data/README.md
git -c "user.email=noreply@anthropic.com" -c "user.name=federated_silo_agent" commit -m "$(cat <<'EOF'
Add data-layer pipeline for five-silo OMOP CDM hospital datasets

Pipeline:
- download_synthea_omop.py: pulls AWS Synthea-OMOP 100K dataset
- split_silos.py: filters to cardiac patients, samples 5 silos of 1,000
  each with target composition (~50 CHF + ~950 other-heart-disease)
- feature_engineering.py: derives chf_cohort_features per silo
  (age_at_index, index_ef, gdmt_adherence, comorbidities, readmit_30d,
  los_index, has_amyloid placeholder)
- apply_scenarios.py: applies the four planted scenarios deterministically
  (GDMT protective effect, DM+CKD supra-additive, Riverside LOS bias,
  cardiac amyloidosis rare subtype)
- validate.py: PASS/FAIL checks confirming scenarios are recoverable
  centrally on pooled data but NOT on single silos (the federation
  power story is mathematically real, not narrative-only)

Output: five SQLite OMOP CDM v5.4 databases at data/silos/ (gitignored).
Schema follows OHDSI standards; system is plug-compatible with real
OMOP-formatted hospital data post-hackathon.

Reference: ../plan.md Section 9 (Synthetic Data Strategy), Section 11.2 P2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Acceptance criteria (exit conditions for this task)

- [ ] Five SQLite databases exist under `data/silos/` (riverside.db, lakeside.db, summit.db, fairview.db, coastal.db)
- [ ] Each is queryable via `sqlite3` and has OMOP CDM v5.4 tables
- [ ] Each silo has ~1,000 patients, ~50 CHF, ~950 other-cardiac
- [ ] `chf_cohort_features` table populated per silo with all 12 features
- [ ] `validate.py` passes all checks
- [ ] Five Python scripts under `data/scripts/` are committed and pushed
- [ ] This README's "Run summary" section is updated with actual counts and seed
- [ ] `.db` files and `data/raw/` are NOT in git history
- [ ] All four planted scenarios produce expected effect sizes when queried on the pooled cohort
- [ ] Scenarios 2 and 4 do NOT produce credible effects on single silos alone (this is the federation power claim)

---

## Failure modes

**AWS Synthea-OMOP URL has moved:** fall back to Eunomia (smaller). Adjust target patient counts proportionally. Document in this README.

**100K dataset is too large for the dev machine:** use the 1K dataset from the same bucket. CHF cohort will be too small — switch to "the demo data is illustrative only" framing and shrink silo targets.

**Cardiac-patient cohort is too small after filtering:** broaden the cardiac-condition inclusion criteria (add more ICD-10 ranges).

**CHF cohort sizes are way off target:** Synthea's CHF prevalence may differ from real epidemiology. Adjust the sampling ratio so each silo lands at ~50 CHF. Document the actual prevalence in the source data.

**GDMT adherence rates are all zero:** Synthea's prescription patterns may not produce many patients meeting the full ACE+β-blocker+diuretic combo. Loosen to "at least 2 of 3 drug classes." Document the relaxation.

**Amyloidosis concept_id not in OMOP vocabulary:** use a placeholder integer concept_id (e.g., 99999001) and document it. Real OMOP installations would map this to SNOMED 17552002.

If something fails not covered here: document the issue, your decision, and rationale at the bottom of this README. The next agent (and future you) need to know what you decided.

---

## Time budget

| Step | Estimate |
|---|---|
| 0–1. Orient + verify prerequisites | 30 min |
| 2. Python environment + .gitignore | 15 min |
| 3. Download Synthea-OMOP | 30–60 min wall-clock |
| 4. Split into 5 silos | 1 hour |
| 5. Feature engineering | 1 hour |
| 6. Apply scenarios | 2 hours |
| 7. Validate | 30 min |
| 8. Update this README | 15 min |
| 9. Commit + push | 10 min |
| **Total** | **~6–7 hours** |

If hitting 12+ hours: write a status note at the bottom of this file describing what's working, what's stuck, and what the next agent should try.

---

## Run summary

> _This section is updated after each successful build. Currently: not yet run._

- **Last regeneration:** (none yet)
- **Random seed:** `20260512` (to be confirmed at first run)
- **Per-silo actuals:** _TBD_
- **Scenario effect sizes:** _TBD_

Good luck.
