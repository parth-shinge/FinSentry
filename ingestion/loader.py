"""
FinSentry - Transaction Loader
==================================

Production-grade ingestion pipeline that loads financial transaction data
from CSV or JSON files, validates each record against the Pydantic schema,
normalizes fields, and persists them to PostgreSQL in configurable batches.

Workflow
--------
1. **Load** — Read raw rows from CSV (``load_csv``) or JSON (``load_json``).
2. **Validate** — Parse each row through :class:`~ingestion.schema.Transaction`.
   Invalid rows are collected separately with error details.
3. **Normalize** — Convert validated transactions into
   :class:`~ingestion.schema.NormalizedTransaction` (uppercase currency,
   ISO country codes, UTC timestamps, derived flags).
4. **Persist** — Batch-insert :class:`~ingestion.db.TransactionRecord` rows
   into PostgreSQL with configurable batch size.

Usage::

    from ingestion.loader import TransactionLoader

    loader = TransactionLoader()
    loader.load_csv("data/sample_transactions.csv")
    summary = loader.save_to_database()
    print(summary)
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ingestion.db import TransactionRecord, get_session, init_db
from ingestion.schema import NormalizedTransaction, Transaction
from utils.config import settings
from utils.logging import get_logger

logger = get_logger("ingestion.loader")


# ---------------------------------------------------------------------------
# Ingestion Summary — returned after a complete pipeline run
# ---------------------------------------------------------------------------


@dataclass
class IngestionSummary:
    """Statistics produced after an ingestion run.

    Attributes:
        total_rows:         Number of raw rows read from the source file.
        valid_count:        Number of rows that passed schema validation.
        invalid_count:      Number of rows that failed validation.
        normalized_count:   Number of rows after normalization.
        persisted_count:    Number of rows successfully written to the DB.
        international_count: Number of cross-border transactions.
        large_txn_count:    Number of transactions above the large threshold.
        errors:             List of ``(row_index, error_message)`` tuples.
    """

    total_rows: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    normalized_count: int = 0
    persisted_count: int = 0
    international_count: int = 0
    large_txn_count: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"IngestionSummary(\n"
            f"  total_rows={self.total_rows},\n"
            f"  valid={self.valid_count},\n"
            f"  invalid={self.invalid_count},\n"
            f"  normalized={self.normalized_count},\n"
            f"  persisted={self.persisted_count},\n"
            f"  international={self.international_count},\n"
            f"  large_transactions={self.large_txn_count},\n"
            f"  error_count={len(self.errors)}\n"
            f")"
        )


# ---------------------------------------------------------------------------
# TransactionLoader
# ---------------------------------------------------------------------------


class TransactionLoader:
    """End-to-end transaction ingestion engine.

    The loader maintains internal state across the load → validate →
    normalize → persist lifecycle so that callers can inspect intermediate
    results or skip stages selectively.

    Args:
        batch_size: Number of records per database batch insert.
                    Defaults to ``settings.BATCH_SIZE``.

    Example::

        loader = TransactionLoader()
        loader.load_csv("data/sample_transactions.csv")
        summary = loader.save_to_database()
        print(summary)
    """

    def __init__(self, batch_size: int | None = None) -> None:
        self.batch_size = batch_size or settings.BATCH_SIZE
        self._raw_rows: list[dict[str, Any]] = []
        self._validated: list[Transaction] = []
        self._normalized: list[NormalizedTransaction] = []
        self._errors: list[tuple[int, str]] = []

    # -- public properties ---------------------------------------------------

    @property
    def raw_rows(self) -> list[dict[str, Any]]:
        """Raw dictionaries read from the source file."""
        return self._raw_rows

    @property
    def validated(self) -> list[Transaction]:
        """Transactions that passed Pydantic validation."""
        return self._validated

    @property
    def normalized(self) -> list[NormalizedTransaction]:
        """Fully normalized transactions ready for DB insertion."""
        return self._normalized

    @property
    def errors(self) -> list[tuple[int, str]]:
        """Validation errors as ``(row_index, message)`` pairs."""
        return self._errors

    # -- 1. Load -------------------------------------------------------------

    def load_csv(self, filepath: str | Path) -> list[dict[str, Any]]:
        """Read transactions from a CSV file.

        Each row is returned as a dictionary keyed by column headers.
        After loading, the data is automatically validated and normalized.

        Args:
            filepath: Path to a CSV file with a header row.

        Returns:
            List of raw row dictionaries.

        Raises:
            FileNotFoundError: If *filepath* does not exist.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        logger.info("Loading CSV file: %s", filepath)

        with open(filepath, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            self._raw_rows = [row for row in reader]

        logger.info("Read %d rows from %s", len(self._raw_rows), filepath.name)
        self.validate_transactions()
        self.normalize_transactions()
        return self._raw_rows

    def load_json(self, filepath: str | Path) -> list[dict[str, Any]]:
        """Read transactions from a JSON file.

        The JSON file must contain either:
        * A top-level **array** of transaction objects, or
        * A top-level object with a ``"transactions"`` key.

        After loading, the data is automatically validated and normalized.

        Args:
            filepath: Path to a JSON file.

        Returns:
            List of raw row dictionaries.

        Raises:
            FileNotFoundError: If *filepath* does not exist.
            ValueError: If the JSON structure is unrecognised.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"JSON file not found: {filepath}")

        logger.info("Loading JSON file: %s", filepath)

        with open(filepath, encoding="utf-8") as fh:
            data = json.load(fh)

        if isinstance(data, list):
            self._raw_rows = data
        elif isinstance(data, dict) and "transactions" in data:
            self._raw_rows = data["transactions"]
        else:
            raise ValueError(
                "JSON must be a list of transactions or an object with a "
                "'transactions' key."
            )

        logger.info("Read %d rows from %s", len(self._raw_rows), filepath.name)
        self.validate_transactions()
        self.normalize_transactions()
        return self._raw_rows

    # -- 2. Validate ---------------------------------------------------------

    def validate_transactions(self) -> list[Transaction]:
        """Validate raw rows against the :class:`Transaction` Pydantic model.

        Valid transactions are stored in :attr:`validated`; failures are
        recorded in :attr:`errors` with the row index and error message.

        Returns:
            List of successfully validated :class:`Transaction` instances.
        """
        self._validated = []
        self._errors = []

        for idx, row in enumerate(self._raw_rows):
            try:
                txn = Transaction(**row)
                self._validated.append(txn)
            except (ValidationError, ValueError, TypeError) as exc:
                error_msg = str(exc)
                self._errors.append((idx, error_msg))
                logger.warning("Validation error at row %d: %s", idx, error_msg)

        logger.info(
            "Validation complete: %d valid, %d invalid out of %d rows",
            len(self._validated),
            len(self._errors),
            len(self._raw_rows),
        )
        return self._validated

    # -- 3. Normalize --------------------------------------------------------

    def normalize_transactions(self) -> list[NormalizedTransaction]:
        """Convert validated transactions into normalized form.

        Applies:
        * Currency uppercasing
        * Country code uppercasing
        * UTC timestamp enforcement
        * ``is_international`` & ``is_large_transaction`` flag derivation

        Returns:
            List of :class:`NormalizedTransaction` instances.
        """
        self._normalized = []

        for txn in self._validated:
            normalized = NormalizedTransaction(
                transaction_id=txn.transaction_id,
                account_id=txn.account_id,
                sender_entity_id=txn.sender_entity_id,
                receiver_entity_id=txn.receiver_entity_id,
                amount=txn.amount,
                currency=txn.currency.upper(),
                timestamp=txn.timestamp,
                origin_country=txn.origin_country.upper(),
                destination_country=txn.destination_country.upper(),
                merchant_category=txn.merchant_category,
                transaction_type=txn.transaction_type,
                channel=txn.channel,
                risk_flag=txn.risk_flag,
            )
            self._normalized.append(normalized)

        logger.info("Normalized %d transactions", len(self._normalized))
        return self._normalized

    # -- 4. Persist ----------------------------------------------------------

    def save_to_database(self, engine=None) -> IngestionSummary:
        """Persist normalized transactions to PostgreSQL in batches.

        Automatically initializes the database tables if they do not
        exist.  Records are inserted in batches of :attr:`batch_size` to
        control memory pressure and transaction scope.

        Args:
            engine: Optional SQLAlchemy engine override (useful for
                    testing with an in-memory SQLite database).

        Returns:
            An :class:`IngestionSummary` with statistics from the run.
        """
        init_db(engine)

        persisted = 0
        total = len(self._normalized)

        logger.info(
            "Persisting %d normalized transactions (batch_size=%d)",
            total,
            self.batch_size,
        )

        # Process in batches
        for batch_start in range(0, total, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total)
            batch = self._normalized[batch_start:batch_end]

            records = [
                TransactionRecord(
                    transaction_id=txn.transaction_id,
                    account_id=txn.account_id,
                    sender_entity_id=txn.sender_entity_id,
                    receiver_entity_id=txn.receiver_entity_id,
                    amount=txn.amount,
                    currency=txn.currency,
                    timestamp=txn.timestamp,
                    origin_country=txn.origin_country,
                    destination_country=txn.destination_country,
                    merchant_category=txn.merchant_category,
                    transaction_type=txn.transaction_type,
                    channel=txn.channel,
                    is_international=txn.is_international,
                    risk_flag=txn.risk_flag,
                )
                for txn in batch
            ]

            try:
                with get_session(engine) as session:
                    session.add_all(records)
                persisted += len(records)
                logger.info(
                    "Batch [%d–%d] inserted (%d records)",
                    batch_start,
                    batch_end - 1,
                    len(records),
                )
            except Exception as exc:
                logger.error(
                    "Failed to insert batch [%d–%d]: %s",
                    batch_start,
                    batch_end - 1,
                    exc,
                )

        # Build summary
        summary = IngestionSummary(
            total_rows=len(self._raw_rows),
            valid_count=len(self._validated),
            invalid_count=len(self._errors),
            normalized_count=len(self._normalized),
            persisted_count=persisted,
            international_count=sum(
                1 for t in self._normalized if t.is_international
            ),
            large_txn_count=sum(
                1 for t in self._normalized if t.is_large_transaction
            ),
            errors=list(self._errors),
        )

        logger.info("Ingestion complete: %s", summary)
        return summary
