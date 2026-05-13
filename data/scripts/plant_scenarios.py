"""Plant four AML scenarios into the bank databases.

Run AFTER build_banks.py. This script adds shell entities and their
transaction patterns to the existing bank SQLite databases. Each shell
entity has a stable `name_hash` shared across all banks where it holds
accounts — that's the cross-bank identity linkage the federation uses
to detect the rings.

Scenarios:

  S1 — Headline structuring ring (5 entities, spans all 3 banks)
       Each entity has accounts at exactly 2 of the 3 banks.
       ~200 sub-CTR transfers form a closed cycle through all 3 banks.
       Contains the PEP entity (S4).

  S2 — Smaller structuring ring (3 entities, spans Alpha + Beta only)
       ~60 sub-CTR transfers. Demonstrates federation handles partial-
       overlap cases (no Gamma involvement).

  S3 — Layering chain (4 entities, Alpha -> Beta -> Gamma -> Alpha)
       ~30 transfers in a sequential chain that closes into a loop.
       Different typology from structuring; shows federation breadth.

  S4 — PEP entity inside S1
       One of the S1 ring entities has a synthetic Politically Exposed
       Person relation. Triggers F3 sanctions agent during S1 demo.

Ground truth is stored in a separate `ground_truth_entities` table per
bank — used only by validate_banks.py to confirm detection. The
federation engine does NOT see this table; it's labels for testing.

Run from repo root:
    uv run python data/scripts/build_banks.py     # if not already built
    uv run python data/scripts/plant_scenarios.py
"""

from __future__ import annotations

import hashlib
import random
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SILOS_DIR = REPO_ROOT / "data" / "silos"
SEED = 20260512

BANK_IDS = ("bank_alpha", "bank_beta", "bank_gamma")
WINDOW_START = np.datetime64("2025-04-01")
WINDOW_END = np.datetime64("2026-04-01")


def stable_name_hash(entity_id: str) -> str:
    """Cross-bank identity linkage hash. Same input -> same hash everywhere.

    This is the mechanism by which the federation detects "the same entity
    has accounts at multiple banks." Real-world AML uses similar identity
    tokens (hashes of SSN, name+DOB, etc.).
    """
    return hashlib.sha256(f"shell_entity|{entity_id}".encode()).hexdigest()[:16]


