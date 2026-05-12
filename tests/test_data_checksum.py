"""Content-based fingerprint checksum of the five hospital silo datasets.

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

SILO_IDS = ["riverside", "lakeside", "summit", "fairview", "coastal"]

# ---------------------------------------------------------------------------
# The known-good fingerprint hash, captured against the canonical build.
# Update with ``python tests/test_data_checksum.py --update`` when you
# intentionally change the data pipeline.
# ---------------------------------------------------------------------------
EXPECTED_FINGERPRINT_HASH = "3c05659ceab543592803b7a647c9ce28835db70c38a30e8323b5bbe8a1b0063e"


def compute_fingerprint() -> dict:
    """Return a JSON-serializable dict capturing the state of the dataset."""
    out: dict = {"version": 1, "silos": {}}
    pooled = {
        "n_chf": 0,
        "readmit_sum": 0,
        "gdmt_sum": 0,
        "amyloid_sum": 0,
        "diabetes_sum": 0,
        "ckd_sum": 0,
        "los_sum": 0,
    }
    for sid in SILO_IDS:
        db = SILOS_DIR / f"{sid}.db"
        con = sqlite3.connect(str(db))
        df = pd.read_sql("SELECT * FROM chf_cohort_features", con).sort_values("person_id")
        con.close()

        los = pd.to_numeric(df["los_index"], errors="coerce").fillna(0).astype(int)

        # A small per-silo summary; the hash captures everything below.
        silo_stats = {
            "n_chf": int(len(df)),
            "person_ids_sha": hashlib.sha256(
                ",".join(str(p) for p in df["person_id"].tolist()).encode()
            ).hexdigest()[:16],
            "readmit_sum": int(df["readmit_30d"].sum()),
            "gdmt_sum": int(df["gdmt_adherence"].sum()),
            "amyloid_sum": int(df["has_amyloid"].sum()),
            "diabetes_sum": int(df["has_diabetes"].sum()),
            "ckd_sum": int(df["has_ckd"].sum()),
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
    if not _databases_present():
        pytest.skip(
            "data/silos/*.db not present. Build first with:\n"
            "    uv run python data/scripts/build_silos.py\n"
            "    uv run python data/scripts/feature_engineering.py\n"
            "    uv run python data/scripts/apply_scenarios.py"
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
