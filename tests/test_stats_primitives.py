from __future__ import annotations

import sqlite3
from datetime import date

import numpy as np
import pytest

from backend.silos import stats_primitives
from backend.silos.budget import PrivacyBudgetLedger, RequesterKey
from backend.silos.local_reader import bank_db_path
from backend.silos.stats_primitives import (
    MAX_HASH_LIST_LENGTH,
    REFUSAL_BUDGET_EXHAUSTED,
    BankStatsPrimitives,
    DateWindow,
)
from shared.enums import BankId, PrivacyUnit, ResponseValueKind
from shared.messages import BankAggregate


FULL_WINDOW = DateWindow(start=date(2025, 1, 1), end=date(2026, 12, 31))


def requester(responding_bank: BankId = BankId.BANK_ALPHA) -> RequesterKey:
    return RequesterKey(
        requesting_investigator_id="investigator-alpha",
        requesting_bank_id=BankId.BANK_BETA,
        responding_bank_id=responding_bank,
    )


def primitive_layer(rho_max: float = 1.0) -> BankStatsPrimitives:
    return BankStatsPrimitives(
        bank_id=BankId.BANK_ALPHA,
        ledger=PrivacyBudgetLedger(rho_max=rho_max),
        rng=np.random.default_rng(20260513),
    )


def sample_name_hash_with_signal() -> tuple[str, str]:
    query = """
        SELECT c.name_hash, s.signal_type
        FROM suspicious_signals s
        JOIN transactions t ON s.transaction_id = t.transaction_id
        JOIN accounts a ON t.account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
        ORDER BY s.signal_id
        LIMIT 1
    """
    with sqlite3.connect(bank_db_path(BankId.BANK_ALPHA)) as con:
        row = con.execute(query).fetchone()
    return str(row[0]), str(row[1])


def sample_counterparty_hash() -> str:
    with sqlite3.connect(bank_db_path(BankId.BANK_ALPHA)) as con:
        row = con.execute(
            "SELECT counterparty_account_id_hashed FROM transactions ORDER BY transaction_id LIMIT 1"
        ).fetchone()
    return str(row[0])


def test_count_entities_by_name_hash_is_exact_and_provenanced() -> None:
    layer = primitive_layer()
    name_hash, _signal_type = sample_name_hash_with_signal()

    first = layer.count_entities_by_name_hash(
        name_hashes=[name_hash, "missing_hash_000000"],
        requester=requester(),
    )
    second = layer.count_entities_by_name_hash(
        name_hashes=[name_hash, "missing_hash_000000"],
        requester=requester(),
    )

    assert first.value == 1
    assert second.value == first.value
    assert first.record.privacy_unit == PrivacyUnit.NONE
    assert first.record.rho_debited == 0.0
    assert first.record.returned_value_kind == ResponseValueKind.INT
    assert len(first.record.args_hash) == 64


def test_counterparty_edge_existence_is_exact_hash_only() -> None:
    layer = primitive_layer()
    counterparty_hash = sample_counterparty_hash()

    result = layer.counterparty_edge_existence(
        counterparty_hashes=[counterparty_hash, "missing_counterparty_hash"],
        window=FULL_WINDOW,
        requester=requester(),
    )

    assert result.value == {
        counterparty_hash: True,
        "missing_counterparty_hash": False,
    }
    assert result.record.privacy_unit == PrivacyUnit.NONE
    assert result.record.returned_value_kind == ResponseValueKind.HASH_LIST


def test_alert_count_for_entity_debits_budget_and_records_dp_metadata() -> None:
    layer = primitive_layer()
    name_hash, signal_type = sample_name_hash_with_signal()

    result = layer.alert_count_for_entity(
        name_hash=name_hash,
        window=FULL_WINDOW,
        signal_type=signal_type,
        requester=requester(),
        rho=0.02,
    )

    assert isinstance(result.value, int)
    assert result.value >= 0
    assert result.record.privacy_unit == PrivacyUnit.TRANSACTION
    assert result.record.rho_debited == 0.02
    assert result.record.sigma_applied == 5.0
    assert result.record.eps_delta_display is not None
    assert layer.ledger.spent(requester()) == 0.02


def test_flow_histogram_returns_dp_histogram_with_fixed_shape() -> None:
    layer = primitive_layer()
    name_hash, _signal_type = sample_name_hash_with_signal()

    result = layer.flow_histogram(
        name_hashes=[name_hash],
        window=FULL_WINDOW,
        requester=requester(),
        rho=0.03,
    )

    assert isinstance(result.value, list)
    assert len(result.value) == 5
    assert all(isinstance(value, int) and value >= 0 for value in result.value)
    assert result.record.returned_value_kind == ResponseValueKind.HISTOGRAM
    assert result.record.rho_debited == 0.03