def hash_counterparty(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

@dataclass
class ShellEntity:
    entity_id: str
    name_hash: str  # cross-bank identity token (computed)
    cover_business: str
    banks: tuple[str, ...]
    is_pep: bool = False
    scenario: str = ""  # "S1" / "S2" / "S3"
    role: str = ""      # "node" / "source" / "sink"
    account_ids_by_bank: dict[str, str] = field(default_factory=dict)


def make_shell_entities() -> list[ShellEntity]:
    """Define all shell entities across all scenarios."""
    entities = []

    # ---- S1: Headline structuring ring (5 entities, all 3 banks) ----
    # Each entity holds accounts at exactly 2 of the 3 banks, arranged
    # so the ring as a whole spans all 3. One entity is the PEP.
    s1_specs = [
        ("S1-A", "Acme Holdings LLC",       ("bank_alpha", "bank_beta"),  False),
        ("S1-B", "Beacon Logistics Inc",    ("bank_beta",  "bank_gamma"), False),
        ("S1-C", "Citadel Trading Co",      ("bank_gamma", "bank_alpha"), False),
        ("S1-D", "Delta Imports Ltd",       ("bank_alpha", "bank_beta"),  True),   # PEP
        ("S1-E", "Eagle Consulting Group",  ("bank_beta",  "bank_gamma"), False),
    ]
    for eid, cover, banks, is_pep in s1_specs:
        entities.append(ShellEntity(
            entity_id=eid,
            name_hash=stable_name_hash(eid),
            cover_business=cover,
            banks=banks,
            is_pep=is_pep,
            scenario="S1",
            role="ring_node",
        ))

    # ---- S2: Smaller structuring ring (3 entities, Alpha + Beta only) ----
    s2_specs = [
        ("S2-A", "Foxtrot Wholesale",  ("bank_alpha", "bank_beta")),
        ("S2-B", "Gulf Stream Trading",("bank_alpha", "bank_beta")),
        ("S2-C", "Horizon Ventures",   ("bank_alpha", "bank_beta")),
    ]
    for eid, cover, banks in s2_specs:
        entities.append(ShellEntity(
            entity_id=eid,
            name_hash=stable_name_hash(eid),
            cover_business=cover,
            banks=banks,
            scenario="S2",
            role="ring_node",
        ))

    # ---- S3: Layering chain (4 entities, A->B->G->A) ----
    s3_specs = [
        ("S3-A", "Iridium Capital Partners", ("bank_alpha",),                 "chain_start"),
        ("S3-B", "Juniper Asset Mgmt",       ("bank_alpha", "bank_beta"),     "chain_relay"),
        ("S3-C", "Kestrel Holdings",         ("bank_beta",  "bank_gamma"),    "chain_relay"),
        ("S3-D", "Lattice Investments",      ("bank_gamma", "bank_alpha"),    "chain_end"),
    ]
    for eid, cover, banks, role in s3_specs:
        entities.append(ShellEntity(
            entity_id=eid,
            name_hash=stable_name_hash(eid),
            cover_business=cover,
            banks=banks,
            scenario="S3",
            role=role,
        ))

    return entities


# ---------------------------------------------------------------------------
# DB-level operations
# ---------------------------------------------------------------------------

GROUND_TRUTH_CREATE = """
CREATE TABLE IF NOT EXISTS ground_truth_entities (
    entity_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    name_hash TEXT NOT NULL,
    cover_business TEXT NOT NULL,
    scenario TEXT NOT NULL,
    role TEXT NOT NULL,
    is_pep INTEGER NOT NULL,
    PRIMARY KEY (entity_id, customer_id)
)
"""


def insert_shell_entities_into_bank(
    bank_id: str,
    entities: list[ShellEntity],
    rng: np.random.Generator,
) -> None:
    """Insert customer + account rows for each shell entity that has
    presence at this bank. Also populates ground_truth_entities."""
    db_path = SILOS_DIR / f"{bank_id}.db"
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute(GROUND_TRUTH_CREATE)

    # Count existing customers so the shell ones get unique IDs that
    # don't collide with the baseline ones.
    cur.execute("SELECT COUNT(*) FROM customers")
    base_count = cur.fetchone()[0]
    next_idx = base_count  # 0-padded continuation

    for entity in entities:
        if bank_id not in entity.banks:
            continue

        cust_id = f"{bank_id}_cust_{next_idx:06d}"
        acct_id = f"{bank_id}_acct_{next_idx:06d}_00"
        next_idx += 1

        # Same name_hash everywhere — this is the cross-bank linkage
        # key the federation will use.
        cur.execute(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?)",
            (
                cust_id,
                entity.name_hash,
                1980,  # arbitrary stable year for shell entities
                "small_business",
                "2024-01-01",  # all shells "opened" around the same time
            ),
        )
        cur.execute(
            "INSERT INTO accounts VALUES (?, ?, ?, ?, ?)",
            (acct_id, cust_id, "business_checking", "2024-01-01", "active"),
        )
        cur.execute(
            "INSERT INTO ground_truth_entities VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                entity.entity_id,
                cust_id,
                entity.name_hash,
                entity.cover_business,
                entity.scenario,
                entity.role,
                int(entity.is_pep),
            ),
        )

        entity.account_ids_by_bank[bank_id] = acct_id

    con.commit()
    con.close()


