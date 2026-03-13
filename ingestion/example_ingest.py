#!/usr/bin/env python
"""
FinSentry AI - Example Ingestion Script
=========================================

Demonstrates the end-to-end ingestion pipeline:

1. Load ``data/sample_transactions.csv``
2. Validate against the Pydantic schema
3. Normalize all fields (currency, countries, timestamps, flags)
4. Persist to the database (uses in-memory SQLite by default)
5. Print an ingestion summary

Usage::

    cd d:\\FinSentry
    python ingestion/example_ingest.py

.. note::

   By default this script uses an **in-memory SQLite** database so it
   runs without any external dependencies.  Set the ``DATABASE_URL``
   environment variable (or update ``.env``) to use PostgreSQL instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import create_engine

from ingestion.db import Base, TransactionRecord, get_session, reset_engine
from ingestion.loader import TransactionLoader
from utils.config import settings
from utils.logging import get_logger

logger = get_logger("ingestion.example")


def main() -> None:
    """Run the example ingestion pipeline."""
    # -- 1. Resolve data path ----------------------------------------------
    data_file = _PROJECT_ROOT / "data" / "sample_transactions.csv"
    if not data_file.exists():
        logger.error("Sample dataset not found at %s", data_file)
        print(f"ERROR: Sample dataset not found at {data_file}")
        sys.exit(1)

    print("=" * 65)
    print("  FinSentry AI - Example Transaction Ingestion")
    print("=" * 65)
    print()

    # -- 2. Set up database (SQLite in-memory for demo) --------------------
    #    To use PostgreSQL, comment out the next 3 lines and ensure
    #    DATABASE_URL is set in .env
    reset_engine()
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    print(f"  Database    : in-memory SQLite (demo mode)")
    print(f"  Data source : {data_file}")
    print()

    # -- 3. Load & validate & normalize ------------------------------------
    loader = TransactionLoader(batch_size=25)
    loader.load_csv(data_file)

    print(f"  Raw rows read       : {len(loader.raw_rows)}")
    print(f"  Validated OK        : {len(loader.validated)}")
    print(f"  Validation errors   : {len(loader.errors)}")
    print(f"  Normalized          : {len(loader.normalized)}")
    print()

    # Print first 5 normalized transactions as a preview
    print("  -- Preview (first 5 normalized transactions) --")
    for i, txn in enumerate(loader.normalized[:5]):
        print(
            f"    [{i+1}] {txn.transaction_id}  "
            f"{txn.amount:>12,.2f} {txn.currency}  "
            f"{txn.origin_country}->{txn.destination_country}  "
            f"{'INTL' if txn.is_international else 'DOM ':>4}  "
            f"{'LARGE' if txn.is_large_transaction else '     '}"
        )
    print()

    # -- 4. Persist to database --------------------------------------------
    summary = loader.save_to_database(engine=engine)

    print("  -- Ingestion Summary --")
    print(f"    Total rows          : {summary.total_rows}")
    print(f"    Valid               : {summary.valid_count}")
    print(f"    Invalid             : {summary.invalid_count}")
    print(f"    Normalized          : {summary.normalized_count}")
    print(f"    Persisted to DB     : {summary.persisted_count}")
    print(f"    International txns  : {summary.international_count}")
    print(f"    Large txns (>= ${settings.LARGE_TRANSACTION_THRESHOLD:,.0f}): {summary.large_txn_count}")
    print()

    # -- 5. Verify by querying the database --------------------------------
    with get_session(engine) as session:
        total_in_db = session.query(TransactionRecord).count()
        intl_in_db = (
            session.query(TransactionRecord)
            .filter(TransactionRecord.is_international == True)  # noqa: E712
            .count()
        )
    print("  -- Database Verification --")
    print(f"    Records in DB       : {total_in_db}")
    print(f"    International in DB : {intl_in_db}")
    print()

    # -- 6. Report any validation errors -----------------------------------
    if summary.errors:
        print("  -- Validation Errors --")
        for row_idx, msg in summary.errors[:10]:
            print(f"    Row {row_idx}: {msg[:120]}")
        if len(summary.errors) > 10:
            print(f"    ... and {len(summary.errors) - 10} more")
        print()

    print("=" * 65)
    print("  Ingestion complete [OK]")
    print("=" * 65)


if __name__ == "__main__":
    main()