def test_pattern_aggregate_for_f2_returns_bank_aggregate_and_two_records() -> None:
    layer = primitive_layer()

    result = layer.pattern_aggregate_for_f2(
        window=FULL_WINDOW,
        requester=requester(),
        rho=0.04,
    )

    assert isinstance(result.value, BankAggregate)
    assert result.value.bank_id == BankId.BANK_ALPHA
    assert len(result.value.edge_count_distribution) == 4
    assert len(result.value.bucketed_flow_histogram) == 5
    assert result.value.rho_debited == 0.04
    assert {record.field_name for record in result.records} == {
        "edge_count_distribution",
        "bucketed_flow_histogram",
    }
    assert sum(record.rho_debited for record in result.records) == 0.04


def test_budget_exhaustion_returns_structural_refusal() -> None:
    layer = primitive_layer(rho_max=0.01)
    name_hash, _signal_type = sample_name_hash_with_signal()

    result = layer.alert_count_for_entity(
        name_hash=name_hash,
        window=FULL_WINDOW,
        requester=requester(),
        rho=0.02,
    )

    assert result.value is None
    assert result.records == []
    assert result.refusal_reason == REFUSAL_BUDGET_EXHAUSTED


def test_concurrent_dp_primitive_calls_serialize_rng_access() -> None:
    """The primitives layer serializes RNG access across threads.

    numpy.random.Generator is not thread-safe. Concurrent `rng.normal()`
    calls can correlate samples or corrupt internal state, which would
    break the audit-replay determinism property the debit-before-noise
    reorder secures. BankStatsPrimitives holds a `threading.Lock` over
    `_sample_gaussian_noise` so that the noise step runs atomically.
    """
    import threading

    layer = primitive_layer(rho_max=10.0)
    name_hash, _signal_type = sample_name_hash_with_signal()
    barrier = threading.Barrier(8)
    results: list[int] = []
    errors: list[BaseException] = []

    def worker(slot: int) -> None:
        # Each thread gets its own RequesterKey so they each have their
        # own budget bucket, so the only contention is on the RNG itself.
        key = RequesterKey(
            requesting_investigator_id=f"investigator-{slot}",
            requesting_bank_id=BankId.BANK_BETA,
            responding_bank_id=BankId.BANK_ALPHA,
        )
        try:
            barrier.wait(timeout=5.0)
            result = layer.alert_count_for_entity(
                name_hash=name_hash,
                window=FULL_WINDOW,
                requester=key,
                rho=0.02,
            )
            assert isinstance(result.value, int)
            results.append(result.value)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not errors, f"thread errors: {errors}"
    assert len(results) == 8


def test_args_hash_is_stable_under_small_float_drift() -> None:
    """args_hash canonicalizes floats before hashing so tiny drift is invisible.

    rho values arriving from arithmetic on different platforms could differ
    in the last few bits of their double-precision representation. The
    args_hash rounds floats to 9 decimal places before JSON serialization,
    so values within that precision produce the same hash.
    """
    from backend.silos.stats_primitives import _args_hash

    base = {"rho": 0.02, "requester": "investigator|bank_alpha|bank_beta"}
    drifted = {"rho": 0.02 + 1e-15, "requester": "investigator|bank_alpha|bank_beta"}
    different = {"rho": 0.03, "requester": "investigator|bank_alpha|bank_beta"}

    assert _args_hash(base) == _args_hash(drifted)
    assert _args_hash(base) != _args_hash(different)


def test_record_property_raises_on_multi_record_result() -> None:
    """PrimitiveResult.record is a single-record convenience; multi-record raises.

    `pattern_aggregate_for_f2` returns two records (one per histogram
    component). Callers of that primitive must iterate `result.records`;
    accessing `.record` raises ValueError citing the multi-record case.
    """
    layer = primitive_layer()
    result = layer.pattern_aggregate_for_f2(
        window=FULL_WINDOW,
        requester=requester(),
        rho=0.04,
    )

    assert len(result.records) == 2  # confirms this is a multi-record primitive
    with pytest.raises(ValueError, match="multi-record"):
        _ = result.record