def insert_transactions(bank_id: str, transactions: list[dict]) -> None:
    """Append transactions and matching suspicious_signals to a bank's DB."""
    if not transactions:
        return
    db_path = SILOS_DIR / f"{bank_id}.db"
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()

    cur.executemany(
        "INSERT INTO transactions VALUES (:transaction_id, :account_id, "
        ":counterparty_account_id_hashed, :amount, :currency, :transaction_type, "
        ":timestamp, :channel)",
        transactions,
    )

    # Each shell-entity transaction in the $5K–$9.999K range generates a
    # within-bank "amount near CTR threshold" signal. These will look
    # like ordinary suspicion at each bank (~50–100 per entity) but
    # *the cross-bank pattern* is what makes them a ring rather than
    # independent small fish.
    cur.execute("SELECT MAX(signal_id) FROM suspicious_signals")
    row = cur.fetchone()
    max_existing = row[0] if row and row[0] else f"{bank_id}_sig_0000000"
    next_sig_idx = int(max_existing.split("_")[-1]) + 1

    signals = []
    for txn in transactions:
        if 9_000 <= txn["amount"] < 10_000:
            signals.append({
                "signal_id": f"{bank_id}_sig_{next_sig_idx:07d}",
                "transaction_id": txn["transaction_id"],
                "signal_type": "amount_near_ctr_threshold",
                "severity": 0.7,
                "computed_at": txn["timestamp"],
            })
            next_sig_idx += 1
        elif 5_000 <= txn["amount"] < 9_000:
            signals.append({
                "signal_id": f"{bank_id}_sig_{next_sig_idx:07d}",
                "transaction_id": txn["transaction_id"],
                "signal_type": "elevated_business_activity",
                "severity": 0.3,
                "computed_at": txn["timestamp"],
            })
            next_sig_idx += 1
    cur.executemany(
        "INSERT INTO suspicious_signals VALUES (:signal_id, :transaction_id, "
        ":signal_type, :severity, :computed_at)",
        signals,
    )

    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Scenario transaction generators
# ---------------------------------------------------------------------------

def random_timestamp_in_window(rng: np.random.Generator) -> str:
    days = rng.integers(0, 365)
    hours = rng.integers(0, 24)
    minutes = rng.integers(0, 60)
    ts = (
        np.datetime64(WINDOW_START, "h")
        + np.timedelta64(int(days * 24 + hours), "h")
        + np.timedelta64(int(minutes), "m")
    )
    return str(ts)


def sub_ctr_amount(rng: np.random.Generator) -> float:
    """Random amount in $5K–$9.999K, weighted toward the upper end
    (which is the classic structuring tell)."""
    # 70% in $8K–$9.999K (just below CTR), 30% in $5K–$8K (cover).
    if rng.random() < 0.7:
        amt = rng.uniform(8_000, 9_999)
    else:
        amt = rng.uniform(5_000, 8_000)
    return round(amt, 2)


