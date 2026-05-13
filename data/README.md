# `data/` — Bank Silo Datasets (AML pivot, build pending)

This folder will contain the three synthetic bank SQLite databases used by the AML multi-agent demo. The data layer is currently **not built** — the project pivoted from clinical federated stats (Synthea-OMOP) to cross-bank AML mid-build, and the new data pipeline begins on Day 1 of the post-pivot build.

> **Status:** scripts not yet written; databases not yet generated. The clinical-archive subfolder preserves the prior Synthea-OMOP pipeline as historical reference.

---

## What's in this folder

```
data/
├── README.md                        # This file
├── scripts/
│   ├── __init__.py
│   └── clinical-archive/            # Prior Synthea-OMOP pipeline (preserved for history)
│       ├── download_synthea_omop.py
│       ├── build_silos.py
│       ├── feature_engineering.py
│       ├── apply_scenarios.py
│       ├── validate.py
│       └── vocab.py
├── raw/                             # (will hold synthetic source artifacts if any)
└── silos/                           # (will hold three bank SQLite databases)
```

The AML scripts coming on Day 1 (per [`../plan.md`](../plan.md) Section 11):

- `data/scripts/build_banks.py` — generate three synthetic banks
- `data/scripts/plant_ring.py` — embed the 5-entity structuring ring
- `data/scripts/validate_banks.py` — confirm the ring is detectable centrally on the pooled data and undetectable per bank

---

## What the AML data will look like (target shape)

Three SQLite databases, one per bank:

```
customers          (customer_id, name_hash, dob_year, kyc_risk_tier, account_open_date)
accounts           (account_id, customer_id, account_type, open_date, status)
transactions       (transaction_id, account_id, counterparty_account_id_hashed,
                    amount, currency, transaction_type, timestamp, channel)
suspicious_signals (signal_id, transaction_id, signal_type, severity, computed_at)
```

| Bank | Customers | Transactions (12-month window) |
|---|---:|---:|
| Bank Alpha | ~5,000 | ~50,000 |
| Bank Beta | ~5,000 | ~50,000 |
| Bank Gamma | ~5,000 | ~50,000 |
| **Pooled** | **~15,000** | **~150,000** |

Total disk footprint: ~50 MB across three SQLite files.

### Planted scenario: 5-entity structuring ring

- 5 shell entities, each with accounts at exactly two of the three banks
- ~200 sub-$10K transfers across the ring over a 90-day window
- Per-bank velocity stays just below the bank's individual structuring-alert threshold
- Cross-bank pattern forms a closed cycle through all three banks
- One entity has a PEP relation (will trigger F3 sanctions agent)

The whole point: **federated detection succeeds; single-bank detection fails.**

### Reproducibility

- Deterministic seed (`SEED=20260512`, same convention as the clinical pipeline)
- Canonical fingerprint hash baked into `tests/test_data_checksum.py` once the data exists
- Re-running `build_banks.py` + `plant_ring.py` will produce bit-identical SQLite databases

---

## Reconstructing the dataset (after Day 1 build)

Once the AML scripts land, the regeneration workflow will be:

```bash
# 1. Set up Python env (already done if you've run prior pipeline)
uv sync

# 2. Generate three synthetic bank databases (no external download — purely synthetic)
uv run python data/scripts/build_banks.py

# 3. Embed the planted structuring ring
uv run python data/scripts/plant_ring.py

# 4. Verify the ring is centrally detectable AND single-bank invisible
uv run python data/scripts/validate_banks.py

# 5. Run the checksum test to confirm bit-identical reconstruction
uv run pytest tests/test_data_checksum.py
```

No internet required, no API keys, no external data downloads. Pure local synthetic data generation.

---

## Clinical pipeline archive

The prior clinical pipeline (Synthea-OMOP, CHF cohort across five hospital silos) is preserved in [`data/scripts/clinical-archive/`](data/scripts/clinical-archive/). Each script is functional but won't run end-to-end without the OMOP CDM raw data that we don't preserve in the repo. The pipeline produced five hospital silo SQLite databases with ~50 synthetically-labeled CHF patients each (~251 pooled) over a 1,815-cardiac-patient population. The clinical work is documented in [`docs/clinical-archive/plan.md`](../docs/clinical-archive/plan.md).

To reconstruct the clinical pipeline state, check out git commit `5bf0283` (the last clinical-state commit before the AML pivot).
