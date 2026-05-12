# Data Setup — Pre-P0 Work

> **For the agent reading this:** You're picking up an isolated task on the `federated_silo_agent` project. The work below is self-contained — you don't need to interact with the rest of the system yet. By the end you'll have produced three SQLite OMOP CDM databases (one per simulated hospital silo) with four "planted" demo scenarios applied, plus scripts that reproduce that work deterministically.
>
> **Working directory:** `C:\Users\scgee\OneDrive\Documents\Projects\federated_silo_agent` (Windows; bash CLI works fine).
> **GitHub repo:** `Airwhale/federated_silo_agent` (your `gh` CLI is already authenticated).
> **Branch:** work directly on `main`.

---

## 0. Orient yourself first (5 minutes)

Before doing anything, read these three files in order. They give you the full project context:

1. **`README.md`** — what the project is, who it's for, the three-layer architecture, the mermaid diagrams. Skim the architecture and the primitives table.
2. **`plan.md`** — full product design doc. **Specifically read:**
   - **Section 0 (TL;DR)**
   - **Section 9 (Synthetic Data Strategy)** — this is the most important section for your task; it describes the data schema, calibration sources, and the four planted scenarios you'll implement
   - **Section 11.2 P2** (synthetic data generator part) — the build-plan part this task corresponds to
3. **This file** — keep open as the step-by-step guide.

Do not start coding before you've read those sections. The plan defines the *shapes* (column names, planted-scenario effect sizes, cohort definitions) you're going to materialize.

---

## 1. What you're producing — the end state

Three SQLite databases sitting at:

```
data/silos/riverside.db      (~12,000 patients, "academic medical center" tilt)
data/silos/lakeside.db       (~8,000 patients,  "regional hospital" tilt)
data/silos/summit.db         (~6,000 patients,  "community hospital" tilt)
```

Each database:

