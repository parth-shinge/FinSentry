"""
FinSentry - Ingestion Unit Tests
====================================

Tests for the transaction ingestion pipeline covering:

* CSV loading
* JSON loading
* Pydantic schema validation (valid & invalid inputs)
* Field normalization (currency, country codes, timestamps, flags)
* Database insertion via in-memory SQLite

All database tests use an **in-memory SQLite** engine so no external
PostgreSQL instance is required to run the suite.

Run::

    cd d:\\FinSentry
    python -m pytest tests/test_ingestion.py -v
"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so imports work
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ingestion.schema import NormalizedTransaction, Transaction, TransactionBatch
from ingestion.db import Base, TransactionRecord, get_session, init_db, reset_engine
from ingestion.loader import TransactionLoader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ROW: dict = {
    "transaction_id": "TXN-TEST-001",
    "account_id": "ACC-9999",
    "sender_entity_id": "ENT-S001",
    "receiver_entity_id": "ENT-R001",
    "amount": "1500.50",
    "currency": "usd",
    "timestamp": "2025-06-15 14:30:00",
    "origin_country": "us",
    "destination_country": "gb",
    "merchant_category": "electronics",
    "transaction_type": "wire",
    "channel": "online",
    "is_international": "True",
    "risk_flag": "medium",
}

SAMPLE_ROW_DOMESTIC: dict = {
    **SAMPLE_ROW,
    "transaction_id": "TXN-TEST-002",
    "destination_country": "us",
    "is_international": "False",
    "amount": "250.00",
}


@pytest.fixture()
def sqlite_engine():
    """Create a fresh in-memory SQLite engine for each test."""
    reset_engine()
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    reset_engine()


@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    """Write a minimal CSV file with two valid rows."""
    filepath = tmp_path / "test_transactions.csv"
    rows = [SAMPLE_ROW, SAMPLE_ROW_DOMESTIC]
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return filepath


@pytest.fixture()
def sample_json(tmp_path: Path) -> Path:
    """Write a minimal JSON file with two valid transactions."""
    filepath = tmp_path / "test_transactions.json"
    rows = [SAMPLE_ROW, SAMPLE_ROW_DOMESTIC]
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    return filepath


@pytest.fixture()
def sample_json_wrapped(tmp_path: Path) -> Path:
    """Write a JSON file with a ``transactions`` wrapper key."""
    filepath = tmp_path / "test_wrapped.json"
    data = {"transactions": [SAMPLE_ROW], "source": "test"}
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return filepath


# ===========================================================================
# Schema validation tests
# ===========================================================================


class TestTransactionSchema:
    """Tests for the Transaction Pydantic model."""

    def test_valid_transaction(self):
        """A valid row should parse without error."""
        txn = Transaction(**SAMPLE_ROW)
        assert txn.transaction_id == "TXN-TEST-001"
        assert txn.amount == 1500.50
        assert txn.currency == "USD"  # uppercased by validator
        assert txn.origin_country == "US"
        assert txn.destination_country == "GB"
        assert txn.is_international is True
        assert txn.risk_flag == "medium"

    def test_amount_coercion(self):
        """String amounts should be coerced to float."""
        txn = Transaction(**{**SAMPLE_ROW, "amount": "9999.99"})
        assert txn.amount == 9999.99

    def test_negative_amount_rejected(self):
        """Negative amounts should be rejected."""
        with pytest.raises(Exception):
            Transaction(**{**SAMPLE_ROW, "amount": "-100"})

    def test_invalid_country_code(self):
        """Country codes longer than 2 characters should be rejected."""
        with pytest.raises(Exception):
            Transaction(**{**SAMPLE_ROW, "origin_country": "USA"})

    def test_timestamp_parsing_iso(self):
        """ISO-format timestamps should be accepted."""
        txn = Transaction(**{**SAMPLE_ROW, "timestamp": "2025-06-15T14:30:00"})
        assert txn.timestamp.year == 2025
        assert txn.timestamp.month == 6
        assert txn.timestamp.tzinfo is not None

    def test_timestamp_parsing_date_only(self):
        """Date-only strings should be accepted."""
        txn = Transaction(**{**SAMPLE_ROW, "timestamp": "2025-06-15"})
        assert txn.timestamp.year == 2025

    def test_bool_coercion_from_string(self):
        """String booleans ('True', '1', 'yes') should be coerced."""
        for truthy in ("True", "1", "yes", "t", "y"):
            txn = Transaction(**{**SAMPLE_ROW, "is_international": truthy})
            assert txn.is_international is True

        for falsy in ("False", "0", "no", "f", "n"):
            txn = Transaction(**{**SAMPLE_ROW, "is_international": falsy})
            assert txn.is_international is False

    def test_currency_uppercased(self):
        """Currency should always be uppercased."""
        txn = Transaction(**{**SAMPLE_ROW, "currency": "eur"})
        assert txn.currency == "EUR"

    def test_missing_required_field(self):
        """Omitting a required field should raise a validation error."""
        incomplete = {k: v for k, v in SAMPLE_ROW.items() if k != "amount"}
        with pytest.raises(Exception):
            Transaction(**incomplete)

    def test_optional_risk_flag_none(self):
        """risk_flag should default to None when absent."""
        row = {k: v for k, v in SAMPLE_ROW.items() if k != "risk_flag"}
        txn = Transaction(**row)
        assert txn.risk_flag is None


class TestTransactionBatch:
    """Tests for the TransactionBatch model."""

    def test_batch_count(self):
        """Batch count property should reflect list length."""
        batch = TransactionBatch(
            transactions=[Transaction(**SAMPLE_ROW)],
            source="test",
        )
        assert batch.count == 1

    def test_empty_batch(self):
        """An empty batch should have count 0."""
        batch = TransactionBatch(transactions=[])
        assert batch.count == 0


class TestNormalizedTransaction:
    """Tests for the NormalizedTransaction model."""

    def test_international_flag_derived(self):
        """is_international should be True when countries differ."""
        norm = NormalizedTransaction(**{**SAMPLE_ROW, "amount": 500.0})
        assert norm.is_international is True  # US → GB

    def test_domestic_flag_derived(self):
        """is_international should be False when countries match."""
        norm = NormalizedTransaction(**SAMPLE_ROW_DOMESTIC)
        assert norm.is_international is False  # US → US

    def test_large_transaction_flag(self):
        """Amounts >= threshold should set is_large_transaction."""
        norm = NormalizedTransaction(**{**SAMPLE_ROW, "amount": 15000.0})
        assert norm.is_large_transaction is True

    def test_small_transaction_flag(self):
        """Amounts below threshold should not set is_large_transaction."""
        norm = NormalizedTransaction(**{**SAMPLE_ROW, "amount": 500.0})
        assert norm.is_large_transaction is False


# ===========================================================================
# CSV / JSON loading tests
# ===========================================================================


class TestCSVLoading:
    """Tests for TransactionLoader.load_csv()."""

    def test_load_csv_row_count(self, sample_csv: Path):
        """Should load the correct number of rows."""
        loader = TransactionLoader()
        rows = loader.load_csv(sample_csv)
        assert len(rows) == 2

    def test_load_csv_validates(self, sample_csv: Path):
        """All rows should pass validation after loading from CSV."""
        loader = TransactionLoader()
        loader.load_csv(sample_csv)
        assert len(loader.validated) == 2
        assert len(loader.errors) == 0

    def test_load_csv_normalizes(self, sample_csv: Path):
        """Normalized list should have the same length as validated."""
        loader = TransactionLoader()
        loader.load_csv(sample_csv)
        assert len(loader.normalized) == 2

    def test_file_not_found(self):
        """Loading a nonexistent file should raise FileNotFoundError."""
        loader = TransactionLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_csv("/nonexistent/path.csv")


class TestJSONLoading:
    """Tests for TransactionLoader.load_json()."""

    def test_load_json_array(self, sample_json: Path):
        """Should load from a top-level JSON array."""
        loader = TransactionLoader()
        rows = loader.load_json(sample_json)
        assert len(rows) == 2

    def test_load_json_wrapped(self, sample_json_wrapped: Path):
        """Should load from a JSON object with 'transactions' key."""
        loader = TransactionLoader()
        rows = loader.load_json(sample_json_wrapped)
        assert len(rows) == 1

    def test_json_file_not_found(self):
        """Loading a nonexistent JSON file should raise FileNotFoundError."""
        loader = TransactionLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_json("/nonexistent/path.json")


# ===========================================================================
# Normalization tests
# ===========================================================================


class TestNormalization:
    """Tests for the normalization step of TransactionLoader."""

    def test_currency_normalized(self, sample_csv: Path):
        """Currency should be uppercased in normalized output."""
        loader = TransactionLoader()
        loader.load_csv(sample_csv)
        for ntxn in loader.normalized:
            assert ntxn.currency == ntxn.currency.upper()

    def test_country_codes_normalized(self, sample_csv: Path):
        """Country codes should be uppercased."""
        loader = TransactionLoader()
        loader.load_csv(sample_csv)
        for ntxn in loader.normalized:
            assert ntxn.origin_country == ntxn.origin_country.upper()
            assert ntxn.destination_country == ntxn.destination_country.upper()

    def test_international_detection(self, sample_csv: Path):
        """International flag should be set when countries differ."""
        loader = TransactionLoader()
        loader.load_csv(sample_csv)
        intl = [t for t in loader.normalized if t.is_international]
        domestic = [t for t in loader.normalized if not t.is_international]
        # SAMPLE_ROW is US→GB (international), SAMPLE_ROW_DOMESTIC is US→US
        assert len(intl) == 1
        assert len(domestic) == 1

    def test_timestamp_utc(self, sample_csv: Path):
        """All normalized timestamps should be UTC-aware."""
        loader = TransactionLoader()
        loader.load_csv(sample_csv)
        for ntxn in loader.normalized:
            assert ntxn.timestamp.tzinfo is not None


# ===========================================================================
# Database insertion tests
# ===========================================================================


class TestDatabaseInsertion:
    """Tests for TransactionLoader.save_to_database() using SQLite."""

    def test_save_to_database(self, sample_csv: Path, sqlite_engine):
        """Records should be persisted to the database."""
        loader = TransactionLoader()
        loader.load_csv(sample_csv)
        summary = loader.save_to_database(engine=sqlite_engine)

        assert summary.persisted_count == 2
        assert summary.valid_count == 2
        assert summary.invalid_count == 0

        # Verify records exist in the database
        with get_session(sqlite_engine) as session:
            count = session.query(TransactionRecord).count()
            assert count == 2

    def test_save_summary_statistics(self, sample_csv: Path, sqlite_engine):
        """Summary should report correct international / large counts."""
        loader = TransactionLoader()
        loader.load_csv(sample_csv)
        summary = loader.save_to_database(engine=sqlite_engine)

        assert summary.international_count == 1  # US→GB
        assert summary.total_rows == 2

    def test_batch_insertion(self, sample_csv: Path, sqlite_engine):
        """Batch size should be respected (even with small data)."""
        loader = TransactionLoader(batch_size=1)
        loader.load_csv(sample_csv)
        summary = loader.save_to_database(engine=sqlite_engine)

        assert summary.persisted_count == 2

    def test_record_fields_persisted(self, sample_csv: Path, sqlite_engine):
        """Field values should round-trip correctly through the DB."""
        loader = TransactionLoader()
        loader.load_csv(sample_csv)
        loader.save_to_database(engine=sqlite_engine)

        with get_session(sqlite_engine) as session:
            rec = (
                session.query(TransactionRecord)
                .filter_by(transaction_id="TXN-TEST-001")
                .first()
            )
            assert rec is not None
            assert rec.amount == 1500.50
            assert rec.currency == "USD"
            assert rec.origin_country == "US"
            assert rec.destination_country == "GB"
            assert rec.is_international is True
            assert rec.risk_flag == "medium"

    def test_full_dataset(self, sqlite_engine):
        """Integration test with the sample_transactions.csv dataset."""
        data_path = _PROJECT_ROOT / "data" / "sample_transactions.csv"
        if not data_path.exists():
            pytest.skip("Sample dataset not found")

        loader = TransactionLoader()
        loader.load_csv(data_path)
        summary = loader.save_to_database(engine=sqlite_engine)

        assert summary.total_rows == 50
        assert summary.valid_count == 50
        assert summary.invalid_count == 0
        assert summary.persisted_count == 50
        assert summary.international_count > 0
        assert summary.large_txn_count > 0
