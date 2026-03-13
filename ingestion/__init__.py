"""
FinSentry - Transaction Ingestion Package
=============================================

Provides a production-grade pipeline for loading, validating, normalizing,
and persisting financial transaction data.

Modules:
    schema  — Pydantic validation models
    db      — SQLAlchemy ORM layer & session management
    loader  — TransactionLoader (CSV / JSON → validate → normalize → DB)
"""

from ingestion.schema import NormalizedTransaction, Transaction, TransactionBatch
from ingestion.loader import TransactionLoader

__all__ = [
    "Transaction",
    "TransactionBatch",
    "NormalizedTransaction",
    "TransactionLoader",
]