- Follows **OMOP CDM v5.4 schema** (tables: `person`, `observation_period`, `visit_occurrence`, `condition_occurrence`, `drug_exposure`, `measurement`, `procedure_occurrence`, `death`, plus vocabulary tables — see [OMOP CDM v5.4 spec](https://ohdsi.github.io/CommonDataModel/cdm54.html)).
- Contains a CHF (congestive heart failure) study cohort identifiable via `condition_occurrence` rows with SNOMED `84114007` or ICD-10 `I50.x` codes.
- Has four **planted scenarios** materialized as data modifications (specified in §6 below).
- Has an additional **derived-features table** `chf_cohort_features` per silo for convenience — read-only summary per CHF patient (`age_at_index`, `index_bmi`, `index_ef`, `prior_chf_admissions_12mo`, `has_diabetes`, `has_ckd`, `gdmt_adherence`, `readmit_30d`, `los_index`).

You're also producing:

- **Python scripts under `backend/data/`** that recreate the databases deterministically from a fixed seed.
- **A short manifest** at `data/silos/README.md` describing what was built, the seed used, the cohort sizes, and how to regenerate.

The `.db` files themselves should **NOT** be committed to git (too large). Scripts and manifest **should** be committed.

---

## 2. Prerequisites — verify these are installed (10 minutes)

Run quick verification commands. Install anything missing.

| Tool | Version target | Verify command | Install if missing |
|---|---|---|---|
| Python | 3.11+ | `python --version` | https://www.python.org/downloads/ |
| `uv` (Python package manager) | latest | `uv --version` | `pip install uv` or https://github.com/astral-sh/uv |
| `gh` CLI | any | `gh auth status` | Already verified — authenticated as `Airwhale` |
| AWS CLI (optional, for direct S3) | any | `aws --version` | Skip if not present — we'll use HTTPS download instead |
| `sqlite3` CLI | 3.x | `sqlite3 --version` | Comes with Python; standalone optional |

**You do NOT need:** Java, R, Docker, Synthea, OHDSI/ETL-Synthea. The approach below uses pre-built Synthea-OMOP data from AWS Open Data, which is simpler and faster than running Synthea + ETL ourselves.

---

## 3. Project setup — Python environment (10 minutes)

If `pyproject.toml` doesn't exist yet at the repo root, create one. From the repo root:

```bash
cd "C:/Users/scgee/OneDrive/Documents/Projects/federated_silo_agent"
uv init --python 3.11        # if pyproject.toml doesn't exist
uv add pandas numpy duckdb sqlite-utils requests tqdm pyarrow
uv add --dev pytest
```

Verify imports work:

```bash
uv run python -c "import pandas, numpy, duckdb, sqlite_utils, requests; print('ok')"
```

Why these packages:
- `pandas` + `numpy` — table manipulation
- `duckdb` — fast columnar SQL over the CSV/Parquet downloads (much faster than loading 100K-row CSVs through pandas)
- `sqlite-utils` — convenient for building the SQLite OMOP databases
- `requests` + `tqdm` — downloading from S3 / public URLs with progress
- `pyarrow` — Parquet support if the AWS dataset uses it

Commit `pyproject.toml` and `uv.lock`:

```bash
git add pyproject.toml uv.lock
git -c "user.email=noreply@anthropic.com" -c "user.name=federated_silo_agent" commit -m "Add Python project scaffolding (uv) with data-layer dependencies

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

---

## 4. Download the Synthea-OMOP dataset (30–60 minutes wall-clock, mostly I/O)

The AWS Open Data registry hosts pre-built Synthea-OMOP datasets at three sizes. We'll use the **100K-patient dataset**, which we'll sub-sample down to ~26K across our three silos.

**Reference:** https://registry.opendata.aws/synthea-omop/

The dataset is in S3 at the bucket noted on the registry page. Files are CSVs (one per OMOP CDM table) following the OMOP CDM v5.4 schema.

**Your task:**

Create `backend/data/download_synthea_omop.py` that:

1. Downloads the 100K-patient Synthea-OMOP dataset from the AWS S3 bucket (use HTTPS public URLs — no AWS credentials needed).
2. Stores the raw CSVs under `data/raw/synthea_omop_100k/` (this directory should be `.gitignore`'d).
3. Verifies each expected OMOP table file is present and non-empty.
4. Prints a summary: rows per table, total disk usage.

**Expected OMOP CDM tables (per v5.4):**

- `person.csv`
- `observation_period.csv`
- `visit_occurrence.csv`
- `visit_detail.csv` (may be empty)
- `condition_occurrence.csv`
- `drug_exposure.csv`
- `procedure_occurrence.csv`
- `measurement.csv`
- `observation.csv`
- `death.csv`
- `care_site.csv`
- `location.csv`
- `provider.csv`
- `concept.csv` (vocabulary — large)
- `concept_relationship.csv` (vocabulary — large)
- `concept_ancestor.csv` (vocabulary)
- `vocabulary.csv`
- `domain.csv`
- `concept_class.csv`
- `relationship.csv`
- `drug_strength.csv`

**Failure mode:** if S3 URLs have changed or the dataset has moved, fall back to **Eunomia** (https://github.com/OHDSI/Eunomia). Eunomia bundles a smaller Synthea-OMOP dataset (~2,500 patients) as a downloadable ZIP. It's smaller than ideal but functional — note this in `data/silos/README.md` if you take the fallback path.

Add `data/raw/` to `.gitignore`:

```bash
echo "data/raw/" >> .gitignore
echo "data/silos/*.db" >> .gitignore
echo "data/silos/*.db-journal" >> .gitignore
git add .gitignore
git commit -m "Ignore raw data downloads and per-silo SQLite DBs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

Verify the download succeeded:

```bash
uv run python backend/data/download_synthea_omop.py
```

Acceptance: `person.csv` shows ~100,000 rows. Total raw download under 5 GB.

---

## 5. Split into three hospital silos (1 hour)

Create `backend/data/split_silos.py` that:

1. Reads the raw 100K-patient OMOP CDM CSVs.
2. **Deterministically assigns each `person_id` to one of three silos** using a fixed seed (`numpy.random.default_rng(seed=20260512)`).
3. Allocates patients with these target counts and demographic biases:

| Silo | Target patients | Bias (post-allocation filter) |
|---|---|---|
| `riverside` | ~12,000 | tilt toward older mean age (academic medical center, complex case mix) |
| `lakeside` | ~8,000 | mixed (regional hospital, balanced) |
| `summit` | ~6,000 | tilt toward younger mean age (community hospital, lower acuity) |

To create the age tilt without breaking randomness: after random assignment, optionally swap a small fraction of younger/older patients between silos to nudge the means apart. Document the swap procedure in your script so it's reproducible.

4. For each silo, builds a SQLite database at `data/silos/{silo_id}.db` containing **only** the rows of OMOP tables that pertain to that silo's patients. Specifically:
   - `person`, `observation_period`, `visit_occurrence`, `condition_occurrence`, `drug_exposure`, `procedure_occurrence`, `measurement`, `observation`, `death` — filtered to that silo's `person_id`s.
   - Vocabulary tables (`concept`, `concept_relationship`, `concept_ancestor`, `vocabulary`, `domain`, `concept_class`, `relationship`, `drug_strength`) — **copied in full to every silo** (these are reference data, not patient-specific).
5. Adds appropriate indexes on `person_id`, `concept_id`, and date columns for query speed.
6. Prints per-silo summary: patient count, encounter count, condition-occurrence count, CHF cohort count.

**Implementation hint:** load CSVs via `duckdb.read_csv` rather than `pandas.read_csv` — much faster for these volumes. Then `INSERT INTO sqlite_db SELECT * FROM duckdb_table WHERE person_id IN (...)`.

Run it:

```bash
uv run python backend/data/split_silos.py
```

Acceptance: three `.db` files exist under `data/silos/`. Each is queryable via `sqlite3` and has the expected row counts.

---

## 6. Feature engineering — derive the CHF cohort (1 hour)

Create `backend/data/feature_engineering.py` that, for each silo:

1. Identifies the **CHF cohort** — patients with at least one `condition_occurrence` row matching:
   - SNOMED concept_id mapped to `84114007` (Heart failure) or any descendant
   - OR ICD-10-CM source codes matching `I50%` (use `concept` table to find the OMOP concept_ids; or use a direct concept_id lookup if simpler)
2. For each CHF patient, computes a single "index encounter" (the first CHF-related inpatient `visit_occurrence`, or if none, the first CHF condition_occurrence).
3. Derives features per CHF patient:
   - `age_at_index` — integer years
   - `sex` — from `person.gender_concept_id` (M / F / Unknown)
   - `race` — from `person.race_concept_id` (categorical, OMOP-standard)
   - `index_bmi` — most recent BMI `measurement` within 90 days of index (LOINC `39156-5` or similar; if multiple measurements per LOINC over time, take the closest to index date)
   - `index_ef` — most recent ejection-fraction `measurement` within 180 days of index (LOINC `10230-1` Left ventricular ejection fraction by Echo, or `8806-2` LVEF by US 2D, or `18043-0` LVEF by Cardiac MRI). Range typically 5–80%.
   - `prior_chf_admissions_12mo` — count of CHF-coded inpatient visits in the 12 months *before* index
   - `has_diabetes` — any condition_occurrence matching ICD-10 `E10%` or `E11%` (or SNOMED concept_ids for diabetes mellitus)
   - `has_ckd` — any condition_occurrence matching ICD-10 `N18%` (chronic kidney disease)
   - `gdmt_adherence` — binary: at least one `drug_exposure` of (ACE inhibitor OR ARB) AND (beta-blocker) AND (diuretic) on or before the discharge of the index encounter. Use RxNorm ingredient concept_ids; if you need a starter list:
     - ACE/ARB: lisinopril (1308216), enalapril (1308842), losartan (1367500), valsartan (1308257)
     - Beta-blockers: carvedilol (1346823), metoprolol (1307046), bisoprolol (1346823)
     - Diuretics: furosemide (956874), spironolactone (970250)
     - (Use OMOP concept_ancestor table to find descendants if needed.)
   - `readmit_30d` — binary: any inpatient `visit_occurrence` starting within 30 days *after* index encounter's discharge
   - `los_index` — `visit_end_date − visit_start_date` for the index encounter, in days

4. Writes the result to a `chf_cohort_features` table inside each silo's SQLite database (NOT a separate file — same `.db` so it's available alongside the OMOP tables).

Run it:

```bash
uv run python backend/data/feature_engineering.py
```

Acceptance: each silo's `chf_cohort_features` table has rows. Print the counts:

```sql
SELECT 'riverside' AS silo, COUNT(*) AS chf_patients FROM riverside.chf_cohort_features
UNION ALL
SELECT 'lakeside', COUNT(*) FROM lakeside.chf_cohort_features
UNION ALL
SELECT 'summit', COUNT(*) FROM summit.chf_cohort_features;
```

Sanity ranges: each silo should have 300–800 CHF patients given Synthea's prevalence (it'll vary). If any silo has under 100, something's wrong — investigate the cohort definition.

