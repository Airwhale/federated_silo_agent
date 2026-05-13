"""Generate three synthetic bank databases for the AML federation demo.

Three banks with deliberately different profiles, calibrated to public sources:

  - Bank Alpha (national)        ~8,000 customers, ~80,000 transactions
  - Bank Beta  (regional community) ~5,000 customers, ~40,000 transactions
  - Bank Gamma (credit union)    ~3,000 customers, ~25,000 transactions

The data is fully synthetic. The script does NOT plant the structuring /
layering rings — that's plant_scenarios.py. This script produces the
baseline "legitimate" customer + transaction pool that the planted
scenarios are embedded into.

Calibration references (see comments at point of use):
  - FFIEC BSA/AML Examination Manual — $10K Currency Transaction Report
    threshold, $3K enhanced recordkeeping requirement, channel definitions
  - FinCEN SAR statistics — ~3M SARs/year industry-wide; structuring is
    ~20-25% of typology codes
  - Industry benchmarks — per-customer transaction frequency, channel
    distribution by bank type, KYC tier distributions

Output: three SQLite databases at data/silos/{bank_id}.db with tables:
    customers, accounts, transactions, suspicious_signals

Determinism: master seed 20260512; re-running produces bit-identical DBs.

Run from repo root:
    uv run python data/scripts/build_banks.py
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SILOS_DIR = REPO_ROOT / "data" / "silos"

SEED = 20260512
WINDOW_START = np.datetime64("2025-04-01")
WINDOW_END = np.datetime64("2026-04-01")
WINDOW_DAYS = int((WINDOW_END - WINDOW_START) / np.timedelta64(1, "D"))

# FFIEC BSA/AML Examination Manual: Currency Transaction Report threshold
# is $10,000 (transactions ABOVE $10K must be reported). Structuring is
# defined as deliberately splitting transactions to stay below.
CTR_THRESHOLD_USD = 10_000.0

# FFIEC BSA/AML Examination Manual: $3,000 threshold for enhanced
# recordkeeping on certain wire transfers.
ENHANCED_RECORDKEEPING_USD = 3_000.0


def silo_seed(silo_id: str, base_seed: int = SEED) -> int:
    """Deterministic per-silo seed via stable SHA-256 hash.

    Python's built-in hash() randomizes per-process; SHA-256 is stable.
    """
    h = hashlib.sha256(silo_id.encode("utf-8")).hexdigest()
    return base_seed + int(h[:8], 16) % 1_000_000


# ---------------------------------------------------------------------------
# Bank profiles — calibrated, intentionally different
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BankProfile:
    bank_id: str
    display_name: str
    bank_type: str
    n_customers: int
    txns_per_customer_per_year_mean: float
    # KYC tier mix (must sum to 1.0): retail, small_business, commercial
    kyc_tier_weights: tuple[float, float, float]
    # Channel mix (must sum to 1.0): wire, electronic, check, cash, debit
    channel_weights: tuple[float, float, float, float, float]
    # Per-bank alert sensitivity — multiplies a baseline rate; higher
    # means more false positives flagged. Production AML systems report
    # ~95% FP rates; this knob calibrates per-bank.
    alert_sensitivity: float


# Profiles deliberately diverge across the three banks. Distributions
# are loosely calibrated to industry norms — see "Calibration" comments
# below — and exaggerated mildly so the inter-bank differences are
# visible in summary statistics.
BANKS = (
    BankProfile(
        bank_id="bank_alpha",
        display_name="Bank Alpha (National)",
        bank_type="national",
        n_customers=8_000,
        txns_per_customer_per_year_mean=10.0,
        # National bank: more commercial customers, fewer retail-only.
        # Calibration: large US banks report ~10–15% commercial book by
        # account count; we set 10% to keep the demo at a manageable
        # scale.
        kyc_tier_weights=(0.60, 0.30, 0.10),
        # National banks lean wire-heavy because of commercial activity;
        # debit share is high from large retail customer base.
        channel_weights=(0.30, 0.45, 0.05, 0.03, 0.17),
        alert_sensitivity=0.6,  # sophisticated AML lowers their false-positive count
    ),
    BankProfile(
        bank_id="bank_beta",
        display_name="Bank Beta (Regional Community)",
        bank_type="regional_community",
        n_customers=5_000,
        txns_per_customer_per_year_mean=8.0,
        # Regional community bank: mostly retail + small business; few
        # commercial accounts.
        kyc_tier_weights=(0.65, 0.32, 0.03),
        # Community banks have heavier check / cash share due to local
        # small-business clientele.
        channel_weights=(0.18, 0.40, 0.18, 0.10, 0.14),
        alert_sensitivity=1.0,  # baseline alert sensitivity
    ),
    BankProfile(
        bank_id="bank_gamma",
        display_name="Bank Gamma (Credit Union)",
        bank_type="credit_union",
        n_customers=3_000,
        txns_per_customer_per_year_mean=8.5,
        # Credit unions are predominantly retail; small-business is a
        # minority share; commercial is rare.
        kyc_tier_weights=(0.85, 0.13, 0.02),
        # Credit unions are predominantly electronic / debit; minimal
        # wire activity.
        channel_weights=(0.08, 0.50, 0.07, 0.05, 0.30),
        alert_sensitivity=1.4,  # less-sophisticated monitoring → more FPs
    ),
)


KYC_TIER_NAMES = ("retail", "small_business", "commercial")
CHANNEL_NAMES = ("wire", "electronic", "check", "cash", "debit")

# Per-KYC-tier transaction-amount distributions (lognormal).
# Calibration: rough industry norms for typical transaction sizes.
# Lognormal because real transaction amounts are heavy-tailed.
KYC_AMOUNT_PARAMS = {
    # tier:        (mu, sigma)  → mean ≈ exp(mu + sigma**2/2)
    "retail":          (5.0, 1.1),   # mean ~$270, P95 ~$1100
    "small_business":  (7.0, 1.3),   # mean ~$2,500, P95 ~$10,000
    "commercial":      (9.0, 1.5),   # mean ~$25,000, P95 ~$130,000
}

# Account types by KYC tier
KYC_ACCOUNT_TYPES = {
    "retail": ("checking", "savings"),
    "small_business": ("business_checking", "merchant_services"),
    "commercial": ("commercial_demand", "treasury_management"),
}


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def make_customer_id(bank_id: str, idx: int) -> str:
    """Bank-namespaced customer ID."""
    return f"{bank_id}_cust_{idx:06d}"


def make_account_id(bank_id: str, customer_idx: int, account_idx: int) -> str:
    return f"{bank_id}_acct_{customer_idx:06d}_{account_idx:02d}"


def hash_counterparty(value: str) -> str:
    """One-way hash of a counterparty identifier for cross-bank linkage.

    The system never exposes raw counterparty IDs across banks. Hashes
    are deterministic so two banks holding accounts at the same
    counterparty can correlate via the hash without sharing the ID.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def generate_customers(profile: BankProfile, rng: np.random.Generator) -> list[dict]:
    """Generate the customer table for one bank."""
    customers = []
    tiers = rng.choice(
        KYC_TIER_NAMES,
        size=profile.n_customers,
        p=profile.kyc_tier_weights,
    )
    # Approximate calibration: a synthetic year-of-birth roughly
    # consistent with adult US population. Banks skew slightly older
    # than overall population.
    birth_years = rng.integers(1935, 2007, size=profile.n_customers)
    # Account open dates spread over last 20 years
    days_since_open = rng.integers(30, 365 * 20, size=profile.n_customers)
    open_dates = WINDOW_END - days_since_open.astype("timedelta64[D]")

    for i in range(profile.n_customers):
        customers.append({
            "customer_id": make_customer_id(profile.bank_id, i),
            "name_hash": hashlib.sha256(
                f"{profile.bank_id}|name|{i}".encode("utf-8")
            ).hexdigest()[:16],
            "dob_year": int(birth_years[i]),
            "kyc_tier": str(tiers[i]),
            "account_open_date": str(open_dates[i]),
        })
    return customers


