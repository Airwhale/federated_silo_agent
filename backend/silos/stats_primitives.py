"""Bank-local stats primitives with DP accounting and provenance."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, TypeAlias

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.silos.budget import PrivacyBudgetLedger, RequesterKey
from backend.silos.dp import (
    add_gaussian_noise,
    eps_delta_display,
    sigma_for_zcdp,
    validate_opendp_gaussian_map,
)
from backend.silos.local_reader import bank_db_path
from shared.enums import BankId, PrivacyUnit, ResponseValueKind, SignalType
from shared.identifiers import hash_identifier
from shared.messages import BankAggregate, PrimitiveCallRecord


DEFAULT_AMOUNT_BUCKETS: tuple[tuple[float, float], ...] = (
    (0.0, 1_000.0),
    (1_000.0, 5_000.0),
    (5_000.0, 10_000.0),
    (10_000.0, 50_000.0),
    (50_000.0, math.inf),
)
DEFAULT_EDGE_COUNT_BUCKETS: tuple[tuple[int, int | None], ...] = (
    (1, 1),
    (2, 2),
    (3, 4),
    (5, None),
)
REFUSAL_BUDGET_EXHAUSTED = "budget_exhausted"

PrimitiveValue: TypeAlias = int | list[int] | dict[str, bool] | BankAggregate


class PrimitiveModel(BaseModel):
    """Strict Pydantic base for P7 primitive boundary objects."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class DateWindow(PrimitiveModel):
    """Inclusive date window for bank-local primitive queries."""

    start: date
    end: date

    @model_validator(mode="after")
    def start_must_not_exceed_end(self) -> DateWindow:
        if self.start > self.end:
            raise ValueError("window start must be before or equal to end")
        return self

    @classmethod
    def coerce(cls, value: DateWindow | tuple[date, date]) -> DateWindow:
        if isinstance(value, DateWindow):
            return value
        start, end = value
        return cls(start=start, end=end)

    def sqlite_bounds(self) -> tuple[str, str]:
        return (
            f"{self.start.isoformat()}T00",
            f"{(self.end + timedelta(days=1)).isoformat()}T00",
        )


class PrimitiveResult(PrimitiveModel):
    """Typed result for one primitive call or one structural refusal."""

    value: PrimitiveValue | None = None
    records: list[PrimitiveCallRecord] = Field(default_factory=list)
    refusal_reason: Literal["budget_exhausted"] | None = None

    @model_validator(mode="after")
    def success_or_refusal(self) -> PrimitiveResult:
        if self.refusal_reason is None:
            if self.value is None or not self.records:
                raise ValueError("successful primitive results require value and records")
            return self
        if self.value is not None or self.records:
            raise ValueError("refused primitive results cannot include value or records")
        return self

    @property
    def record(self) -> PrimitiveCallRecord:
        if len(self.records) != 1:
            raise ValueError("primitive result does not contain exactly one record")
        return self.records[0]


