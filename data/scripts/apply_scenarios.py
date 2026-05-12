"""Apply the four planted demo scenarios to chf_cohort_features.

See plan.md Section 9.6 for the design rationale.

  S1: GDMT effect on readmission        ~30% relative reduction
  S2: DM+CKD heterogeneity              supra-additive readmit risk
  S3: Hospital-level LOS variation       Riverside +1.3 days
  S4: Cardiac amyloidosis rare subtype  ~2 per silo (~10 pooled);
                                         elevated readmit risk

All modifications are deterministic (seeded). After this script,
validate.py confirms the effects are centrally recoverable.

Run:
    uv run python data/scripts/apply_scenarios.py
"""

from __future__ import annotations

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

# Calibrated effect sizes
GDMT_RR_REDUCTION = 0.30       # 30% relative reduction in readmit on adherent
DM_CKD_INDUCED_RATE = 0.40     # If triple-positive, push readmit_30d=1 to this rate
RIVERSIDE_LOS_BIAS_DAYS = 1.3  # Riverside LOS shift
AMYLOID_PER_SILO_TARGET = 2    # Per silo target count
AMYLOID_READMIT_BUMP = 0.30    # Extra probability that an amyloid pt is readmitted


def apply_to_silo(silo_id: str, rng: np.random.Generator) -> dict:
    """Apply all four scenarios to one silo's chf_cohort_features. Returns a stats dict."""
    db = SILOS_DIR / f"{silo_id}.db"
    con = sqlite3.connect(str(db))
    df = pd.read_sql("SELECT * FROM chf_cohort_features", con)

    before = {
        "n_chf": len(df),
        "readmit_rate_overall": df["readmit_30d"].mean(),
        "los_mean": pd.to_numeric(df["los_index"], errors="coerce").mean(),
    }

    # If baseline readmission is very low (because synth data is sparse), goose it
    # up to a plausible ~25% baseline first so the GDMT scenario has effect headroom.
    if df["readmit_30d"].mean() < 0.20:
        gap = 0.25 - df["readmit_30d"].mean()
        # Flip some readmit_30d=0 to 1 randomly
        zero_idx = df[df["readmit_30d"] == 0].index.tolist()
        n_to_flip = int(len(df) * gap)
        flip_idx = rng.choice(zero_idx, size=min(n_to_flip, len(zero_idx)), replace=False)
        df.loc[flip_idx, "readmit_30d"] = 1

    after_baseline = df["readmit_30d"].mean()

    # ---- Scenario 1: GDMT protective effect ----
    # Among GDMT-adherent patients currently readmit=1, flip ~30% to 0
    adherent_readmit = df[(df["gdmt_adherence"] == 1) & (df["readmit_30d"] == 1)].index.tolist()
    n_flip = int(round(len(adherent_readmit) * GDMT_RR_REDUCTION))
    if n_flip > 0:
        flip_idx = rng.choice(adherent_readmit, size=n_flip, replace=False)
        df.loc[flip_idx, "readmit_30d"] = 0
    s1_readmit_adherent = df[df["gdmt_adherence"] == 1]["readmit_30d"].mean()
    s1_readmit_nonadherent = df[df["gdmt_adherence"] == 0]["readmit_30d"].mean()

    # ---- Scenario 2: DM + CKD supra-additive ----
    # Among CHF + DM + CKD patients currently readmit=0, flip enough to reach 40% rate
    triple_pos = df[(df["has_diabetes"] == 1) & (df["has_ckd"] == 1)].index
    if len(triple_pos) > 0:
        current = df.loc[triple_pos, "readmit_30d"].mean()
        target = DM_CKD_INDUCED_RATE
        if current < target:
            zero_idx = df[(df.index.isin(triple_pos)) & (df["readmit_30d"] == 0)].index.tolist()
            n_flip = int(round(len(triple_pos) * (target - current)))
            n_flip = min(n_flip, len(zero_idx))
            if n_flip > 0:
                flip_idx = rng.choice(zero_idx, size=n_flip, replace=False)
                df.loc[flip_idx, "readmit_30d"] = 1
    s2_triple_pos_readmit = (
        df[(df["has_diabetes"] == 1) & (df["has_ckd"] == 1)]["readmit_30d"].mean()
        if len(triple_pos) > 0 else None
    )

    # ---- Scenario 3: Riverside LOS bias ----
    if silo_id == "riverside":
        los = pd.to_numeric(df["los_index"], errors="coerce")
        noise = rng.uniform(-0.5, 0.5, size=len(df))
        df["los_index"] = (los + RIVERSIDE_LOS_BIAS_DAYS + noise).round().astype("Int64")
    s3_los_mean = pd.to_numeric(df["los_index"], errors="coerce").mean()

    # ---- Scenario 4: Amyloid cardiomyopathy rare subtype ----
    chosen_pids = rng.choice(df["person_id"].tolist(), size=AMYLOID_PER_SILO_TARGET, replace=False)
    df.loc[df["person_id"].isin(chosen_pids), "has_amyloid"] = 1
    # Elevate readmit rate for amyloid patients
    am_idx = df[(df["has_amyloid"] == 1) & (df["readmit_30d"] == 0)].index.tolist()
    n_bump = int(round(len(chosen_pids) * AMYLOID_READMIT_BUMP * 2))  # *2 because we sample from zero-only
    if am_idx and n_bump > 0:
        flip = rng.choice(am_idx, size=min(n_bump, len(am_idx)), replace=False)
        df.loc[flip, "readmit_30d"] = 1

    # Also insert condition_occurrence rows for amyloid for the chosen patients
    co = pd.read_sql("SELECT * FROM condition_occurrence", con)
    new_id = co["condition_occurrence_id"].max() + 1
    new_rows = []
    for i, pid in enumerate(chosen_pids):
        new_rows.append({
            "condition_occurrence_id": new_id + i,
            "person_id": int(pid),
            "condition_concept_id": vocab.CONDITIONS["amyloid_cardiomyopathy"]["primary_omop_concept_id"],
            "condition_start_date": "2020-06-15",
            "condition_start_datetime": "2020-06-15",
            "condition_end_date": None,
            "condition_end_datetime": None,
            "condition_type_concept_id": 32020,
            "stop_reason": None,
            "provider_id": None,
            "visit_occurrence_id": None,
            "visit_detail_id": None,
            "condition_source_value": vocab.CONDITIONS["amyloid_cardiomyopathy"]["primary_snomed"],
            "condition_source_concept_id": vocab.CONDITIONS["amyloid_cardiomyopathy"]["primary_omop_concept_id"],
            "condition_status_source_value": None,
            "condition_status_concept_id": None,
        })
    new_df = pd.DataFrame(new_rows)
    for c in co.columns:
        if c not in new_df.columns:
            new_df[c] = None
    new_df = new_df[co.columns]
    co_updated = pd.concat([co, new_df], ignore_index=True)
    co_updated.to_sql("condition_occurrence", con, if_exists="replace", index=False)

    # Save the updated features back
    df.to_sql("chf_cohort_features", con, if_exists="replace", index=False)
    cur = con.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chfcf_person ON chf_cohort_features(person_id)")
    con.commit()
    con.close()

    return {
        "silo": silo_id,
        "n_chf": before["n_chf"],
        "readmit_baseline": after_baseline,
        "readmit_overall_final": df["readmit_30d"].mean(),
        "s1_gdmt_adherent_readmit": s1_readmit_adherent,
        "s1_gdmt_nonadherent_readmit": s1_readmit_nonadherent,
        "s2_triple_pos_n": (df["has_diabetes"] & df["has_ckd"]).sum(),
        "s2_triple_pos_readmit": s2_triple_pos_readmit,
        "s3_los_mean": s3_los_mean,
        "s4_amyloid_n": int(df["has_amyloid"].sum()),
        "s4_amyloid_readmit": df[df["has_amyloid"] == 1]["readmit_30d"].mean(),
    }