def generate_accounts(
    profile: BankProfile,
    customers: list[dict],
    rng: np.random.Generator,
) -> list[dict]:
    """Generate the accounts table. Each customer gets 1–3 accounts."""
    accounts = []
    for i, cust in enumerate(customers):
        tier = cust["kyc_tier"]
        # Retail customers typically have checking + maybe savings (1–2).
        # Business / commercial more likely to have multiple.
        if tier == "retail":
            n_accts = int(rng.choice([1, 2], p=[0.45, 0.55]))
        elif tier == "small_business":
            n_accts = int(rng.choice([1, 2, 3], p=[0.30, 0.50, 0.20]))
        else:  # commercial
            n_accts = int(rng.choice([1, 2, 3], p=[0.10, 0.40, 0.50]))

        account_types = KYC_ACCOUNT_TYPES[tier]
        chosen_types = rng.choice(account_types, size=n_accts, replace=True)
        for j in range(n_accts):
            accounts.append({
                "account_id": make_account_id(profile.bank_id, i, j),
                "customer_id": cust["customer_id"],
                "account_type": str(chosen_types[j]),
                "open_date": cust["account_open_date"],
                "status": "active",
            })
    return accounts


def generate_transactions(
    profile: BankProfile,
    customers: list[dict],
    accounts: list[dict],
    rng: np.random.Generator,
) -> list[dict]:
    """Generate the transactions table.

    Transaction counts per customer are Poisson(λ) where λ depends on
    the customer's KYC tier. Amounts are tier-conditional lognormal.
    Channel mix follows the bank's profile.
    """
    # Group accounts by customer for fast lookup
    accounts_by_customer: dict[str, list[dict]] = {}
    for a in accounts:
        accounts_by_customer.setdefault(a["customer_id"], []).append(a)

    # Per-tier transaction-frequency multipliers (relative to bank mean).
    # Commercial customers have many more transactions than retail.
    tier_freq_multiplier = {
        "retail": 0.7,
        "small_business": 1.8,
        "commercial": 4.5,
    }

    # Build a small synthetic external-counterparty pool. These represent
    # merchants, employers, and other-bank accounts that bank customers
    # interact with. ~500 distinct counterparties keeps the graph dense
    # enough to make some natural pattern-detection signal.
    ext_counterparty_pool = [
        f"ext_cp_{i:05d}" for i in range(500)
    ]

    transactions = []
    txn_idx = 0

    # Use vectorized sampling where possible.
    for cust_idx, cust in enumerate(customers):
        tier = cust["kyc_tier"]
        cust_accounts = accounts_by_customer[cust["customer_id"]]

        # Number of transactions this customer makes in the 12-month
        # window: Poisson with mean = bank_mean × tier_multiplier.
        lam = profile.txns_per_customer_per_year_mean * tier_freq_multiplier[tier]
        n_txns = int(rng.poisson(lam))

        if n_txns == 0:
            continue

        # Pick an account for each transaction (uniform over the
        # customer's own accounts).
        account_choices = rng.choice(
            [a["account_id"] for a in cust_accounts],
            size=n_txns,
        )

        # Counterparty: hashed external pool. Most transactions go to
        # external counterparties; a small fraction are intra-bank
        # (account-to-account at the same bank, e.g., transfers).
        intra_bank = rng.random(n_txns) < 0.15
        cp_choices = []
        for is_intra in intra_bank:
            if is_intra:
                # Intra-bank: another customer's account at this bank
                other_cust_idx = int(rng.integers(0, len(customers)))
                while other_cust_idx == cust_idx:
                    other_cust_idx = int(rng.integers(0, len(customers)))
                other_accts = accounts_by_customer[customers[other_cust_idx]["customer_id"]]
                cp_raw = other_accts[int(rng.integers(0, len(other_accts)))]["account_id"]
            else:
                cp_raw = ext_counterparty_pool[int(rng.integers(0, len(ext_counterparty_pool)))]
            cp_choices.append(hash_counterparty(cp_raw))

        # Amount: tier-conditional lognormal
        mu, sigma = KYC_AMOUNT_PARAMS[tier]
        amounts = rng.lognormal(mean=mu, sigma=sigma, size=n_txns)
        # Clip to a sensible upper bound to avoid absurd outliers in
        # the synthetic data.
        amounts = np.clip(amounts, 1.0, 250_000.0)
        # Round to cents
        amounts = np.round(amounts, 2)

        # Channel: per-bank profile
        channels = rng.choice(
            CHANNEL_NAMES,
            size=n_txns,
            p=profile.channel_weights,
        )

        # Transaction type: incoming vs outgoing (rough 50/50)
        directions = rng.choice(["credit", "debit"], size=n_txns)

        # Timestamps: spread uniformly over the 12-month window
        day_offsets = rng.integers(0, WINDOW_DAYS, size=n_txns)
        timestamps = WINDOW_START + day_offsets.astype("timedelta64[D]")
        # Add a random hour within the day for realism
        hour_offsets = rng.integers(0, 24, size=n_txns)

        for k in range(n_txns):
            ts = np.datetime64(timestamps[k], "h") + np.timedelta64(int(hour_offsets[k]), "h")
            transactions.append({
                "transaction_id": f"{profile.bank_id}_txn_{txn_idx:08d}",
                "account_id": str(account_choices[k]),
                "counterparty_account_id_hashed": cp_choices[k],
                "amount": float(amounts[k]),
                "currency": "USD",
                "transaction_type": str(directions[k]),
                "timestamp": str(ts),
                "channel": str(channels[k]),
            })
            txn_idx += 1

    return transactions