class BankStatsPrimitives:
    """Deterministic primitive layer for one bank silo."""

    def __init__(
        self,
        *,
        bank_id: BankId,
        db_path: Path | None = None,
        ledger: PrivacyBudgetLedger | None = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        if bank_id == BankId.FEDERATION:
            raise ValueError("federation has no bank-local primitive layer")
        self.bank_id = bank_id
        self.db_path = db_path or bank_db_path(bank_id)
        self.ledger = ledger or PrivacyBudgetLedger()
        self.rng = rng or np.random.default_rng()

    def count_entities_by_name_hash(
        self,
        *,
        name_hashes: list[str],
        requester: RequesterKey,
        rho: float = 0.0,
    ) -> PrimitiveResult:
        """Return how many requested name hashes are present in this bank."""
        _require_non_empty(name_hashes, "name_hashes")
        _require_no_dp(rho)

        unique_hashes = sorted(set(name_hashes))
        placeholders = ",".join("?" for _ in unique_hashes)
        query = f"""
            SELECT COUNT(DISTINCT name_hash)
            FROM customers
            WHERE name_hash IN ({placeholders})
        """
        with self._connect() as con:
            value = int(con.execute(query, unique_hashes).fetchone()[0])

        return PrimitiveResult(
            value=value,
            records=[
                self._record(
                    field_name="entity_count",
                    primitive_name="count_entities_by_name_hash",
                    args={
                        "name_hashes": unique_hashes,
                        "requester": requester.stable_key,
                        "rho": rho,
                    },
                    privacy_unit=PrivacyUnit.NONE,
                    rho_debited=0.0,
                    sigma_applied=None,
                    sensitivity=1.0,
                    returned_value_kind=ResponseValueKind.INT,
                )
            ],
        )

    def alert_count_for_entity(
        self,
        *,
        name_hash: str,
        window: DateWindow | tuple[date, date],
        requester: RequesterKey,
        rho: float = 0.02,
        signal_type: str | SignalType | None = None,
    ) -> PrimitiveResult:
        """Return a DP-protected suspicious-signal count for one entity."""
        parsed_window = DateWindow.coerce(window)
        if self.ledger.remaining(requester) < rho:
            return _budget_refusal()

        start, end = parsed_window.sqlite_bounds()
        params: list[str] = [name_hash, start, end]
        signal_filter = ""
        if signal_type is not None:
            signal_filter = "AND s.signal_type = ?"
            params.append(signal_type.value if isinstance(signal_type, SignalType) else signal_type)

        query = f"""
            SELECT COUNT(DISTINCT s.signal_id)
            FROM suspicious_signals s
            JOIN transactions t ON s.transaction_id = t.transaction_id
            JOIN accounts a ON t.account_id = a.account_id
            JOIN customers c ON a.customer_id = c.customer_id
            WHERE c.name_hash = ?
              AND t.timestamp >= ?
              AND t.timestamp < ?
              {signal_filter}
        """
        with self._connect() as con:
            true_value = int(con.execute(query, params).fetchone()[0])

        sigma = sigma_for_zcdp(sensitivity=1.0, rho=rho)
        validate_opendp_gaussian_map(sensitivity=1.0, rho=rho, sigma=sigma)
        noisy = add_gaussian_noise(
            float(true_value),
            sensitivity=1.0,
            rho=rho,
            rng=self.rng,
        )
        debit = self.ledger.debit(requester, rho)
        if not debit.allowed:
            return _budget_refusal()

        released = _nonnegative_int(noisy.value)
        return PrimitiveResult(
            value=released,
            records=[
                self._record(
                    field_name="alert_count",
                    primitive_name="alert_count_for_entity",
                    args={
                        "name_hash": name_hash,
                        "window": parsed_window.model_dump(mode="json"),
                        "signal_type": (
                            signal_type.value
                            if isinstance(signal_type, SignalType)
                            else signal_type
                        ),
                        "requester": requester.stable_key,
                        "rho": rho,
                    },
                    privacy_unit=PrivacyUnit.TRANSACTION,
                    rho_debited=rho,
                    eps_delta=noisy.eps_delta_display,
                    sigma_applied=noisy.sigma,
                    sensitivity=1.0,
                    returned_value_kind=ResponseValueKind.INT,
                )
            ],
        )

    def flow_histogram(
        self,
        *,
        name_hashes: list[str],
        window: DateWindow | tuple[date, date],
        requester: RequesterKey,
        buckets: list[tuple[float, float]] | None = None,
        rho: float = 0.03,
        max_transactions: int = 500,
    ) -> PrimitiveResult:
        """Return a DP-protected amount histogram for requested entities."""
        _require_non_empty(name_hashes, "name_hashes")
        parsed_window = DateWindow.coerce(window)
        amount_buckets = tuple(buckets or DEFAULT_AMOUNT_BUCKETS)
        _validate_amount_buckets(amount_buckets)
        if self.ledger.remaining(requester) < rho:
            return _budget_refusal()

        amounts = self._amounts_for_name_hashes(
            name_hashes=sorted(set(name_hashes)),
            window=parsed_window,
            max_transactions=max_transactions,
        )
        true_histogram = _amount_histogram(amounts, amount_buckets)
        # Serial composition over disjoint histogram buckets; parallel composition
        # would permit full ρ per bucket but adds complexity for marginal utility gain.
        rho_per_bucket = rho / len(amount_buckets)
        bucket_sigma = sigma_for_zcdp(sensitivity=1.0, rho=rho_per_bucket)
        validate_opendp_gaussian_map(
            sensitivity=1.0,
            rho=rho_per_bucket,
            sigma=bucket_sigma,
        )
        noised = [
            _nonnegative_int(
                add_gaussian_noise(
                    float(count),
                    sensitivity=1.0,
                    rho=rho_per_bucket,
                    rng=self.rng,
                ).value
            )
            for count in true_histogram
        ]
        debit = self.ledger.debit(requester, rho)
        if not debit.allowed:
            return _budget_refusal()

        return PrimitiveResult(
            value=noised,
            records=[
                self._record(
                    field_name="flow_histogram",
                    primitive_name="flow_histogram",
                    args={
                        "name_hashes": sorted(set(name_hashes)),
                        "window": parsed_window.model_dump(mode="json"),
                        "buckets": _jsonable_buckets(amount_buckets),
                        "max_transactions": max_transactions,
                        "requester": requester.stable_key,
                        "rho": rho,
                    },
                    privacy_unit=PrivacyUnit.TRANSACTION,
                    rho_debited=rho,
                    eps_delta=eps_delta_display(rho=rho),
                    sigma_applied=bucket_sigma,
                    sensitivity=1.0,
                    returned_value_kind=ResponseValueKind.HISTOGRAM,
                )
            ],
        )

    def counterparty_edge_existence(
        self,
        *,
        counterparty_hashes: list[str],
        window: DateWindow | tuple[date, date],
        requester: RequesterKey,
        rho: float = 0.0,
    ) -> PrimitiveResult:
        """Return exact hash-only counterparty edge presence."""
        _require_non_empty(counterparty_hashes, "counterparty_hashes")
        _require_no_dp(rho)
        parsed_window = DateWindow.coerce(window)
        requested = sorted(set(counterparty_hashes))
        start, end = parsed_window.sqlite_bounds()
        placeholders = ",".join("?" for _ in requested)
        query = f"""
            SELECT DISTINCT counterparty_account_id_hashed
            FROM transactions
            WHERE counterparty_account_id_hashed IN ({placeholders})
              AND timestamp >= ?
              AND timestamp < ?
        """
        with self._connect() as con:
            found = {
                str(row[0])
                for row in con.execute(query, [*requested, start, end]).fetchall()
            }
        value = {hash_value: hash_value in found for hash_value in requested}
        return PrimitiveResult(
            value=value,
            records=[
                self._record(
                    field_name="counterparty_edges",
                    primitive_name="counterparty_edge_existence",
                    args={
                        "counterparty_hashes": requested,
                        "window": parsed_window.model_dump(mode="json"),
                        "requester": requester.stable_key,
                        "rho": rho,
                    },
                    privacy_unit=PrivacyUnit.NONE,
                    rho_debited=0.0,
                    sigma_applied=None,
                    sensitivity=1.0,
                    returned_value_kind=ResponseValueKind.HASH_LIST,
                )
            ],
        )

    def pattern_aggregate_for_f2(
        self,
        *,
        window: DateWindow | tuple[date, date],
        requester: RequesterKey,
        rho: float = 0.04,
        max_transactions: int = 10_000,
    ) -> PrimitiveResult:
        """Return a DP-protected bank aggregate for F2 graph analysis."""
        parsed_window = DateWindow.coerce(window)
        if self.ledger.remaining(requester) < rho:
            return _budget_refusal()

        rows = self._transaction_rows(window=parsed_window, max_transactions=max_transactions)
        amounts = [float(row["amount"]) for row in rows]
        counterparty_counts = Counter(
            str(row["counterparty_account_id_hashed"]) for row in rows
        )

        rho_per_component = rho / 2.0
        edge_true = _edge_count_distribution(counterparty_counts)
        # Serial composition over disjoint histogram buckets; parallel composition
        # would permit full ρ per bucket but adds complexity for marginal utility gain.
        edge_rho_per_bucket = rho_per_component / len(DEFAULT_EDGE_COUNT_BUCKETS)
        edge_sigma = sigma_for_zcdp(sensitivity=2.0, rho=edge_rho_per_bucket)
        validate_opendp_gaussian_map(
            sensitivity=2.0,
            rho=edge_rho_per_bucket,
            sigma=edge_sigma,
        )
        flow_true = _amount_histogram(amounts, DEFAULT_AMOUNT_BUCKETS)
        flow_rho_per_bucket = rho_per_component / len(DEFAULT_AMOUNT_BUCKETS)
        flow_sigma = sigma_for_zcdp(sensitivity=1.0, rho=flow_rho_per_bucket)
        validate_opendp_gaussian_map(
            sensitivity=1.0,
            rho=flow_rho_per_bucket,
            sigma=flow_sigma,
        )
        edge_noised = [
            _nonnegative_int(
                add_gaussian_noise(
                    float(count),
                    sensitivity=2.0,
                    rho=edge_rho_per_bucket,
                    rng=self.rng,
                ).value
            )
            for count in edge_true
        ]

        flow_noised = [
            _nonnegative_int(
                add_gaussian_noise(
                    float(count),
                    sensitivity=1.0,
                    rho=flow_rho_per_bucket,
                    rng=self.rng,
                ).value
            )
            for count in flow_true
        ]
        debit = self.ledger.debit(requester, rho)
        if not debit.allowed:
            return _budget_refusal()

        aggregate = BankAggregate(
            bank_id=self.bank_id,
            edge_count_distribution=edge_noised,
            bucketed_flow_histogram=flow_noised,
            rho_debited=rho,
        )
        return PrimitiveResult(
            value=aggregate,
            records=[
                self._record(
                    field_name="edge_count_distribution",
                    primitive_name="pattern_aggregate_for_f2",
                    args={
                        "window": parsed_window.model_dump(mode="json"),
                        "component": "edge_count_distribution",
                        "max_transactions": max_transactions,
                        "requester": requester.stable_key,
                        "rho": rho_per_component,
                    },
                    privacy_unit=PrivacyUnit.TRANSACTION,
                    rho_debited=rho_per_component,
                    eps_delta=eps_delta_display(rho=rho_per_component),
                    sigma_applied=edge_sigma,
                    sensitivity=2.0,
                    returned_value_kind=ResponseValueKind.HISTOGRAM,
                ),
                self._record(
                    field_name="bucketed_flow_histogram",
                    primitive_name="pattern_aggregate_for_f2",
                    args={
                        "window": parsed_window.model_dump(mode="json"),
                        "component": "bucketed_flow_histogram",
                        "max_transactions": max_transactions,
                        "requester": requester.stable_key,
                        "rho": rho_per_component,
                    },
                    privacy_unit=PrivacyUnit.TRANSACTION,
                    rho_debited=rho_per_component,
                    eps_delta=eps_delta_display(rho=rho_per_component),
                    sigma_applied=flow_sigma,
                    sensitivity=1.0,
                    returned_value_kind=ResponseValueKind.HISTOGRAM,
                ),
            ],
        )

    def _amounts_for_name_hashes(
        self,
        *,
        name_hashes: list[str],
        window: DateWindow,
        max_transactions: int,
    ) -> list[float]:
        start, end = window.sqlite_bounds()
        placeholders = ",".join("?" for _ in name_hashes)
        query = f"""
            SELECT t.amount
            FROM transactions t
            JOIN accounts a ON t.account_id = a.account_id
            JOIN customers c ON a.customer_id = c.customer_id
            WHERE c.name_hash IN ({placeholders})
              AND t.timestamp >= ?
              AND t.timestamp < ?
            ORDER BY t.transaction_id
            LIMIT ?
        """
        with self._connect() as con:
            return [
                float(row[0])
                for row in con.execute(
                    query,
                    [*name_hashes, start, end, max_transactions],
                ).fetchall()
            ]

    def _transaction_rows(
        self,
        *,
        window: DateWindow,
        max_transactions: int,
    ) -> list[sqlite3.Row]:
        start, end = window.sqlite_bounds()
        query = """
            SELECT transaction_id, counterparty_account_id_hashed, amount
            FROM transactions
            WHERE timestamp >= ?
              AND timestamp < ?
            ORDER BY transaction_id
            LIMIT ?
        """
        with self._connect() as con:
            return con.execute(query, (start, end, max_transactions)).fetchall()

    def _record(
        self,
        *,
        field_name: str,
        primitive_name: str,
        args: dict[str, object],
        privacy_unit: PrivacyUnit,
        rho_debited: float,
        sigma_applied: float | None,
        sensitivity: float,
        returned_value_kind: ResponseValueKind,
        eps_delta: tuple[float, float] | None = None,
    ) -> PrimitiveCallRecord:
        return PrimitiveCallRecord(
            field_name=field_name,
            primitive_name=primitive_name,
            args_hash=_args_hash(args),
            privacy_unit=privacy_unit,
            rho_debited=rho_debited,
            eps_delta_display=eps_delta,
            sigma_applied=sigma_applied,
            sensitivity=sensitivity,
            returned_value_kind=returned_value_kind,
        )

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"bank database does not exist: {self.db_path}")
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con