def make_ring_transactions(
    entities: list[ShellEntity],
    n_transfers: int,
    txn_id_prefix: str,
    rng: np.random.Generator,
) -> dict[str, list[dict]]:
    """Generate cyclical transactions among the given ring entities.

    Each transfer is between two ring entities; the sender uses one of
    their accounts and the receiver's account is at one of THEIR banks
    (other than the sender's bank, when possible — that's the cross-
    bank structuring tell). Each transfer appears in BOTH banks: as an
    outgoing transaction at sender's bank and as an incoming
    transaction at receiver's bank.
    """
    txns_by_bank: dict[str, list[dict]] = {b: [] for b in BANK_IDS}
    bank_txn_counters = {b: 0 for b in BANK_IDS}
    n = len(entities)

    for _ in range(n_transfers):
        i = int(rng.integers(0, n))
        j = (i + int(rng.integers(1, n))) % n  # different entity
        sender = entities[i]
        receiver = entities[j]

        # Prefer cross-bank transfer (sender bank != receiver bank) so
        # the per-bank pattern looks legitimate but the cross-bank
        # cycle is the structuring tell.
        cross_options = [
            (sb, rb)
            for sb in sender.banks for rb in receiver.banks
            if sb != rb
        ]
        if cross_options:
            sb, rb = cross_options[int(rng.integers(0, len(cross_options)))]
        else:
            # Fallback: same bank (rare — only if sender/receiver overlap fully)
            sb = sender.banks[0]
            rb = receiver.banks[0]

        amount = sub_ctr_amount(rng)
        ts = random_timestamp_in_window(rng)
        channel = str(rng.choice(["wire", "electronic"], p=[0.40, 0.60]))

        sender_acct = sender.account_ids_by_bank[sb]
        receiver_acct = receiver.account_ids_by_bank[rb]

        # Outgoing at sender's bank
        out_id = f"{sb}_{txn_id_prefix}out_{bank_txn_counters[sb]:06d}"
        bank_txn_counters[sb] += 1
        txns_by_bank[sb].append({
            "transaction_id": out_id,
            "account_id": sender_acct,
            "counterparty_account_id_hashed": hash_counterparty(receiver_acct),
            "amount": amount,
            "currency": "USD",
            "transaction_type": "debit",
            "timestamp": ts,
            "channel": channel,
        })

        # Incoming at receiver's bank (slightly offset timestamp realistic)
        in_id = f"{rb}_{txn_id_prefix}in_{bank_txn_counters[rb]:06d}"
        bank_txn_counters[rb] += 1
        txns_by_bank[rb].append({
            "transaction_id": in_id,
            "account_id": receiver_acct,
            "counterparty_account_id_hashed": hash_counterparty(sender_acct),
            "amount": amount,
            "currency": "USD",
            "transaction_type": "credit",
            "timestamp": ts,
            "channel": channel,
        })

    return txns_by_bank