def main() -> None:
    print("Applying planted scenarios...\n")
    rng = np.random.default_rng(SEED)
    t0 = time.time()
    rows = []
    for silo_id in SILO_IDS:
        silo_rng = np.random.default_rng(SEED + hash(silo_id) % 10000)
        r = apply_to_silo(silo_id, silo_rng)
        rows.append(r)
        print(f"  {silo_id:<12} n_chf={r['n_chf']:>3}  "
              f"overall_readmit={r['readmit_overall_final']*100:>4.1f}%  "
              f"adh={r['s1_gdmt_adherent_readmit']*100:>4.1f}% / "
              f"non-adh={r['s1_gdmt_nonadherent_readmit']*100:>4.1f}%  "
              f"LOS_mean={r['s3_los_mean']:>3.1f}d  "
              f"amyloid={r['s4_amyloid_n']}")

    print(f"\nDone in {time.time()-t0:.1f}s")

    # Pooled summary
    df = pd.DataFrame(rows)
    print("\n=== Pooled summary (recoverability check) ===")
    total_chf = df["n_chf"].sum()
    pooled_adh_num = sum(
        r["s1_gdmt_adherent_readmit"] * (r["n_chf"] / 2) for r in rows  # rough
    )
    # Actually compute pooled by re-reading dbs
    pooled_data = []
    for silo_id in SILO_IDS:
        db = SILOS_DIR / f"{silo_id}.db"
        con = sqlite3.connect(str(db))
        pdf = pd.read_sql("SELECT * FROM chf_cohort_features", con)
        pdf["silo"] = silo_id
        pooled_data.append(pdf)
        con.close()
    pooled = pd.concat(pooled_data, ignore_index=True)
    print(f"  Total CHF patients pooled:        {len(pooled)}")
    print(f"  Overall readmit rate (pooled):    {pooled['readmit_30d'].mean()*100:.1f}%")
    print(f"  GDMT-adherent readmit (pooled):   {pooled[pooled['gdmt_adherence']==1]['readmit_30d'].mean()*100:.1f}%")
    print(f"  GDMT non-adherent readmit (pooled): {pooled[pooled['gdmt_adherence']==0]['readmit_30d'].mean()*100:.1f}%")
    triple = pooled[(pooled['has_diabetes']==1) & (pooled['has_ckd']==1)]
    print(f"  CHF+DM+CKD count (pooled):        {len(triple)}")
    print(f"  CHF+DM+CKD readmit rate (pooled): {triple['readmit_30d'].mean()*100:.1f}%")
    print(f"  Amyloid count (pooled):           {pooled['has_amyloid'].sum()}")
    print(f"  Amyloid readmit rate (pooled):    {pooled[pooled['has_amyloid']==1]['readmit_30d'].mean()*100:.1f}%")
    print(f"  Riverside LOS mean:               {pooled[pooled['silo']=='riverside']['los_index'].astype(float).mean():.2f}d")
    print(f"  Other silos LOS mean:             {pooled[pooled['silo']!='riverside']['los_index'].astype(float).mean():.2f}d")


if __name__ == "__main__":
    main()
