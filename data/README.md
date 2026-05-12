# `data/` — Hospital Silo Datasets

Five synthetic hospital silo databases in OMOP Common Data Model (CDM) v5.4 format, used by the federated computation system as the per-silo data sources. Each silo holds ~363 cardiac patients drawn from a Synthea-derived source pool, with ~50 patients synthetically labeled as Congestive Heart Failure (CHF). Four "planted" scenarios are embedded so the federated-statistics demo can land predictably.

The actual `.db` files are not committed to git (they're reproducible from a fixed random seed and the scripts here). See [Regenerating the data](#regenerating-the-data) below.

---

## What's in this folder

```
data/
├── README.md             # This file — describes the dataset and how it was built
├── scripts/              # Build pipeline (committed)
│   ├── __init__.py
│   ├── vocab.py                  # In-repo OMOP concept-id map
│   ├── download_synthea_omop.py  # Pulls source CSVs from AWS Open Data
│   ├── build_silos.py            # Creates 5 silo SQLite DBs
│   ├── feature_engineering.py    # Derives chf_cohort_features
│   ├── apply_scenarios.py        # Applies the 4 planted scenarios
│   └── validate.py               # PASS/FAIL battery
├── raw/                  # Downloaded Synthea-OMOP CSVs (gitignored)
└── silos/                # Output SQLite databases (gitignored)
    ├── riverside.db
    ├── lakeside.db
    ├── summit.db
    ├── fairview.db
    └── coastal.db
```

---

## The five silos

| Silo ID | Hospital identity | Profile bias |
|---|---|---|
| `riverside` | Riverside General | Academic medical center; older + higher acuity tilt |
| `lakeside` | Lakeside Medical | Regional referral; balanced |
| `summit` | Summit Community Health | Community hospital; younger + lower acuity |
| `fairview` | Fairview Regional | Mid-size regional; slightly elevated diabetes |
| `coastal` | Coastal Medical Center | Suburban; slightly higher BMI distribution |

Each silo's SQLite database contains a subset of OMOP CDM v5.4 clinical tables (filtered to that silo's patient population) plus a derived `chf_cohort_features` table.

### Per-silo actuals (current build)

| Silo | Total cardiac patients | CHF (injected) | DB size |
|---|---:|---:|---:|
| riverside | 363 | 50 | 12.3 MB |
| lakeside | 363 | 50 | 12.3 MB |
| summit | 363 | 48 | 12.3 MB |
| fairview | 363 | 52 | 12.3 MB |
| coastal | 363 | 51 | 12.3 MB |
| **Pooled across all 5** | **1,815** | **251** | — |

---

## How the data was generated

### 1. Source pool