def generate_suspicious_signals(
    profile: BankProfile,
    transactions: list[dict],
    rng: np.random.Generator,
) -> list[dict]:
    """Generate the bank's pre-existing suspicious-activity alerts.

    Real-world AML systems report ~95% false-positive rates on alerts.
    We simulate this with a high-noise rule-based scorer that flags
    transactions exceeding $9,000 (just below the CTR threshold — a
    classic structuring tell) plus a small random share of high-amount
    transactions.

    The flag rate is scaled by bank.alert_sensitivity to differentiate
    the three banks.
    """
    signals = []
    sig_idx = 0
    for txn in transactions:
        # Rule 1: amount in the structuring suspicion zone
        # ($9,000–$9,999 — just below the CTR threshold).
        is_structuring_zone = 9_000 <= txn["amount"] < CTR_THRESHOLD_USD
        # Rule 2: enhanced-recordkeeping zone ($3,000–$10,000).
        is_recordkeeping_zone = ENHANCED_RECORDKEEPING_USD <= txn["amount"] < CTR_THRESHOLD_USD
        # Rule 3: high-velocity flag (random small probability).
        is_velocity_flag = rng.random() < 0.001 * profile.alert_sensitivity

        if is_structuring_zone:
            signal_type = "amount_near_ctr_threshold"
            severity = 0.7
        elif is_recordkeeping_zone and rng.random() < 0.05 * profile.alert_sensitivity:
            signal_type = "enhanced_recordkeeping_zone"
            severity = 0.3
        elif is_velocity_flag:
            signal_type = "high_velocity"
            severity = 0.5
        else:
            continue

        signals.append({
            "signal_id": f"{profile.bank_id}_sig_{sig_idx:07d}",
            "transaction_id": txn["transaction_id"],
            "signal_type": signal_type,
            "severity": severity,
            "computed_at": txn["timestamp"],
        })
        sig_idx += 1
    return signals


