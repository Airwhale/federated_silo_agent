"""Derive the CHF cohort features table for each silo.

For each silo's SQLite OMOP CDM database, this script:
  1. Identifies the CHF cohort (patients with heart failure concept_id)
  2. For each CHF patient, derives:
       age_at_index, sex, race
       index_bmi, index_ef, prior_chf_admissions_12mo
       has_diabetes, has_ckd
       gdmt_adherence
       has_amyloid (placeholder; populated by apply_scenarios.py)
       readmit_30d, los_index
  3. Writes the result to a `chf_cohort_features` table in the same DB

Run:
    uv run python data/scripts/feature_engineering.py
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vocab  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
SILOS_DIR = REPO_ROOT / "data" / "silos"

SEED = 20260512
SILO_IDS = ["riverside", "lakeside", "summit", "fairview", "coastal"]

# Comorbidity prevalence used when Synthea's source data is too sparse to
# populate has_diabetes / has_ckd from real condition_occurrence rows.
# Calibrated so the DM + CKD triple-positive cohort is large enough to
# support the planned interaction-term story in apply_scenarios.py.
SYNTH_DM_RATE = 0.55  # bumped from 0.35
SYNTH_CKD_RATE = 0.40  # bumped from 0.20
SYNTH_GDMT_RATE = 0.45
SYNTH_BASE_READMIT_RATE = 0.25


def silo_seed(silo_id: str, base_seed: int = SEED) -> int:
    """Deterministic per-silo seed derived from a stable hash.

    Python's built-in hash() randomizes string hashes per-process; use
    SHA-256 instead so the pipeline is bit-deterministic.
    """
    h = hashlib.sha256(silo_id.encode("utf-8")).hexdigest()
    return base_seed + int(h[:8], 16) % 1_000_000


def compute_features_for_silo(db_path: Path, rng: np.random.Generator) -> pd.DataFrame:
    """Compute the chf_cohort_features table for one silo."""
    con = sqlite3.connect(str(db_path))

    # CHF patients
    chf_ids = vocab.CHF_OMOP_CONCEPT_IDS
    chf_cids_csv = ",".join(str(x) for x in chf_ids)
    chf_pts = pd.read_sql(
        f"""
        SELECT DISTINCT co.person_id,
                        MIN(co.condition_start_date) AS chf_onset_date
        FROM condition_occurrence co
        WHERE co.condition_concept_id IN ({chf_cids_csv})
        GROUP BY co.person_id
        """,
        con,
    )
    if len(chf_pts) == 0:
        print(f"  WARN: no CHF patients in {db_path.name}")
        return pd.DataFrame()

    chf_pts["chf_onset_date"] = pd.to_datetime(chf_pts["chf_onset_date"])

    # Person demographics
    person = pd.read_sql(
        "SELECT person_id, gender_concept_id, race_concept_id, birth_datetime, year_of_birth FROM person",
        con,
    )
    person["birth_datetime"] = pd.to_datetime(person["birth_datetime"], errors="coerce")
    chf_pts = chf_pts.merge(person, on="person_id", how="left")

    # age_at_index — years between birth and chf_onset_date
    chf_pts["age_at_index"] = (
        (chf_pts["chf_onset_date"] - chf_pts["birth_datetime"]).dt.days // 365
    ).astype("Int64")

    # sex
    chf_pts["sex"] = chf_pts["gender_concept_id"].map(
        {8507: "M", 8532: "F"}  # OMOP standard gender concept_ids
    ).fillna("Unknown")

    # race (OMOP standard concept_ids — just store the ID; narrator/UI can map)
    chf_pts["race"] = chf_pts["race_concept_id"].astype("Int64")

    # ---- Measurements: BMI and ejection fraction near index ----
    # Convert value_as_number to numeric
    meas = pd.read_sql(
        "SELECT person_id, measurement_concept_id, measurement_date, value_as_number FROM measurement",
        con,
    )
    meas["value_as_number"] = pd.to_numeric(meas["value_as_number"], errors="coerce")
    meas["measurement_date"] = pd.to_datetime(meas["measurement_date"], errors="coerce")

    bmi_cid = vocab.MEASUREMENTS["body_mass_index"]["primary_omop_concept_id"]
    ef_cid = vocab.MEASUREMENTS["ejection_fraction"]["primary_omop_concept_id"]

    # index_bmi: most recent BMI within 90d of CHF onset
    def closest_value(person_id, target_date, concept_id, window_days):
        m = meas[(meas["person_id"] == person_id)
                 & (meas["measurement_concept_id"] == concept_id)
                 & meas["value_as_number"].notna()
                 & meas["measurement_date"].between(
                     target_date - pd.Timedelta(days=window_days), target_date
                   )]
        if len(m) == 0:
            return None
        m = m.sort_values("measurement_date", ascending=False)
        return float(m.iloc[0]["value_as_number"])

    chf_pts["index_bmi"] = [
        closest_value(p, d, bmi_cid, 365) for p, d in zip(chf_pts["person_id"], chf_pts["chf_onset_date"])
    ]
    chf_pts["index_ef"] = [
        closest_value(p, d, ef_cid, 365) for p, d in zip(chf_pts["person_id"], chf_pts["chf_onset_date"])
    ]

    # If no real EF observed, sample a plausible value (Synthea may not generate
    # echo measurements for our injected CHF patients). Sample from a clinically
    # realistic range so the regression has signal.
    missing_ef_mask = chf_pts["index_ef"].isna()
    chf_pts.loc[missing_ef_mask, "index_ef"] = rng.normal(loc=42, scale=12, size=missing_ef_mask.sum()).clip(15, 75)

    # Similarly fill missing BMI
    missing_bmi_mask = chf_pts["index_bmi"].isna()
    chf_pts.loc[missing_bmi_mask, "index_bmi"] = rng.normal(loc=28, scale=5, size=missing_bmi_mask.sum()).clip(16, 50)

    # ---- Prior CHF admissions in 12 months before index ----
    visits = pd.read_sql(
        "SELECT person_id, visit_start_date, visit_concept_id FROM visit_occurrence",
        con,
    )
    visits["visit_start_date"] = pd.to_datetime(visits["visit_start_date"], errors="coerce")
    # OMOP inpatient visit_concept_id is 9201
    inpt = visits[visits["visit_concept_id"].isin([9201, 9203])]  # inpatient + emergency

    def prior_admit_count(pid, idx_date):
        v = inpt[(inpt["person_id"] == pid)
                 & inpt["visit_start_date"].between(
                     idx_date - pd.Timedelta(days=365), idx_date - pd.Timedelta(days=1)
                   )]
        return len(v)

    chf_pts["prior_chf_admissions_12mo"] = [
        prior_admit_count(p, d) for p, d in zip(chf_pts["person_id"], chf_pts["chf_onset_date"])
    ]

    # ---- Comorbidities ----
    cond = pd.read_sql(
        "SELECT person_id, condition_concept_id, condition_start_date FROM condition_occurrence",
        con,
    )

    dm_cid = vocab.CONDITIONS["type2_diabetes"]["primary_omop_concept_id"]
    ckd_cid = vocab.CONDITIONS["chronic_kidney_disease"]["primary_omop_concept_id"]

    chf_pts["has_diabetes"] = chf_pts["person_id"].isin(
        cond[cond["condition_concept_id"] == dm_cid]["person_id"]
    ).astype(int)
    chf_pts["has_ckd"] = chf_pts["person_id"].isin(
        cond[cond["condition_concept_id"] == ckd_cid]["person_id"]
    ).astype(int)
    # If Synthea didn't generate any DM or CKD in our cardiac pool, sprinkle them
    # synthetically. Rates are tuned so the joint DM+CKD cohort has enough
    # members for the planned interaction-term scenario in apply_scenarios.py
    # (target: ~10 triple-positive per silo, ~50 pooled).
    if chf_pts["has_diabetes"].sum() == 0:
        chf_pts["has_diabetes"] = rng.binomial(1, SYNTH_DM_RATE, size=len(chf_pts))
    if chf_pts["has_ckd"].sum() == 0:
        chf_pts["has_ckd"] = rng.binomial(1, SYNTH_CKD_RATE, size=len(chf_pts))

    # ---- GDMT adherence ----
    # Check drug_exposure for any of ACE/ARB/beta-blocker/diuretic
    drugs = pd.read_sql(
        "SELECT person_id, drug_concept_id FROM drug_exposure",
        con,
    )
    ace_arb_ids = (
        vocab.DRUG_INGREDIENTS["ace_inhibitors"]["omop_concept_ids"]
        + vocab.DRUG_INGREDIENTS["arbs"]["omop_concept_ids"]
    )
    bb_ids = vocab.DRUG_INGREDIENTS["beta_blockers"]["omop_concept_ids"]
    di_ids = vocab.DRUG_INGREDIENTS["loop_diuretics"]["omop_concept_ids"]

    has_ace = drugs[drugs["drug_concept_id"].isin(ace_arb_ids)]["person_id"].unique()
    has_bb = drugs[drugs["drug_concept_id"].isin(bb_ids)]["person_id"].unique()
    has_di = drugs[drugs["drug_concept_id"].isin(di_ids)]["person_id"].unique()

    chf_pts["gdmt_adherence"] = (
        chf_pts["person_id"].isin(has_ace)
        & chf_pts["person_id"].isin(has_bb)
        & chf_pts["person_id"].isin(has_di)
    ).astype(int)
    # If GDMT adherence rate is unrealistically low (because we don't have all the
    # ingredient concept_ids mapped), simulate it. Target: ~45% adherence baseline.
    if chf_pts["gdmt_adherence"].mean() < 0.05:
        chf_pts["gdmt_adherence"] = rng.binomial(1, 0.45, size=len(chf_pts))

    # ---- Placeholder for amyloid (populated by apply_scenarios.py) ----
    chf_pts["has_amyloid"] = 0

    # ---- LOS for index encounter ----
    # Approximate: find inpatient visit closest to chf_onset_date
    def index_los(pid, idx_date):
        v = inpt[(inpt["person_id"] == pid)]
        if len(v) == 0:
            return None
        v = v.assign(diff=(v["visit_start_date"] - idx_date).abs())
        v = v.sort_values("diff")
        nearest = v.iloc[0]
        end = pd.to_datetime(visits.loc[
            (visits["person_id"] == pid)
            & (visits["visit_start_date"] == nearest["visit_start_date"]),
            "visit_start_date"
        ].iloc[0]) + pd.Timedelta(days=int(rng.integers(2, 9)))  # synth LOS 2-8 days
        return (end - nearest["visit_start_date"]).days

    chf_pts["los_index"] = [
        index_los(p, d) for p, d in zip(chf_pts["person_id"], chf_pts["chf_onset_date"])
    ]
    # Fill NULL LOS with synthesized values
    missing_los = chf_pts["los_index"].isna()
    chf_pts.loc[missing_los, "los_index"] = rng.integers(3, 10, size=missing_los.sum())

    # ---- 30-day readmission ----
    def readmit(pid, idx_date, los):
        if pd.isna(los):
            return 0
        disch_date = idx_date + pd.Timedelta(days=int(los))
        v = inpt[(inpt["person_id"] == pid)
                 & inpt["visit_start_date"].between(
                     disch_date + pd.Timedelta(days=1), disch_date + pd.Timedelta(days=30)
                   )]
        return int(len(v) > 0)

    chf_pts["readmit_30d"] = [
        readmit(p, d, los)
        for p, d, los in zip(chf_pts["person_id"], chf_pts["chf_onset_date"], chf_pts["los_index"])
    ]
    # If Synthea didn't generate any 30-day readmissions for our synthetic CHF cohort,
    # synthesize a baseline 25% readmission rate.
    if chf_pts["readmit_30d"].sum() == 0:
        chf_pts["readmit_30d"] = rng.binomial(1, 0.25, size=len(chf_pts))

    # Final column order
    out_cols = [
        "person_id", "chf_onset_date", "age_at_index", "sex", "race",
        "index_bmi", "index_ef", "prior_chf_admissions_12mo",
        "has_diabetes", "has_ckd", "gdmt_adherence", "has_amyloid",
        "readmit_30d", "los_index",
    ]
    out = chf_pts[out_cols].copy()
    out["chf_onset_date"] = out["chf_onset_date"].dt.date.astype(str)
    out["los_index"] = pd.to_numeric(out["los_index"], errors="coerce").astype("Int64")

    # Write to DB
    out.to_sql("chf_cohort_features", con, if_exists="replace", index=False)
    cur = con.cursor()
    cur.execute("CREATE INDEX idx_chfcf_person ON chf_cohort_features(person_id)")
    con.commit()
    con.close()
    return out


def main() -> None:
    print("Deriving chf_cohort_features per silo...\n")
    t0 = time.time()
    summary = []
    for silo_id in SILO_IDS:
        db = SILOS_DIR / f"{silo_id}.db"
        print(f"=== {silo_id} ===")
        silo_rng = np.random.default_rng(silo_seed(silo_id))
        df = compute_features_for_silo(db, silo_rng)
        if len(df):
            summary.append({
                "silo": silo_id,
                "n_chf": len(df),
                "mean_age": df["age_at_index"].mean(),
                "mean_bmi": df["index_bmi"].mean(),
                "mean_ef": df["index_ef"].mean(),
                "pct_diabetes": df["has_diabetes"].mean() * 100,
                "pct_ckd": df["has_ckd"].mean() * 100,
                "pct_gdmt": df["gdmt_adherence"].mean() * 100,
                "pct_readmit": df["readmit_30d"].mean() * 100,
                "mean_los": df["los_index"].astype(float).mean(),
            })
            print(f"  n_chf={len(df)}  readmit_rate={df['readmit_30d'].mean()*100:.1f}%  "
                  f"gdmt={df['gdmt_adherence'].mean()*100:.1f}%")
    print()
    print(f"Done in {time.time()-t0:.1f}s")
    print()
    sdf = pd.DataFrame(summary)
    print(sdf.to_string(index=False, float_format=lambda x: f"{x:.1f}"))


if __name__ == "__main__":
    main()
