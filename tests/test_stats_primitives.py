from __future__ import annotations

import sqlite3
from datetime import date

import numpy as np
import pytest

from backend.silos import stats_primitives
from backend.silos.budget import PrivacyBudgetLedger, RequesterKey
from backend.silos.local_reader import bank_db_path
from backend.silos.stats_primitives import (
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


def test_failed_noise_sampling_does_not_debit_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    assert ledger.spent(key) == 0.0