# ---------------------------------------------------------------------------
# DB writer
# ---------------------------------------------------------------------------

CREATE_STATEMENTS = (
    """
    CREATE TABLE customers (
        customer_id TEXT PRIMARY KEY,
        name_hash TEXT NOT NULL,
        dob_year INTEGER NOT NULL,
        kyc_tier TEXT NOT NULL,
        account_open_date TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE accounts (
        account_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL REFERENCES customers(customer_id),
        account_type TEXT NOT NULL,
        open_date TEXT NOT NULL,
        status TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE transactions (
        transaction_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES accounts(account_id),
        counterparty_account_id_hashed TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        channel TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE suspicious_signals (
        signal_id TEXT PRIMARY KEY,
        transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
        signal_type TEXT NOT NULL,
        severity REAL NOT NULL,
        computed_at TEXT NOT NULL
    )
    """,
)

CREATE_INDEXES = (
    "CREATE INDEX idx_accounts_customer ON accounts(customer_id)",
    "CREATE INDEX idx_txns_account ON transactions(account_id)",
    "CREATE INDEX idx_txns_cp_hash ON transactions(counterparty_account_id_hashed)",
    "CREATE INDEX idx_txns_amount ON transactions(amount)",
    "CREATE INDEX idx_txns_timestamp ON transactions(timestamp)",
    "CREATE INDEX idx_signals_txn ON suspicious_signals(transaction_id)",
)


