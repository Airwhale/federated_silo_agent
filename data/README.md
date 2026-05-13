# `data/` Bank Silo Datasets

This folder contains the synthetic bank data for the AML multi-agent demo. The active data pipeline builds three bank-local SQLite databases and plants cross-bank money-laundering scenarios that are visible only through federation.

The prior clinical pipeline is preserved under `data/scripts/clinical-archive/` for history. It is not the active build.

## What's In This Folder

```text
data/
  README.md
  silos/
    bank_alpha.db
    bank_beta.db
    bank_gamma.db
  scripts/
    __init__.py
    build_banks.py
    plant_scenarios.py
    validate_banks.py
    clinical-archive/
      download_synthea_omop.py
      build_silos.py
      feature_engineering.py
      apply_scenarios.py
      validate.py
      vocab.py
```

## Active AML Dataset

Three SQLite databases, one per bank:

```text
customers          (customer_id, name_hash, dob_year, kyc_risk_tier, account_open_date)
accounts           (account_id, customer_id, account_type, open_date, status)
transactions       (transaction_id, account_id, counterparty_account_id_hashed,
                    amount, currency, transaction_type, timestamp, channel)
suspicious_signals (signal_id, transaction_id, signal_type, severity, computed_at)
ground_truth_entities (entity_id, customer_id, name_hash, cover_business,
                       scenario, role, is_pep)
```

Current canonical build:

| Bank | Customers | Accounts | Transactions | Suspicious signals | Ground-truth rows |
|---|---:|---:|---:|---:|---:|
| Bank Alpha | 8,009 | 14,043 | 112,212 | 1,969 | 9 |
| Bank Beta | 5,009 | 8,375 | 46,743 | 794 | 9 |
| Bank Gamma | 3,005 | 4,836 | 22,961 | 313 | 5 |

## Planted Scenarios

- **S1 headline structuring ring:** 5 shell entities spanning all three banks. Each entity has accounts at exactly two banks. The ring generates 200 dual-booked sub-CTR transfer rows, counted as 100 debit-credit transfer pairs.
- **S2 smaller structuring ring:** 3 entities spanning Bank Alpha and Bank Beta only. This tests partial-bank federation.
- **S3 layering chain:** 4 entities moving funds through Alpha, Beta, Gamma, and back to Alpha.
- **S4 PEP marker:** one S1 entity has a synthetic politically exposed person relation for the sanctions or PEP screening agent.

The intended product claim is specific: pooled cross-bank analysis can recover the planted network, while any single bank sees only noisy local business activity and cannot identify the complete ring.

## Reproducibility

- Deterministic seed: `SEED=20260512`
- Bank-specific RNG seeds are derived through stable SHA-256 hashing.
- `tests/test_data_checksum.py` stores a content-based fingerprint of the canonical generated databases.
- The fingerprint hashes row content instead of SQLite bytes, so incidental SQLite page layout differences do not create false failures.

## Regenerating The Dataset

From the repo root:

```powershell
uv sync
uv run python data/scripts/build_banks.py
uv run python data/scripts/plant_scenarios.py
uv run python data/scripts/validate_banks.py
uv run pytest tests/test_data_checksum.py
```

`build_banks.py` rebuilds the baseline databases. `plant_scenarios.py` inserts shell entities, dual-booked transactions, suspicious signals, and ground-truth labels. `validate_banks.py` confirms schema, planted scenario presence, cross-bank detectability, single-bank invisibility, PEP placement, layering-loop closure, and debit-credit balance closure.

## Clinical Pipeline Archive

The prior clinical pipeline used Synthea-OMOP data and five hospital silos. It is preserved in `data/scripts/clinical-archive/` and documented in `docs/clinical-archive/plan.md`.

Those scripts are historical reference only. They will not run end-to-end from the current active AML dataset without reconstructing the old clinical raw-data inputs from git history.
