"""Content-based fingerprint checksum of the bank silo datasets.

**Status (post-AML pivot):** the canonical hash here references the prior
clinical (Synthea-OMOP) build and will not match the new AML dataset.
The test now skips when the new bank SQLite databases are not yet
present at ``data/silos/``. Once the AML data pipeline (Day 1 build —
see plan.md Section 11) produces three bank SQLite databases, the
``compute_fingerprint`` body should be rewritten to fingerprint the
bank-specific tables (customers, accounts, transactions, suspicious_signals)
and the canonical hash regenerated with::

    uv run python tests/test_data_checksum.py --update

The clinical fingerprint shape (chf_cohort_features + condition_occurrence
+ person) is preserved in git history at commit 5bf0283.

What this test does
-------------------
Computes a deterministic, content-based fingerprint of the data state
across all five silos (cohort sizes, per-silo aggregate sums for each
key feature, the pooled scenario-effect summary) and compares the
SHA-256 of that fingerprint to a known-good value.

If the data pipeline produces bit-identical output given the fixed seed
(``20260512``), this test passes. If anything drifts, it fails with a
side-by-side diff so you can see exactly what changed.

When the test fails
-------------------
1. **You intentionally changed the data pipeline** (new scenario, new
   seed, different cohort definition). Run::

       uv run python tests/test_data_checksum.py --update

   to recompute and overwrite ``EXPECTED_FINGERPRINT_HASH`` below, then
   commit the update with the same PR.

2. **Regression** — the same scripts now produce different output
   despite identical inputs. Investigate before updating the hash.

3. **The data hasn't been built yet**. The test skips in that case;
   run the pipeline first (see ``data/README.md``).

Why content-based fingerprint rather than byte-level ``.db`` hashing
--------------------------------------------------------------------
SQLite's on-disk layout (page ordering, free-list reuse, index page
positions) varies with SQLite version, write order, and incidental
factors. A byte-level hash would generate spurious failures. The
content-based fingerprint hashes *what the data actually says*, not
*how SQLite stored it*.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SILOS_DIR = REPO_ROOT / "data" / "silos"

# Bank silo IDs for the AML build (Day 1 work). The clinical silo IDs
# (riverside, lakeside, summit, fairview, coastal) are preserved in git
# history at commit 5bf0283 along with the matching fingerprint hash.
SILO_IDS = ["bank_alpha", "bank_beta", "bank_gamma"]

# ---------------------------------------------------------------------------
# The known-good fingerprint hash, captured against the canonical build.
# Update with ``python tests/test_data_checksum.py --update`` when you
# intentionally change the data pipeline.
# ---------------------------------------------------------------------------
# Reset to None after the AML pivot. Will be regenerated once the bank
# SQLite databases exist and ``compute_fingerprint`` is rewritten for the
# AML schema. Until then the test skips.
EXPECTED_FINGERPRINT_HASH: str | None = None


def _table_row_hash(df: pd.DataFrame, sort_cols: list[str]) -> str:
    """Hash the full row-level content of a DataFrame, sorted for determinism.

    Stronger than aggregate sums — catches drift in individual feature
    values (e.g., wrong BMI for patient X) that an aggregate hash misses.
    """
    sorted_df = df.sort_values(sort_cols).reset_index(drop=True)
    # Canonicalize column order too, so a column-reordering doesn't churn the hash
    sorted_df = sorted_df.reindex(sorted(sorted_df.columns), axis=1)
    text = sorted_df.to_csv(index=False, header=True, na_rep="<NA>")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_fingerprint() -> dict:
    """Return a JSON-serializable dict capturing the state of the dataset.

    Version 2 adds row-level table hashes alongside the aggregate sums,
    so the fingerprint detects drift in individual feature values and
    condition_occurrence rows — not only changes in summary statistics.
    """
    out: dict = {"version": 2, "silos": {}}
    pooled = {
        "n_chf": 0,
        "readmit_sum": 0,
        "gdmt_sum": 0,
        "amyloid_sum": 0,
        "diabetes_sum": 0,
        "ckd_sum": 0,
        "los_sum": 0,
        "n_dm_ckd_triple_pos": 0,
    }
    for sid in SILO_IDS:
        db = SILOS_DIR / f"{sid}.db"
        con = sqlite3.connect(str(db))
        chf = pd.read_sql("SELECT * FROM chf_cohort_features", con)
        co = pd.read_sql(
            "SELECT condition_occurrence_id, person_id, condition_concept_id, "
            "condition_source_value, condition_start_date "
            "FROM condition_occurrence",
            con,
        )
        person = pd.read_sql("SELECT person_id, year_of_birth, gender_concept_id FROM person", con)
        con.close()

        los = pd.to_numeric(chf["los_index"], errors="coerce").fillna(0).astype(int)

        triple_pos = int(((chf["has_diabetes"] == 1) & (chf["has_ckd"] == 1)).sum())

        silo_stats = {
            "n_chf": int(len(chf)),
            "n_total_persons": int(len(person)),
            "n_condition_occurrence": int(len(co)),
            # Row-level hashes (the strong fingerprints):
            "chf_features_rows_sha": _table_row_hash(chf, ["person_id"]),
            "condition_occurrence_rows_sha": _table_row_hash(
                co, ["person_id", "condition_concept_id", "condition_start_date"]
            ),
            "person_demographics_sha": _table_row_hash(person, ["person_id"]),
            # Aggregate sums (kept for human inspection on failure):
            "readmit_sum": int(chf["readmit_30d"].sum()),
            "gdmt_sum": int(chf["gdmt_adherence"].sum()),
            "amyloid_sum": int(chf["has_amyloid"].sum()),
            "diabetes_sum": int(chf["has_diabetes"].sum()),
            "ckd_sum": int(chf["has_ckd"].sum()),
            "n_dm_ckd_triple_pos": triple_pos,
            "los_sum": int(los.sum()),
        }
        out["silos"][sid] = silo_stats

        pooled["n_chf"] += silo_stats["n_chf"]
        pooled["readmit_sum"] += silo_stats["readmit_sum"]
        pooled["gdmt_sum"] += silo_stats["gdmt_sum"]
        pooled["amyloid_sum"] += silo_stats["amyloid_sum"]
        pooled["diabetes_sum"] += silo_stats["diabetes_sum"]
        pooled["ckd_sum"] += silo_stats["ckd_sum"]
        pooled["los_sum"] += silo_stats["los_sum"]
        pooled["n_dm_ckd_triple_pos"] += triple_pos

    out["pooled"] = pooled
    return out


def fingerprint_hash(fp: dict) -> str:
    return hashlib.sha256(
        json.dumps(fp, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _databases_present() -> bool:
    return SILOS_DIR.exists() and all(
        (SILOS_DIR / f"{sid}.db").exists() for sid in SILO_IDS
    )


# ---------------------------------------------------------------------------
# The actual test
# ---------------------------------------------------------------------------

def test_data_checksum() -> None:
    """The dataset fingerprint matches the canonical expected value."""
    if EXPECTED_FINGERPRINT_HASH is None:
        pytest.skip(
            "EXPECTED_FINGERPRINT_HASH is None — the AML dataset is not yet "
            "built. Day 1 of the post-pivot build adds data/scripts/build_banks.py "
            "and data/scripts/plant_ring.py; once those exist and the SQLite "
            "databases are produced, regenerate the hash with:\n"
            "    uv run python tests/test_data_checksum.py --update"
        )

    if not _databases_present():
        pytest.skip(
            "data/silos/*.db not present. Build first with:\n"
            "    uv run python data/scripts/build_banks.py\n"
            "    uv run python data/scripts/plant_ring.py"
        )

    fp = compute_fingerprint()
    actual = fingerprint_hash(fp)

    if actual != EXPECTED_FINGERPRINT_HASH:
        pretty = json.dumps(fp, sort_keys=True, indent=2)
        msg = (
            "\n"
            "Data fingerprint changed.\n"
            f"  Expected hash: {EXPECTED_FINGERPRINT_HASH}\n"
            f"  Actual hash:   {actual}\n"
            "\n"
            "Actual content-based fingerprint:\n"
            f"{pretty}\n"
            "\n"
            "If this change was intentional (new seed, new scenario, etc.), "
            "regenerate the expected hash with:\n"
            "    uv run python tests/test_data_checksum.py --update\n"
            "and commit the updated value.\n"
        )
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# CLI for regenerating the expected hash
# ---------------------------------------------------------------------------

def _update_expected_hash() -> None:
    """Recompute the fingerprint hash and rewrite EXPECTED_FINGERPRINT_HASH."""
    if not _databases_present():
        sys.exit(
            "data/silos/*.db not present. Build first with:\n"
            "    uv run python data/scripts/build_silos.py\n"
            "    uv run python data/scripts/feature_engineering.py\n"
            "    uv run python data/scripts/apply_scenarios.py"
        )
    fp = compute_fingerprint()
    new_hash = fingerprint_hash(fp)
    print("Computed fingerprint:")
    print(json.dumps(fp, sort_keys=True, indent=2))
    print(f"\nNew hash: {new_hash}")

    # Rewrite this file
    me = Path(__file__).read_text(encoding="utf-8")
    updated = re.sub(
        r'EXPECTED_FINGERPRINT_HASH = ".*"',
        f'EXPECTED_FINGERPRINT_HASH = "{new_hash}"',
        me,
        count=1,
    )
    if updated == me:
        sys.exit("Failed to locate EXPECTED_FINGERPRINT_HASH in this file.")
    Path(__file__).write_text(updated, encoding="utf-8")
    print(f"\nUpdated EXPECTED_FINGERPRINT_HASH in {__file__}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="Recompute and overwrite the expected fingerprint hash in this file.",
    )
    args = parser.parse_args()
    if args.update:
        _update_expected_hash()
    else:
        # Run as a script: print the current fingerprint + hash and exit 0/1.
        fp = compute_fingerprint()
        h = fingerprint_hash(fp)
        print(json.dumps(fp, sort_keys=True, indent=2))
        print(f"\nFingerprint hash: {h}")
        if h == EXPECTED_FINGERPRINT_HASH:
            print("MATCH: data state matches the committed expected hash.")
        else:
            print(f"MISMATCH: expected {EXPECTED_FINGERPRINT_HASH}")
            sys.exit(1)