def make_layering_chain_transactions(
    chain: list[ShellEntity],
    txn_id_prefix: str,
    rng: np.random.Generator,
    initial_amount: float = 95_000.0,
    fee_pct_per_hop: float = 0.03,
    n_iterations: int = 8,
) -> dict[str, list[dict]]:
    """Generate sequential transfers along a chain E0 -> E1 -> ... -> E0.

    Each "iteration" of the layering pattern moves a sum through the
    chain, slightly attenuated by per-hop "fees" (which is how
    layerers obscure provenance and skim).
    """
    txns_by_bank: dict[str, list[dict]] = {b: [] for b in BANK_IDS}
    bank_txn_counters = {b: 0 for b in BANK_IDS}

    for iteration in range(n_iterations):
        amount = initial_amount
        base_day = int(rng.integers(0, 360))
        for hop_idx in range(len(chain)):
            sender = chain[hop_idx]
            receiver = chain[(hop_idx + 1) % len(chain)]
            # Each hop happens ~3–7 days after the prior hop
            day_offset = int(rng.integers(3, 8))
            base_day += day_offset
            hour = int(rng.integers(8, 18))
            ts = str(
                np.datetime64(WINDOW_START, "h")
                + np.timedelta64(base_day * 24 + hour, "h")
            )

            # Pick a sender bank where they have an account
            sb = sender.banks[int(rng.integers(0, len(sender.banks)))]
            # Receiver's bank: pick from receiver's accounts, prefer
            # different from sender's bank
            rb_options = [b for b in receiver.banks if b != sb]
            rb = (
                rb_options[int(rng.integers(0, len(rb_options)))]
                if rb_options
                else receiver.banks[0]
            )

            sender_acct = sender.account_ids_by_bank[sb]
            receiver_acct = receiver.account_ids_by_bank[rb]

            amount = round(amount * (1 - fee_pct_per_hop), 2)

            out_id = f"{sb}_{txn_id_prefix}out_{bank_txn_counters[sb]:06d}"
            bank_txn_counters[sb] += 1
            txns_by_bank[sb].append({
                "transaction_id": out_id,
                "account_id": sender_acct,
                "counterparty_account_id_hashed": hash_counterparty(receiver_acct),
                "amount": amount,
                "currency": "USD",
                "transaction_type": "debit",
                "timestamp": ts,
                "channel": "wire",
            })

            in_id = f"{rb}_{txn_id_prefix}in_{bank_txn_counters[rb]:06d}"
            bank_txn_counters[rb] += 1
            txns_by_bank[rb].append({
                "transaction_id": in_id,
                "account_id": receiver_acct,
                "counterparty_account_id_hashed": hash_counterparty(sender_acct),
                "amount": amount,
                "currency": "USD",
                "transaction_type": "credit",
                "timestamp": ts,
                "channel": "wire",
            })

    return txns_by_bank


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def main() -> None:
    if not all((SILOS_DIR / f"{b}.db").exists() for b in BANK_IDS):
        sys.exit(
            "Bank databases not found. Build them first:\n"
            "    uv run python data/scripts/build_banks.py"
        )

    rng = np.random.default_rng(SEED + 1)  # different from build_banks for clarity

    # Make all shell entities and insert their customer + account rows.
    entities = make_shell_entities()
    s1 = [e for e in entities if e.scenario == "S1"]
    s2 = [e for e in entities if e.scenario == "S2"]
    s3 = [e for e in entities if e.scenario == "S3"]

    print("=== Inserting shell entities ===")
    for bank_id in BANK_IDS:
        bank_rng = np.random.default_rng(
            SEED + 2 + int(hashlib.sha256(bank_id.encode()).hexdigest()[:8], 16) % 10000
        )
        insert_shell_entities_into_bank(bank_id, entities, bank_rng)
        n_at_bank = sum(1 for e in entities if bank_id in e.banks)
        print(f"  {bank_id}: {n_at_bank} shell entities inserted")

    # Now generate transactions for each scenario.
    print("\n=== Planting S1 (headline 5-entity structuring ring, all 3 banks) ===")
    s1_txns = make_ring_transactions(s1, n_transfers=100, txn_id_prefix="s1_", rng=rng)
    for bank_id, txns in s1_txns.items():
        insert_transactions(bank_id, txns)
        print(f"  {bank_id}: {len(txns)} S1 transactions")

    print("\n=== Planting S2 (smaller 3-entity ring, Alpha+Beta only) ===")
    s2_txns = make_ring_transactions(s2, n_transfers=40, txn_id_prefix="s2_", rng=rng)
    for bank_id, txns in s2_txns.items():
        insert_transactions(bank_id, txns)
        if txns:
            print(f"  {bank_id}: {len(txns)} S2 transactions")

    print("\n=== Planting S3 (4-entity layering chain Alpha->Beta->Gamma->Alpha) ===")
    s3_txns = make_layering_chain_transactions(
        s3, txn_id_prefix="s3_", rng=rng, n_iterations=8
    )
    for bank_id, txns in s3_txns.items():
        insert_transactions(bank_id, txns)
        if txns:
            print(f"  {bank_id}: {len(txns)} S3 transactions")

    # PEP entity is just a flag inside S1 (already set during entity creation
    # and recorded in ground_truth_entities table). Print a confirmation.
    pep_entities = [e for e in entities if e.is_pep]
    print(f"\n=== S4 PEP marker ===")
    for e in pep_entities:
        print(f"  {e.entity_id} ({e.cover_business}) flagged as PEP across {e.banks}")

    # Summary
    print("\n=== Final bank database state ===")
    for bank_id in BANK_IDS:
        db_path = SILOS_DIR / f"{bank_id}.db"
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM customers")
        n_cust = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM transactions")
        n_txns = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM suspicious_signals")
        n_sigs = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ground_truth_entities")
        n_shells = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ground_truth_entities WHERE is_pep = 1")
        n_peps = cur.fetchone()[0]
        size_mb = db_path.stat().st_size / 1024 / 1024
        print(f"  {bank_id}: {n_cust:,} customers ({n_shells} shells, {n_peps} PEP), "
              f"{n_txns:,} txns, {n_sigs:,} signals, {size_mb:.1f} MB")
        con.close()

    print("\nNext: uv run python data/scripts/validate_banks.py")


if __name__ == "__main__":
    main()