def test_primitive_call_closes_database_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each primitive call must close its SQLite connection on exit.

    Python's `sqlite3.Connection.__exit__` only commits/rolls back the
    implicit transaction — it does NOT close the connection. A naive
    `with self._connect() as con:` would leak a file descriptor on every
    primitive call. P7 wraps `_connect` in `@contextlib.contextmanager`
    with `finally: con.close()` so closure is deterministic.
    """
    close_count = [0]

    class TrackingConnection(sqlite3.Connection):
        def close(self) -> None:  # type: ignore[override]
            close_count[0] += 1
            super().close()

    real_connect = sqlite3.connect

    def tracking_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        kwargs["factory"] = TrackingConnection
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)

    layer = primitive_layer()
    name_hash, _signal_type = sample_name_hash_with_signal()

    layer.count_entities_by_name_hash(
        name_hashes=[name_hash],
        requester=requester(),
    )
    layer.alert_count_for_entity(
        name_hash=name_hash,
        window=FULL_WINDOW,
        requester=requester(),
        rho=0.02,
    )

    # Both primitive calls opened a connection and must have closed it.
    assert close_count[0] == 2


def test_hash_list_inputs_capped_at_runtime_layer() -> None:
    """Hash-list primitives refuse oversize inputs before issuing SQL.

    The P4 schema caps `name_hashes`/`account_hashes`/`entity_hashes` at
    100 entries to stay well under SQLite's SQLITE_LIMIT_VARIABLE_NUMBER
    (default 999) on `IN ({placeholders})` queries. The primitives layer
    mirrors that cap as defense-in-depth so a direct call (tests, future
    internal flows) raises a clear error instead of hitting the SQLite
    cliff with a cryptic 'too many SQL variables' message.
    """
    layer = primitive_layer()
    oversize = [f"{i:016x}" for i in range(MAX_HASH_LIST_LENGTH + 1)]

    with pytest.raises(ValueError, match="at most"):
        layer.count_entities_by_name_hash(
            name_hashes=oversize,
            requester=requester(),
        )

    with pytest.raises(ValueError, match="at most"):
        layer.flow_histogram(
            name_hashes=oversize,
            window=FULL_WINDOW,
            requester=requester(),
            rho=0.01,
        )

    with pytest.raises(ValueError, match="at most"):
        layer.counterparty_edge_existence(
            counterparty_hashes=oversize,
            window=FULL_WINDOW,
            requester=requester(),
        )


def test_failed_dp_primitive_does_not_debit_budget(tmp_path) -> None:
    ledger = PrivacyBudgetLedger(rho_max=1.0)
    key = requester()
    layer = BankStatsPrimitives(
        bank_id=BankId.BANK_ALPHA,
        db_path=tmp_path / "missing.db",
        ledger=ledger,
        rng=np.random.default_rng(20260513),
    )

    with pytest.raises(FileNotFoundError):
        layer.alert_count_for_entity(
            name_hash="missing_hash_000000",
            window=FULL_WINDOW,
            requester=key,
            rho=0.02,
        )

    assert ledger.spent(key) == 0.0


def test_budget_refusal_does_not_advance_rng_state() -> None:
    """If a debit fails, the RNG must not advance (audit-replay determinism).

    The DP primitives commit the budget debit BEFORE drawing noise. This
    means an exhausted-budget refusal must short-circuit without consuming
    any random samples, so a fresh replay against the same seed reaches
    the same RNG state as the original successful run.
    """
    ledger = PrivacyBudgetLedger(rho_max=0.005)  # too low for one alert_count call
    key = requester()
    rng = np.random.default_rng(20260513)
    layer = BankStatsPrimitives(
        bank_id=BankId.BANK_ALPHA,
        ledger=ledger,
        rng=rng,
    )
    name_hash, _signal_type = sample_name_hash_with_signal()

    # Snapshot the RNG state, run a call that must refuse, and verify the
    # RNG produces the same next sample as a fresh generator with the same seed.
    refused = layer.alert_count_for_entity(
        name_hash=name_hash,
        window=FULL_WINDOW,
        requester=key,
        rho=0.02,
    )
    assert refused.refusal_reason == REFUSAL_BUDGET_EXHAUSTED
    assert ledger.spent(key) == 0.0

    expected_next_sample = np.random.default_rng(20260513).normal()
    assert rng.normal() == expected_next_sample


def test_failed_noise_sampling_after_debit_spends_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Documented trade-off: noise failures AFTER debit are budget-spending.

    The audit-replay determinism property (every committed debit corresponds
    to exactly one RNG advance) requires that we commit the budget before
    sampling noise. If the noise mechanism fails after the debit commits,
    the budget is consumed. This is acceptable because (a) the failure is
    exotic — OpenDP's Gaussian mechanism doesn't fail under normal use —
    and (b) preserving determinism for the regulator-audit case is more
    valuable than recovering budget for an unexpected mechanism crash.
    """
    ledger = PrivacyBudgetLedger(rho_max=1.0)
    key = requester()
    layer = BankStatsPrimitives(
        bank_id=BankId.BANK_ALPHA,
        ledger=ledger,
        rng=np.random.default_rng(20260513),
    )
    name_hash, _signal_type = sample_name_hash_with_signal()

    def fail_noise(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("noise backend failed")

    monkeypatch.setattr(stats_primitives, "add_gaussian_noise", fail_noise)

    with pytest.raises(RuntimeError, match="noise backend failed"):
        layer.alert_count_for_entity(
            name_hash=name_hash,
            window=FULL_WINDOW,
            requester=key,
            rho=0.02,
        )

    # Budget IS spent — the debit committed before the noise call failed.
    assert ledger.spent(key) == 0.02