---

## 7. Apply the four planted scenarios (2 hours)

Create `backend/data/apply_scenarios.py`. The plan's Section 9.4 specifies four scenarios. Each is implemented as a targeted modification of the OMOP tables and/or `chf_cohort_features` table. Use the same fixed seed so the modifications are deterministic.

### Scenario 1: GDMT effect on readmission

**Effect to bake in:** patients with `gdmt_adherence = 1` have ~30% lower 30-day readmission rate than non-adherent patients, all else equal.

**Implementation:**

For each silo, compute the current readmission rate among GDMT-adherent vs non-adherent CHF patients. Adjust the `readmit_30d` flag (and, if you can, the underlying `visit_occurrence` rows that drive it) so that the GDMT-adherent group's readmission rate is ~30% lower than non-adherent's, with appropriate randomness so the effect isn't dead-flat.

A simple, defensible approach: for each adherent CHF patient currently flagged `readmit_30d = 1`, flip to `0` with probability 0.30. Document this in the script as "we flip 30% of post-event readmissions among adherent patients to bake in the protective effect."

### Scenario 2: Diabetic + CKD heterogeneity

**Effect to bake in:** CHF patients with both `has_diabetes = 1` AND `has_ckd = 1` have *non-linearly* higher readmission than the additive expectation. That is: the interaction term in a logistic regression `readmit ~ diabetes + ckd + diabetes:ckd` should have a positive, statistically-distinguishable coefficient (after we have enough silos to combine for power).

