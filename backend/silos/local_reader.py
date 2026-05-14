"""Typed local SQLite reads for bank-owned monitoring data."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from backend import BACKEND_ROOT
from backend.agents.a1_models import SignalCandidate
from shared.enums import BankId


PROJECT_ROOT = BACKEND_ROOT.parent
DATA_ROOT = PROJECT_ROOT / "data"
SILO_ROOT = DATA_ROOT / "silos"

OrderMode = Literal["signal_id", "signal_id_desc", "severity_desc"]


class BankDataError(ValueError):
    """Raised when local bank data cannot satisfy a typed read."""


def bank_db_path(bank_id: BankId, *, silo_root: Path = SILO_ROOT) -> Path:
    """Return the SQLite path for a bank id."""
    if bank_id == BankId.FEDERATION:
        raise BankDataError("federation has no local bank database")
    return silo_root / f"{bank_id.value}.db"


def read_signal_candidates(
    bank_id: BankId,
    *,
    limit: int = 50,
    offset: int = 0,
    db_path: Path | None = None,
    order: OrderMode = "severity_desc",
) -> list[SignalCandidate]:
    """Read a deterministic batch of local suspicious-signal candidates."""
    if limit <= 0:
        raise BankDataError("limit must be positive")
    if limit > 50:
        raise BankDataError("A1 batches are capped at 50 candidates")
    if offset < 0:
        raise BankDataError("offset must be non-negative")

    rows = _fetch_candidate_rows(
        bank_id=bank_id,
        db_path=db_path or bank_db_path(bank_id),
        limit=limit,
        offset=offset,
        order=order,
    )
    return _rows_to_candidates(db_path or bank_db_path(bank_id), rows)


def read_signal_candidates_by_ids(
    bank_id: BankId,
    signal_ids: list[str],
    *,
    db_path: Path | None = None,
) -> list[SignalCandidate]:
    """Read specific local suspicious-signal candidates by signal id."""
    if not signal_ids:
        return []
    if len(signal_ids) > 50:
        raise BankDataError("A1 batches are capped at 50 candidates")

    path = db_path or bank_db_path(bank_id)
    placeholders = ",".join("?" for _ in signal_ids)
    query = f"""
        SELECT
            s.signal_id,
            s.signal_type AS source_signal_type,
            s.severity AS source_severity,
            t.transaction_id,
            t.amount,
            t.transaction_type,
            t.channel,
            t.timestamp,
            t.account_id,
            t.counterparty_account_id_hashed,
            c.name_hash AS customer_name_hash,
            c.kyc_tier AS customer_kyc_tier
        FROM suspicious_signals s
        JOIN transactions t ON s.transaction_id = t.transaction_id
        JOIN accounts a ON t.account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
        WHERE s.signal_id IN ({placeholders})
        ORDER BY s.signal_id
    """
    with _connect(path) as con:
        rows = con.execute(query, signal_ids).fetchall()
    return _rows_to_candidates(path, rows)


def _fetch_candidate_rows(
    *,
    bank_id: BankId,
    db_path: Path,
    limit: int,
    offset: int,
    order: OrderMode,
) -> list[sqlite3.Row]:
    if bank_id == BankId.FEDERATION:
        raise BankDataError("federation has no local suspicious signals")

    order_sql = {
        "signal_id": "s.signal_id ASC",
        "signal_id_desc": "s.signal_id DESC",
        "severity_desc": "s.severity DESC, s.signal_id DESC",
    }[order]
    query = f"""
        SELECT
            s.signal_id,
            s.signal_type AS source_signal_type,
            s.severity AS source_severity,
            t.transaction_id,
            t.amount,
            t.transaction_type,
            t.channel,
            t.timestamp,
            t.account_id,
            t.counterparty_account_id_hashed,
            c.name_hash AS customer_name_hash,
            c.kyc_tier AS customer_kyc_tier
        FROM suspicious_signals s
        JOIN transactions t ON s.transaction_id = t.transaction_id
        JOIN accounts a ON t.account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """
    with _connect(db_path) as con:
        return con.execute(query, (limit, offset)).fetchall()


def _rows_to_candidates(db_path: Path, rows: list[sqlite3.Row]) -> list[SignalCandidate]:
    """Materialize SignalCandidate objects with a single batched velocity query.

    Replaces the previous N+1 pattern (one SQL per candidate) with one
    SQL fetching every near-CTR transaction across the candidate accounts,
    then a Python-side counting pass per candidate's 24h window.
    """
    if not rows:
        return []

    parsed_rows: list[tuple[sqlite3.Row, datetime]] = [
        (row, _parse_timestamp(str(row["timestamp"]))) for row in rows
    ]
    account_ids = sorted({str(row["account_id"]) for row, _ in parsed_rows})
    velocity_by_account = _near_ctr_timestamps_by_account(db_path, account_ids)

    candidates: list[SignalCandidate] = []
    for row, timestamp in parsed_rows:
        account_id = str(row["account_id"])
        window_start = timestamp - timedelta(hours=24)
        recent_count = sum(
            1
            for ts in velocity_by_account.get(account_id, ())
            if window_start <= ts <= timestamp
        )
        candidates.append(
            SignalCandidate(
                signal_id=str(row["signal_id"]),
                transaction_id=str(row["transaction_id"]),
                amount=float(row["amount"]),
                transaction_type=str(row["transaction_type"]),
                channel=str(row["channel"]),
                timestamp=timestamp,
                account_id=account_id,
                customer_name_hash=str(row["customer_name_hash"]),
                customer_kyc_tier=str(row["customer_kyc_tier"]),
                recent_near_ctr_count_24h=recent_count,
                counterparty_account_id_hashed=str(row["counterparty_account_id_hashed"]),
                source_signal_type=str(row["source_signal_type"]),
                source_severity=float(row["source_severity"]),
            )
        )
    return candidates


def _near_ctr_timestamps_by_account(
    db_path: Path,
    account_ids: list[str],
) -> dict[str, list[datetime]]:
    """Fetch all near-CTR transaction timestamps for a set of accounts in one SQL."""
    if not account_ids:
        return {}
    placeholders = ",".join("?" for _ in account_ids)
    query = f"""
        SELECT account_id, timestamp
        FROM transactions
        WHERE account_id IN ({placeholders})
          AND amount >= 9000.0
          AND amount < 10000.0
    """
    by_account: dict[str, list[datetime]] = {acct: [] for acct in account_ids}
    with _connect(db_path) as con:
        for row in con.execute(query, account_ids).fetchall():
            account_id = str(row["account_id"])
            by_account[account_id].append(_parse_timestamp(str(row["timestamp"])))
    return by_account


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise BankDataError(f"bank database does not exist: {db_path}")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise BankDataError(f"invalid transaction timestamp: {value}") from exc
