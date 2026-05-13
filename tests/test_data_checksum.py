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
EXPECTED_FINGERPRINT_HASH = "3a87870c1d58a50a6f0df69bf95e6b92a9cfe38297cba2c849e9297a4a13b45e"


def _table_row_hash(df: pd.DataFrame, sort_cols: list[str]) -> str:
    """Hash the full row-level content of a DataFrame, sorted for determinism.

    Stronger than aggregate sums — catches drift in individual values
    (e.g., one transaction's amount changing) that an aggregate hash misses.
    """
    sorted_df = df.sort_values(sort_cols).reset_index(drop=True)
    # Canonicalize column order too, so a column-reordering doesn't churn the hash
    sorted_df = sorted_df.reindex(sorted(sorted_df.columns), axis=1)
    text = sorted_df.to_csv(index=False, header=True, na_rep="<NA>")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_fingerprint() -> dict:
    """Return a JSON-serializable dict capturing the AML dataset state.

    Version 3 — AML schema (post-pivot from clinical). Captures bank-level
    row-level hashes of customers + accounts + transactions +
    suspicious_signals + ground_truth_entities plus aggregate counts.
    """
    out: dict = {"version": 3, "silos": {}}
    pooled = {
        "n_customers": 0,
        "n_accounts": 0,
        "n_transactions": 0,
        "n_signals": 0,
        "n_shell_entities": 0,
        "n_pep": 0,
        "amount_sum_cents": 0,
    }
    for sid in SILO_IDS:
        db = SILOS_DIR / f"{sid}.db"
        con = sqlite3.connect(str(db))
        customers = pd.read_sql("SELECT * FROM customers", con)
        accounts = pd.read_sql("SELECT * FROM accounts", con)
        # Hash the columns that are demo-relevant for content drift.
        # Skip raw transaction-id strings since they're already part of the row.
        txns = pd.read_sql(
            "SELECT transaction_id, account_id, counterparty_account_id_hashed, "
            "amount, currency, transaction_type, timestamp, channel "
            "FROM transactions",
            con,
        )
        signals = pd.read_sql("SELECT * FROM suspicious_signals", con)
        gt = pd.read_sql("SELECT * FROM ground_truth_entities", con)
        con.close()

        amount_sum_cents = int(round(txns["amount"].sum() * 100))

        silo_stats = {
            "n_customers": int(len(customers)),
            "n_accounts": int(len(accounts)),
            "n_transactions": int(len(txns)),
            "n_signals": int(len(signals)),
            "n_shell_entities": int(len(gt)),
            "n_pep": int(gt["is_pep"].sum()) if len(gt) else 0,
            "amount_sum_cents": amount_sum_cents,
            # Row-level hashes (the strong fingerprints):
            "customers_rows_sha": _table_row_hash(customers, ["customer_id"]),
            "accounts_rows_sha": _table_row_hash(accounts, ["account_id"]),
            "transactions_rows_sha": _table_row_hash(
                txns, ["transaction_id"]
            ),
            "signals_rows_sha": _table_row_hash(signals, ["signal_id"]),
            "ground_truth_rows_sha": _table_row_hash(
                gt, ["entity_id", "customer_id"]
            ),
        }
        out["silos"][sid] = silo_stats

        pooled["n_customers"] += silo_stats["n_customers"]
        pooled["n_accounts"] += silo_stats["n_accounts"]
        pooled["n_transactions"] += silo_stats["n_transactions"]
        pooled["n_signals"] += silo_stats["n_signals"]
        pooled["n_shell_entities"] += silo_stats["n_shell_entities"]
        pooled["n_pep"] += silo_stats["n_pep"]
        pooled["amount_sum_cents"] += silo_stats["amount_sum_cents"]

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
        r'EXPECTED_FINGERPRINT_HASH = "3a87870c1d58a50a6f0df69bf95e6b92a9cfe38297cba2c849e9297a4a13b45e"',
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