**Implementation:**

Among CHF + DM + CKD patients across all silos, ensure their readmission rate is meaningfully higher than what `(rate_dm × rate_ckd / rate_baseline)` would predict additively. Concretely: take CHF + DM + CKD patients currently flagged `readmit_30d = 0` and flip a fraction to `1` (e.g., 25%) to push the joint group's rate up.

**Important:** make sure no single silo has so few CHF + DM + CKD cases (n<10) that the effect is detectable within that silo alone. The point is that the *federated* combined cohort has enough power.

### Scenario 3: Hospital-level LOS variation

**Effect to bake in:** Riverside has ~1.3-day longer median index length-of-stay than Lakeside and Summit, for matched acuity (matched comorbidity profile and age).

**Implementation:**

Update the `los_index` column (and, optionally, the underlying `visit_occurrence.visit_end_date`) in Riverside's database to add ~1.3 days to each CHF patient's index LOS. Add some noise (e.g., +1.3 ± 0.5 days uniformly distributed) so it's not a flat offset.

### Scenario 4: Rare-comorbidity statistical power unlock

**Effect to bake in:** ~30 cases of a rare CHF comorbidity (placeholder for amyloid cardiomyopathy) spread across the three silos — 10–15 per silo. Each silo alone has too few cases for confident inference; pooled across silos, a federated regression has tight enough CIs to make a statement.

**Implementation:**

Pick a clinically plausible-sounding SNOMED concept for "amyloid cardiomyopathy" or similar rare CHF subtype (or invent a placeholder concept_id for the demo; document it). Insert ~10–15 `condition_occurrence` rows in each silo, attached to randomly selected CHF patients. Then in `chf_cohort_features`, add a `has_amyloid` binary column.