def write_bank(
    profile: BankProfile,
    customers: list[dict],
    accounts: list[dict],
    transactions: list[dict],
    signals: list[dict],
) -> Path:
    """Write a single bank's data to its SQLite DB."""
    db_path = SILOS_DIR / f"{profile.bank_id}.db"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()

    for stmt in CREATE_STATEMENTS:
        cur.execute(stmt)

    cur.executemany(
        "INSERT INTO customers VALUES (:customer_id, :name_hash, :dob_year, :kyc_tier, :account_open_date)",
        customers,
    )
    cur.executemany(
        "INSERT INTO accounts VALUES (:account_id, :customer_id, :account_type, :open_date, :status)",
        accounts,
    )
    cur.executemany(
        "INSERT INTO transactions VALUES (:transaction_id, :account_id, "
        ":counterparty_account_id_hashed, :amount, :currency, :transaction_type, "
        ":timestamp, :channel)",
        transactions,
    )
    cur.executemany(
        "INSERT INTO suspicious_signals VALUES (:signal_id, :transaction_id, "
        ":signal_type, :severity, :computed_at)",
        signals,
    )

    for stmt in CREATE_INDEXES:
        cur.execute(stmt)

    con.commit()
    con.close()
    return db_path


def main() -> None:
    SILOS_DIR.mkdir(parents=True, exist_ok=True)
    t_total = time.time()
    summary = []

    for profile in BANKS:
        t0 = time.time()
        rng = np.random.default_rng(silo_seed(profile.bank_id))

        print(f"\n=== Building {profile.display_name} ===")
        print(f"  type:                  {profile.bank_type}")
        print(f"  target customers:      {profile.n_customers:,}")

        customers = generate_customers(profile, rng)
        accounts = generate_accounts(profile, customers, rng)
        transactions = generate_transactions(profile, customers, accounts, rng)
        signals = generate_suspicious_signals(profile, transactions, rng)

        db_path = write_bank(profile, customers, accounts, transactions, signals)
        elapsed = time.time() - t0

        kyc_dist = {t: 0 for t in KYC_TIER_NAMES}
        for c in customers:
            kyc_dist[c["kyc_tier"]] += 1

        ch_dist = {ch: 0 for ch in CHANNEL_NAMES}
        for t in transactions:
            ch_dist[t["channel"]] += 1

        size_mb = db_path.stat().st_size / 1024 / 1024
        summary.append({
            "bank": profile.bank_id,
            "customers": len(customers),
            "accounts": len(accounts),
            "transactions": len(transactions),
            "signals": len(signals),
            "size_mb": size_mb,
            "kyc": kyc_dist,
            "channel": ch_dist,
        })

        print(f"  customers:             {len(customers):,}")
        print(f"    retail:              {kyc_dist['retail']:,} "
              f"({100*kyc_dist['retail']/len(customers):.1f}%)")
        print(f"    small business:      {kyc_dist['small_business']:,} "
              f"({100*kyc_dist['small_business']/len(customers):.1f}%)")
        print(f"    commercial:          {kyc_dist['commercial']:,} "
              f"({100*kyc_dist['commercial']/len(customers):.1f}%)")
        print(f"  accounts:              {len(accounts):,}")
        print(f"  transactions:          {len(transactions):,}")
        print(f"  suspicious signals:    {len(signals):,} "
              f"({100*len(signals)/max(len(transactions),1):.2f}% of txns)")
        print(f"  size:                  {size_mb:.1f} MB")
        print(f"  elapsed:               {elapsed:.1f}s")

    print(f"\nTotal time: {time.time()-t_total:.1f}s")
    print(f"Total dataset across 3 banks:")
    print(f"  customers:    {sum(s['customers'] for s in summary):,}")
    print(f"  transactions: {sum(s['transactions'] for s in summary):,}")
    print(f"  signals:      {sum(s['signals'] for s in summary):,}")
    print(f"  size:         {sum(s['size_mb'] for s in summary):.1f} MB")
    print("\nPlanted scenarios (S1 ring, S2 ring, S3 layering, S4 PEP) are NOT")
    print("in this baseline output. Next: uv run python data/scripts/plant_scenarios.py")


if __name__ == "__main__":
    main()