We downloaded the **1,000-patient Synthea-OMOP dataset** from the [AWS Open Data Registry](https://registry.opendata.aws/synthea-omop/) (S3 bucket `synthea-omop/synthea1k/`). [Synthea](https://synthetichealth.github.io/synthea/) is MITRE's open-source synthetic patient generator; the AWS version is pre-transformed into OMOP CDM v5.4 by OHDSI. Total source: 1,130 synthetic patients (~28 MB of plain CSV across 10 OMOP tables).

We deliberately did *not* use the 100k Synthea-OMOP dataset on the same S3 bucket because it's LZO-compressed and requires a C toolchain we didn't want to take on as a dependency for an 8-day hackathon build.

### 2. Cohort filtering

From the 1,130-patient source pool, we filtered to patients with **at least one cardiac condition** — i.e., at least one `condition_occurrence` row matching one of these OMOP concept_ids:

- `316139` Heart failure (we inject this — see below)
- `4329701` Amyloid cardiomyopathy (we inject this for Scenario 4)
- `317576` Coronary arteriosclerosis (CAD)
- `313217` Atrial fibrillation
- `4329847` Myocardial infarction
- `316866` Essential hypertension

This yielded **363 cardiac patients** in the source pool.

### 3. Replication across five silos

The source pool was replicated into five silos, each holding all 363 cardiac patients with:

- **`person_id` offsets** per silo (e.g., Riverside adds `1,000,000` to every patient ID, Lakeside adds `2,000,000`, etc.) — so cross-silo, the same source patient appears under different IDs and the federation engine treats them as independent records.
- **Per-silo demographic tilts** applied to the `person` table (small age shifts of ±4 years to differentiate populations) and to BMI measurements (±2–5% multiplier).
- **Independent CHF label assignment** per silo (next step).

This replication-with-perturbation approach is a deliberate choice for the demo:

- Pro: each silo is statistically distinguishable, the federation engine has 5 independent "hospitals" to query.
- Con: the underlying source patients overlap across silos (with different IDs).

For the AI-judge demo's purposes — where the headline is the *federated computation correctness and privacy story*, not patient-overlap auditing — this trade is fine. A real-data deployment would obviously use disjoint patient populations per silo.

### 4. Synthetic CHF injection

The 1k Synthea source pool contains **zero** patients with heart failure SNOMED codes (Synthea's small populations under-generate rare-ish conditions). We synthetically label 48–52 patients per silo as CHF by inserting a `condition_occurrence` row with `condition_concept_id = 316139` (Heart failure) and `condition_source_value = 84114007` (the SNOMED code for heart failure). The onset date is placed at a patient's median real visit date so the temporal context is plausible.

**This is the most consequential deviation from real data.** It's defensible because:

- The OMOP CDM schema, table structure, and concept_ids are real — anything downstream of the data layer (the federated computation, the planner LLM, the DP layer) sees exactly the same shapes it would see on a real OMOP database.
- The hackathon demo is for an AI-expert audience, not a clinical audience — they care about the federated-statistics mechanics, not clinical realism.
- We're applying planted scenarios on top anyway, so the data was always going to be partially synthetic at the outcome level.

In a post-hackathon production deployment, this layer would be replaced by real OMOP-formatted hospital data from an actual research network — the rest of the system needs zero code change to switch.

### 5. Feature engineering (`chf_cohort_features` table)

For each CHF patient, we derived an analytical features table:

| Column | Source / definition |
|---|---|
| `person_id` | from OMOP `person` |
| `chf_onset_date` | min `condition_start_date` for any CHF condition_occurrence |
| `age_at_index` | years between `birth_datetime` and `chf_onset_date` |
| `sex` | from `gender_concept_id` (M / F / Unknown) |
| `race` | from `race_concept_id` |
| `index_bmi` | most recent BMI within 365 days of index (LOINC 39156-5); sampled from `N(28, 5)` when no real measurement available |
| `index_ef` | most recent ejection fraction within 365 days (LOINC 10230-1 / 8806-2 / 18043-0); sampled from `N(42, 12)` when no real measurement available |
| `prior_chf_admissions_12mo` | count of inpatient visits in 12 months before index |
| `has_diabetes` | from `condition_occurrence` matching diabetes concept; or sampled at 35% when source data is sparse |
| `has_ckd` | from `condition_occurrence` matching CKD concept; or sampled at 20% when source data is sparse |
| `gdmt_adherence` | binary composite (any ACE/ARB drug AND any beta-blocker AND any diuretic); sampled at 45% when source drug data is sparse |
| `has_amyloid` | binary; populated by `apply_scenarios.py` for the planted amyloid cohort |
| `readmit_30d` | any inpatient visit within 30 days of index discharge; sampled at ~25% baseline when source data is sparse |
| `los_index` | length of stay (days) for the index encounter |

Where Synthea's source pool was too sparse to populate a field with real data, we fell back to clinically-plausible synthetic values — explicitly documented as such in `feature_engineering.py`. This is again a hackathon-demo concession: the OMOP schema is real, the features have realistic distributions, but the joint dependencies between them are not learned from real patient trajectories.

### 6. Planted scenarios

Four scenarios are applied to `chf_cohort_features` (and the underlying `condition_occurrence` table for the amyloid one) deterministically from `random.default_rng(seed=20260512)`.

| # | Scenario | Implementation | Target effect | Actual (pooled) |
|---|---|---|---|---|
| 1 | **GDMT protective effect on readmission** | Among GDMT-adherent CHF patients currently `readmit_30d=1`, flip 30% to `0`. | ≥15% relative reduction | non-adherent **27.0%** vs adherent **18.4%** = **31.8% relative reduction** |
| 2 | **Diabetes + CKD heterogeneity** | Among CHF+DM+CKD patients, bump readmit rate to ~40% via random `0→1` flips. | Triple-positive readmit > baseline | Triple-positive **33.3%** vs baseline **22.7%** (n=3 — sparse but directional) |
| 3 | **Hospital-level LOS variation** | Add `+1.3 ± 0.5` days to every Riverside CHF patient's `los_index`. | Riverside LOS bias 0.7–2.0d | Riverside **6.22d** vs other silos **5.07d** = **+1.15d** |
| 4 | **Cardiac amyloidosis rare subtype (the headline)** | Mark 2 CHF patients per silo with `has_amyloid=1`; insert amyloid `condition_occurrence` rows; bump their `readmit_30d` rate. | 8–12 pooled; ≥1.5× baseline readmit | n=**10 pooled** (2 per silo); amyloid readmit **70.0%** vs baseline **22.7%** = **3.08× ratio** |

### 7. Validation

`validate.py` runs a PASS/FAIL battery confirming all four scenarios are recoverable centrally (i.e., the demo will land when queries pool across silos) and that **no single silo has more than 2 amyloid patients** — i.e., single-site inference about the rare subtype is genuinely useless, which is the headline federation-power claim.

Current status: **all checks PASS**.

---

## OMOP CDM tables present in each silo

Each silo's SQLite database contains these OMOP CDM v5.4 clinical tables (filtered to that silo's 363 cardiac patients):

- `person`
- `observation_period`
- `visit_occurrence`
- `condition_occurrence` (includes synthetically-injected CHF and amyloid rows)
- `drug_exposure`
- `measurement`
- `observation`
- `procedure_occurrence`

Plus the derived analytics table:

- `chf_cohort_features`

**Not present in this build:**

- OMOP vocabulary tables (`concept`, `concept_relationship`, `concept_ancestor`, etc.). The AWS Synthea-OMOP datasets don't include these. We work around this with `data/scripts/vocab.py`, an in-repo concept-id map for only the conditions, drugs, and measurements the demo needs. A production deployment would attach the full OHDSI vocabulary (~hundreds of MB).
- `death` table (Synthea 1k pool doesn't emit one for this size).
- `care_site`, `location`, `provider` (not needed for our queries).

---

## Random seed and determinism

Master seed: **`20260512`** (set in every script).

Re-running any of the build scripts with the same seed produces bit-identical SQLite databases. The pipeline is fully deterministic.

---

## Regenerating the data

From the repo root, in order:

```bash
# 1. Download the source pool (~28 MB, takes ~20s on a reasonable connection)
uv run python data/scripts/download_synthea_omop.py

# 2. Build the five silo databases (~5s)
uv run python data/scripts/build_silos.py

# 3. Derive chf_cohort_features per silo (~2s)
uv run python data/scripts/feature_engineering.py

# 4. Apply the four planted scenarios (~1s)
uv run python data/scripts/apply_scenarios.py

# 5. Verify everything (~1s)
uv run python data/scripts/validate.py
```

End-to-end wall-clock from cold: ~30 seconds (mostly the download).

If you've already downloaded `data/raw/synthea_omop_1k/`, steps 1 is skipped automatically (the download script is idempotent on already-present files).

---

## Caveats and honest documentation

What's real vs. what's synthetic, summarized:

| Element | Status |
|---|---|
| OMOP CDM v5.4 schema, table names, column names, foreign-key relationships | Real |
| OMOP concept_ids used for conditions, drugs, measurements | Real (mapped via `vocab.py`) |
| Source patient demographics (age, sex, race), visit history, prescription patterns, lab measurements | Synthetic (from Synthea — realistic distributions, not real people) |
| CHF cohort assignment (which patients have heart failure) | **Synthetic injection** — the 1k source pool has no native CHF patients |
| Diabetes / CKD comorbidity labels | Mixed — real where Synthea generated them; synthetic backfill at 35% / 20% rates where it didn't |
| GDMT adherence labels | Mixed — real where the drug_exposure data contained the GDMT ingredients; synthetic at 45% otherwise |
| BMI and ejection fraction values for CHF patients | Real where Synthea measured them; synthetic from `N(28, 5)` and `N(42, 12)` otherwise |
| 30-day readmission outcomes | Mixed — real where inpatient visit_occurrence data supported them; synthetic at ~25% baseline otherwise |
| The four planted scenarios (GDMT effect, DM+CKD heterogeneity, Riverside LOS bias, amyloid cohort) | Synthetic by design — deliberately injected so the demo lands predictably |
| Inter-silo patient overlap | Same source patients appear in all five silos with different `person_id` offsets (replication-with-perturbation) |

The federated computation system, Lobster Trap policy proxy, OpenDP integration, and statistical pipeline behave identically on this synthetic data and on real OMOP-formatted hospital data. Switching to a real-data deployment requires zero code changes outside the `data/` folder.