Tune so that `has_amyloid = 1` is associated with a meaningfully elevated readmission rate (e.g., 1.8x the baseline). The effect should be detectable only when all three silos contribute.

### Outputs from the script

Print a summary table at the end:

```
Scenario                      | Expected effect | Riverside | Lakeside | Summit | Pooled
GDMT effect on readmit        | ~30% reduction  |   X%      |    Y%    |  Z%    |  W%
DM+CKD heterogeneity          | OR > additive   |   ...     |    ...   |  ...   |  ...
Hospital LOS variation        | Riverside +1.3d |   X.X d   |    Y.Y d |  Z.Z d |  -
Rare-comorbidity (amyloid)    | OR ~1.8 in pool |   ...     |    ...   |  ...   |  ...
```

This summary IS the validation for scenario application. If any line looks wrong, fix it before moving on.

Run it:

```bash
uv run python backend/data/apply_scenarios.py
```

---

## 8. Validation — sanity-check the cohort (30 minutes)

Create `backend/data/validate.py` that runs a battery of checks and prints PASS/FAIL for each. Use `pytest`-style assertions internally but make it executable as a script.

Checks to include:

1. **All three databases exist and are queryable.**
2. **Each silo has the expected patient count** within ±10% of target (12K / 8K / 6K).
3. **CHF cohort sizes are plausible** (>200 per silo).
4. **`chf_cohort_features` table has all expected columns** with non-trivial cardinality (e.g., `gdmt_adherence` not all 0 or all 1; `readmit_30d` proportions in a sensible 5–30% range).
5. **Scenarios are recoverable centrally** (running queries against the unioned cohort):
   - GDMT-adherent readmission rate < non-adherent (by a meaningful margin)
   - CHF+DM+CKD readmission rate > (DM-only rate × CKD-only rate / baseline) — i.e., supra-additive
   - Median Riverside LOS > Median Lakeside LOS by ~1 day
   - Pooled `has_amyloid` count is ~30; pooled odds ratio for readmission > 1.5
6. **Indexes are present on `person_id` and key date columns** in each silo.

Run it:

```bash
uv run python backend/data/validate.py
```

Acceptance: all checks PASS. If any FAIL, debug the corresponding scenario script. **Do not proceed to commit without all checks passing.**

---

## 9. Produce the data/silos/README.md manifest (15 minutes)

Write `data/silos/README.md` with:

- Brief description (one paragraph) of what's in `data/silos/` — three SQLite databases, one per silo, OMOP CDM v5.4, plus a derived `chf_cohort_features` table per silo.
- Random seed used.
- Date of last regeneration.
- Per-silo summary statistics: patient count, encounter count, CHF cohort count, GDMT adherence rate, baseline readmission rate.
- Regeneration instructions: the sequence of `uv run python backend/data/*.py` commands that rebuilds everything from scratch.
- The four planted scenarios with their expected effect sizes (cribbed from your validation output).
- A note: "Database files (`*.db`) are gitignored; only the scripts that produce them are versioned."

---

## 10. Commit and push (10 minutes)

Add everything *except* the actual data:

```bash
git add backend/data/*.py
git add data/silos/README.md
git add pyproject.toml uv.lock
git add .gitignore
# Make sure .db files are NOT staged:
git status        # confirm no *.db files appear
git -c "user.email=noreply@anthropic.com" -c "user.name=federated_silo_agent" commit -m "$(cat <<'EOF'
Add data-layer scripts for OMOP CDM synthetic hospital silos

- download_synthea_omop.py: pulls AWS Synthea-OMOP 100K dataset
- split_silos.py: assigns patients to riverside/lakeside/summit silos
  with target counts ~12K/8K/6K and demographic tilts (academic /
  regional / community)
- feature_engineering.py: derives CHF cohort + index features per silo
  (age_at_index, index_ef, prior_chf_admits_12mo, gdmt_adherence,
  has_diabetes, has_ckd, readmit_30d, los_index)
- apply_scenarios.py: applies the four planted demo scenarios
  (GDMT effect, DM+CKD heterogeneity, Riverside LOS bias,
  rare amyloid comorbidity)
- validate.py: PASS/FAIL battery confirming scenarios are recoverable

Output: three SQLite OMOP CDM v5.4 databases at data/silos/ (gitignored).
Schema follows OHDSI standards; system is plug-compatible with real
OMOP-formatted hospital data post-hackathon.

Reference: plan.md Section 9 (Synthetic Data Strategy), Section 11.2 P2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

Update the GitHub repo. Verify the push landed: `gh repo view Airwhale/federated_silo_agent --web` (will open in browser if available, otherwise just lists the latest commit).

---

## 11. Acceptance criteria (the agent's exit condition)

You're done when **all** of the following are true:

- [ ] Three SQLite databases exist under `data/silos/` (riverside.db, lakeside.db, summit.db)
- [ ] Each is queryable via `sqlite3` and has OMOP CDM v5.4 tables
- [ ] `chf_cohort_features` table populated per silo with all 10 features
- [ ] `validate.py` runs end-to-end and reports all checks PASS
- [ ] Five Python scripts under `backend/data/` are committed and pushed
- [ ] `data/silos/README.md` manifest is committed and pushed
- [ ] `pyproject.toml`, `uv.lock`, `.gitignore` are committed and pushed
- [ ] `.db` files are NOT in git history
- [ ] The four planted scenarios produce the expected effect sizes when queried centrally on the union of all three silos
- [ ] You can hand off to the next agent with a one-line summary like *"Three OMOP CDM silos at data/silos/; CHF cohort sizes [N1, N2, N3]; all four scenarios recoverable; ready for P0."*

---

## 12. Failure modes — what to do if things go sideways

**If the AWS Synthea-OMOP dataset URL has moved or is unavailable:**
Fall back to [Eunomia](https://github.com/OHDSI/Eunomia). Eunomia is an R package, but its underlying ZIP files (Synthea-OMOP-Sample, ~2,500 patients) are downloadable directly from `https://github.com/OHDSI/EunomiaDatasets/raw/main/datasets/SyntheticData/` (URL pattern may vary; check the EunomiaDatasets repo for the current location). Adjust the patient-count targets downward proportionally — e.g., 1,400 / 700 / 400 instead of 12K / 8K / 6K. Document the fallback in `data/silos/README.md`.

**If the 100K dataset is too large to download/process on this machine:**
Use the 1K dataset from the same AWS bucket and accept smaller cohort sizes.

**If CHF cohort sizes are too small:**
Use a broader CHF definition (include ICD-10 I11.0, I13.0 — hypertensive heart disease with heart failure) and document in the script. Sanity check that the broader cohort still represents "heart failure patients" clinically.

**If OMOP CSVs use different column names than the v5.4 spec:**
The Synthea-OMOP outputs sometimes lag the latest CDM spec. Stick with whatever schema the files use; just document it. Downstream code can adapt.

**If GDMT-adherence rates are all 0 (no patients have the drug combination):**
Synthea's drug-exposure modeling may not perfectly mirror real prescription patterns. Loosen the GDMT definition to "at least 2 of 3 drug classes" rather than all 3, or synthetically add some prescriptions during the scenario-application step. Document the relaxation.

**If you hit an issue not covered here:**
Document the issue, your decision, and the rationale in `data/silos/README.md`. Don't silently work around it. The next agent needs to know what you decided and why.

---

## 13. Time budget

| Step | Estimate |
|---|---|
| 0. Orient + read plan.md | 30 min |
| 1–2. Project setup + prerequisites | 30 min |
| 3. Python environment | 15 min |
| 4. Download Synthea-OMOP | 30–60 min (mostly wall-clock) |
| 5. Split into silos | 1 hour |
| 6. Feature engineering | 1 hour |
| 7. Apply planted scenarios | 2 hours |
| 8. Validation | 30 min |
| 9. Manifest | 15 min |
| 10. Commit + push | 10 min |
| **Total** | **~6–7 hours** |

If you're hitting 12+ hours, something's stuck — escalate by writing a clear status update in `data/silos/README.md` describing what's working, what's not, and what the next agent should try.

Good luck.
