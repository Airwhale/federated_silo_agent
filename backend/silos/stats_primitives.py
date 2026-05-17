"""Bank-local stats primitives with DP accounting and provenance."""

from __future__ import annotations

import contextlib
import json
import math
import sqlite3
import threading
from collections import Counter
from collections.abc import Iterator
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
from shared.messages import (
    CANDIDATE_HASH_LIMIT,
    BankAggregate,
    DpCompositionMode,
    PrimitiveCallRecord,
)


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
# Defense-in-depth cap on hash-list inputs. P4 schemas enforce
# max_length=100 at the Sec314bQuery boundary; this cap mirrors that bound
# at the primitives layer so direct calls (tests, future internal flows)
# also fail loudly before hitting SQLite's SQLITE_LIMIT_VARIABLE_NUMBER
# (default 999) on `IN ({placeholders})` queries.
MAX_HASH_LIST_LENGTH = 100

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
        """Single-record convenience accessor; raises on multi-record results.

        Most P7 primitives return one `PrimitiveCallRecord`, so `result.record`
        is a readable shortcut for `result.records[0]` in tests and in code
        that knows the primitive is single-record. `pattern_aggregate_for_f2`
        returns TWO records (one per histogram component) and callers of that
        primitive MUST iterate `result.records` directly — accessing `.record`
        on a multi-record result raises `ValueError` to fail loud rather than
        silently returning the first record.
        """
        if len(self.records) != 1:
            raise ValueError(
                "primitive result does not contain exactly one record; "
                "use result.records directly for multi-record primitives "
                "such as pattern_aggregate_for_f2"
            )
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
        # numpy.random.Generator is not thread-safe (documented). Concurrent
        # `rng.normal()` calls can correlate samples or corrupt internal
        # state, breaking the audit-replay determinism we just secured by
        # reordering debit-before-noise. We serialize the actual noise
        # sample with this lock — the critical section is one numpy call,
        # so contention is negligible. The ledger has its own lock for
        # debit RMW; this is the matching lock on the RNG side.
        self._rng_lock = threading.Lock()

    def _sample_gaussian_noise(
        self,
        value: float,
        *,
        sensitivity: float,
        rho: float,
    ) -> "GaussianMechanismResult":  # noqa: F821 — forward ref to dp module
        """Thread-safe Gaussian sample wrapper around `add_gaussian_noise`."""
        with self._rng_lock:
            return add_gaussian_noise(
                value,
                sensitivity=sensitivity,
                rho=rho,
                rng=self.rng,
            )

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
        # Hash list is capped at MAX_HASH_LIST_LENGTH=100 by _require_non_empty
        # above, well under SQLite's SQLITE_LIMIT_VARIABLE_NUMBER (default 999).
        placeholders = ",".join("?" for _ in unique_hashes)
        query = f"""
            SELECT COUNT(DISTINCT name_hash)
            FROM customers
            WHERE name_hash IN ({placeholders})
        """
        with self._connect() as con:
            row = con.execute(query, unique_hashes).fetchone()
        # SQLite's COUNT aggregate always returns exactly one row, so `row`
        # cannot be None in practice. The guard is defensive against future
        # refactors of this primitive into a non-aggregate query shape.
        value = int(row[0]) if row else 0

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
            row = con.execute(query, params).fetchone()
        # SQLite's COUNT aggregate always returns exactly one row, so `row`
        # cannot be None in practice. The guard is defensive against future
        # refactors of this primitive into a non-aggregate query shape.
        true_value = int(row[0]) if row else 0

        # Commit the debit BEFORE drawing noise so audit-replay is deterministic:
        # every committed debit corresponds to exactly one RNG advance. If we
        # sampled noise first and then a concurrent caller raced our debit to
        # exhaustion, the RNG state would drift between original run and replay.
        sigma = sigma_for_zcdp(sensitivity=1.0, rho=rho)
        validate_opendp_gaussian_map(sensitivity=1.0, rho=rho, sigma=sigma)
        debit = self.ledger.debit(requester, rho)
        if not debit.allowed:
            return _budget_refusal()

        noisy = self._sample_gaussian_noise(
            float(true_value),
            sensitivity=1.0,
            rho=rho,
        )
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
                    rho_remaining=debit.rho_remaining,
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
        composition: DpCompositionMode = "parallel_disjoint",
    ) -> PrimitiveResult:
        """Return a DP-protected amount histogram for requested entities."""
        _require_non_empty(name_hashes, "name_hashes")
        parsed_window = DateWindow.coerce(window)
        amount_buckets = tuple(buckets or DEFAULT_AMOUNT_BUCKETS)
        _validate_amount_buckets(amount_buckets)
        bucket_rho = _bucket_rho_for_composition(
            composition=composition,
            rho=rho,
            bucket_count=len(amount_buckets),
        )
        if self.ledger.remaining(requester) < rho:
            return _budget_refusal()

        amounts = self._amounts_for_name_hashes(
            name_hashes=sorted(set(name_hashes)),
            window=parsed_window,
            max_transactions=max_transactions,
        )
        true_histogram = _amount_histogram(amounts, amount_buckets)
        # Default to parallel composition over disjoint histogram buckets: each
        # transaction lands in exactly one bucket (the `for ... break` loop in
        # `_amount_histogram` enforces this), so zCDP parallel composition pays
        # the max bucket rho, not the sum. The optional serial mode is a
        # conservative reviewer-facing fallback that splits the same ledger
        # debit across buckets and therefore adds more noise.
        bucket_sigma = sigma_for_zcdp(sensitivity=1.0, rho=bucket_rho)
        validate_opendp_gaussian_map(
            sensitivity=1.0,
            rho=bucket_rho,
            sigma=bucket_sigma,
        )
        # Commit the debit BEFORE drawing noise so audit-replay is deterministic.
        debit = self.ledger.debit(requester, rho)
        if not debit.allowed:
            return _budget_refusal()

        noised = [
            _nonnegative_int(
                self._sample_gaussian_noise(
                    float(count),
                    sensitivity=1.0,
                    rho=bucket_rho,
                ).value
            )
            for count in true_histogram
        ]
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
                        "composition": composition,
                        "per_bucket_rho": bucket_rho,
                    },
                    privacy_unit=PrivacyUnit.TRANSACTION,
                    rho_debited=rho,
                    rho_remaining=debit.rho_remaining,
                    eps_delta=eps_delta_display(rho=rho),
                    sigma_applied=bucket_sigma,
                    sensitivity=1.0,
                    dp_composition=composition,
                    per_bucket_rho=bucket_rho,
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
        # Hash list is capped at MAX_HASH_LIST_LENGTH=100 by _require_non_empty
        # above, well under SQLite's SQLITE_LIMIT_VARIABLE_NUMBER (default 999).
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
        candidate_entity_hashes: list[str] | None = None,
        rho: float = 0.04,
        max_transactions: int = 10_000,
    ) -> PrimitiveResult:
        """Return a DP-protected bank aggregate for F2 graph analysis."""
        parsed_window = DateWindow.coerce(window)
        candidate_hashes = candidate_entity_hashes or []
        if len(candidate_hashes) > CANDIDATE_HASH_LIMIT:
            raise ValueError(
                f"candidate_entity_hashes cannot exceed {CANDIDATE_HASH_LIMIT}"
            )
        if self.ledger.remaining(requester) < rho:
            return _budget_refusal()

        rows = self._transaction_rows(window=parsed_window, max_transactions=max_transactions)
        amounts = [float(row["amount"]) for row in rows]
        counterparty_counts = Counter(
            str(row["counterparty_account_id_hashed"]) for row in rows
        )
        approved_candidates = sorted(set(candidate_hashes))

        # Sequential composition between the two components (edge distribution
        # and flow histogram) because they share the same underlying data
        # (every transaction contributes to both views). Split rho into edge
        # and flow components.
        rho_per_component = rho / 2.0
        edge_true = _edge_count_distribution(counterparty_counts)
        flow_true = _amount_histogram(amounts, DEFAULT_AMOUNT_BUCKETS)

        # Within each component, buckets are a disjoint partition of the data
        # (one counterparty's edge count is in exactly one bucket; one
        # transaction's amount is in exactly one bucket). zCDP parallel
        # composition lets us use the full per-component rho on each bucket.
        # The ledger debit is the serial sum across components, not across
        # buckets inside a component.
        #
        # Edge sensitivity is the L2 norm of the change vector, not L1.
        # One transaction can move one counterparty between two adjacent buckets,
        # producing a change vector [+1, -1, 0, ...] with L2 norm sqrt(2). The
        # Gaussian mechanism under zCDP is calibrated on L2 sensitivity.
        edge_sensitivity = math.sqrt(2.0)
        edge_sigma = sigma_for_zcdp(sensitivity=edge_sensitivity, rho=rho_per_component)
        validate_opendp_gaussian_map(
            sensitivity=edge_sensitivity,
            rho=rho_per_component,
            sigma=edge_sigma,
        )
        flow_sigma = sigma_for_zcdp(sensitivity=1.0, rho=rho_per_component)
        validate_opendp_gaussian_map(
            sensitivity=1.0,
            rho=rho_per_component,
            sigma=flow_sigma,
        )

        # Commit the debit BEFORE drawing noise so audit-replay is deterministic.
        debit = self.ledger.debit(requester, rho)
        if not debit.allowed:
            return _budget_refusal()

        edge_noised = [
            _nonnegative_int(
                self._sample_gaussian_noise(
                    float(count),
                    sensitivity=edge_sensitivity,
                    rho=rho_per_component,
                ).value
            )
            for count in edge_true
        ]
        flow_noised = [
            _nonnegative_int(
                self._sample_gaussian_noise(
                    float(count),
                    sensitivity=1.0,
                    rho=rho_per_component,
                ).value
            )
            for count in flow_true
        ]

        aggregate = BankAggregate(
            bank_id=self.bank_id,
            edge_count_distribution=edge_noised,
            bucketed_flow_histogram=flow_noised,
            candidate_entity_hashes=approved_candidates,
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
                    rho_remaining=debit.rho_remaining,
                    eps_delta=eps_delta_display(rho=rho_per_component),
                    sigma_applied=edge_sigma,
                    sensitivity=edge_sensitivity,
                    dp_composition="parallel_disjoint",
                    per_bucket_rho=rho_per_component,
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
                    rho_remaining=debit.rho_remaining,
                    eps_delta=eps_delta_display(rho=rho_per_component),
                    sigma_applied=flow_sigma,
                    sensitivity=1.0,
                    dp_composition="parallel_disjoint",
                    per_bucket_rho=rho_per_component,
                    returned_value_kind=ResponseValueKind.HISTOGRAM,
                ),
                self._record(
                    field_name="candidate_entity_hashes",
                    primitive_name="pattern_aggregate_for_f2",
                    args={
                        "window": parsed_window.model_dump(mode="json"),
                        "component": "candidate_entity_hashes",
                        "max_transactions": max_transactions,
                        "candidate_entity_hashes": approved_candidates,
                        "requester": requester.stable_key,
                        "rho": 0.0,
                    },
                    privacy_unit=PrivacyUnit.NONE,
                    rho_debited=0.0,
                    sigma_applied=None,
                    sensitivity=1.0,
                    returned_value_kind=ResponseValueKind.HASH_LIST,
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
        # name_hashes is capped at MAX_HASH_LIST_LENGTH=100 upstream by
        # flow_histogram's _require_non_empty call, well under SQLite's
        # SQLITE_LIMIT_VARIABLE_NUMBER (default 999).
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
            SELECT
                t.transaction_id,
                t.counterparty_account_id_hashed,
                t.amount
            FROM transactions t
            WHERE t.timestamp >= ?
              AND t.timestamp < ?
            ORDER BY t.transaction_id
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
        rho_remaining: float | None = None,
        eps_delta: tuple[float, float] | None = None,
        dp_composition: DpCompositionMode | None = None,
        per_bucket_rho: float | None = None,
    ) -> PrimitiveCallRecord:
        return PrimitiveCallRecord(
            field_name=field_name,
            primitive_name=primitive_name,
            args_hash=_args_hash(args),
            privacy_unit=privacy_unit,
            rho_debited=rho_debited,
            rho_remaining=rho_remaining,
            eps_delta_display=eps_delta,
            sigma_applied=sigma_applied,
            sensitivity=sensitivity,
            dp_composition=dp_composition,
            per_bucket_rho=per_bucket_rho,
            returned_value_kind=returned_value_kind,
        )

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open the bank database, yield it, and ALWAYS close it on exit.

        Python's `sqlite3.Connection.__exit__` only commits or rolls back
        the implicit transaction — it does NOT close the connection. Using
        the raw connection as a context manager would leak a file
        descriptor on every primitive call. Wrapping the connection in our
        own `@contextmanager` with a `finally: con.close()` block makes the
        close deterministic and matches the lifecycle that long-running
        A3 processes need.
        """
        if not self.db_path.exists():
            raise FileNotFoundError(f"bank database does not exist: {self.db_path}")
        con = sqlite3.connect(self.db_path)
        try:
            con.row_factory = sqlite3.Row
            yield con
        finally:
            con.close()


def _budget_refusal() -> PrimitiveResult:
    return PrimitiveResult(refusal_reason=REFUSAL_BUDGET_EXHAUSTED)


_ARGS_HASH_FLOAT_PRECISION = 9


def _args_hash(args: dict[str, object]) -> str:
    """Hash canonical JSON args for stable audit replay.

    Floats are rounded to a fixed precision before JSON serialization.
    Python's `repr(float)` has been platform-stable shortest-round-trip
    since 3.1, but rounding inputs gives an extra margin against tiny
    arithmetic drift in upstream callers (e.g., a rho computed from
    arithmetic on another platform's libm). The precision is well above
    what ledger ρ values actually use (typically 2 decimal places),
    well inside IEEE-754 double range (~15–17 significant digits).
    """
    canonical = json.dumps(
        _canonicalize_floats(args),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hash_identifier(canonical)


def _canonicalize_floats(value: object) -> object:
    """Recursively round floats so the args_hash is stable across small drift."""
    if isinstance(value, float):
        return round(value, _ARGS_HASH_FLOAT_PRECISION)
    if isinstance(value, dict):
        return {k: _canonicalize_floats(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize_floats(v) for v in value]
    return value


def _require_non_empty(values: list[str], field_name: str) -> None:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    if len(values) > MAX_HASH_LIST_LENGTH:
        raise ValueError(
            f"{field_name} must contain at most {MAX_HASH_LIST_LENGTH} entries "
            f"(got {len(values)}); SQLite IN() clauses are bounded by "
            "SQLITE_LIMIT_VARIABLE_NUMBER. Batch the query if larger sets "
            "are needed."
        )


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


def _bucket_rho_for_composition(
    *,
    composition: DpCompositionMode,
    rho: float,
    bucket_count: int,
) -> float:
    if composition == "parallel_disjoint":
        return rho
    if composition == "serial":
        return rho / bucket_count
    raise ValueError(f"unsupported DP composition mode: {composition}")


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
    # One transaction can move one counterparty between two adjacent buckets;
    # calibration above uses the resulting L2 sensitivity sqrt(2).
    distribution = [0 for _ in DEFAULT_EDGE_COUNT_BUCKETS]
    for count in counterparty_counts.values():
        for index, (lower, upper) in enumerate(DEFAULT_EDGE_COUNT_BUCKETS):
            if count >= lower and (upper is None or count <= upper):
                distribution[index] += 1
                break
    return distribution


def _nonnegative_int(value: float) -> int:
    return max(0, int(round(value)))