def _budget_refusal() -> PrimitiveResult:
    return PrimitiveResult(refusal_reason=REFUSAL_BUDGET_EXHAUSTED)


def _args_hash(args: dict[str, object]) -> str:
    """Hash canonical JSON args for stable audit replay."""
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    return hash_identifier(canonical)


def _require_non_empty(values: list[str], field_name: str) -> None:
    if not values:
        raise ValueError(f"{field_name} must not be empty")


def _require_no_dp(rho: float) -> None:
    if rho != 0.0:
        raise ValueError("this primitive does not apply DP and requires rho=0")


def _validate_amount_buckets(buckets: tuple[tuple[float, float], ...]) -> None:
    if not buckets:
        raise ValueError("buckets must not be empty")
    for lower, upper in buckets:
        if lower < 0.0:
            raise ValueError("bucket lower bounds must be non-negative")
        if lower >= upper:
            raise ValueError("bucket lower bound must be below upper bound")


def _jsonable_buckets(buckets: tuple[tuple[float, float], ...]) -> list[list[float | str]]:
    return [
        [lower, "Infinity" if math.isinf(upper) else upper]
        for lower, upper in buckets
    ]


def _amount_histogram(
    amounts: list[float],
    buckets: tuple[tuple[float, float], ...],
) -> list[int]:
    counts = [0 for _ in buckets]
    for amount in amounts:
        for index, (lower, upper) in enumerate(buckets):
            if lower <= amount < upper:
                counts[index] += 1
                break
    return counts


def _edge_count_distribution(counterparty_counts: Counter[str]) -> list[int]:
    # One transaction can move one counterparty between two adjacent edge-count
    # buckets, L₁ change = 2.
    distribution = [0 for _ in DEFAULT_EDGE_COUNT_BUCKETS]
    for count in counterparty_counts.values():
        for index, (lower, upper) in enumerate(DEFAULT_EDGE_COUNT_BUCKETS):
            if count >= lower and (upper is None or count <= upper):
                distribution[index] += 1
                break
    return distribution


def _nonnegative_int(value: float) -> int:
    return max(0, int(round(value)))
