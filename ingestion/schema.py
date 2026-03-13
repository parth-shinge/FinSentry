"""
FinSentry AI - Transaction Schema Definitions
==============================================

Pydantic v2 models that enforce strict validation, type coercion, and
serialization rules for every transaction that enters the system.

Models
------
Transaction
    Raw inbound transaction — accepts flexible inputs and coerces them
    into canonical types (e.g. string timestamps → ``datetime``).
TransactionBatch
    Thin wrapper around a list of ``Transaction`` objects, useful for
    bulk upload endpoints.
NormalizedTransaction
    Post-processing view with uppercased currencies, ISO country codes,
    UTC-normalized timestamps, and derived flags
    (``is_international``, ``is_large_transaction``).

Normalization Rules
-------------------
* **currency** → uppercased (``usd`` → ``USD``)
* **country codes** → uppercased 2-letter ISO 3166-1 alpha-2
* **timestamp** → timezone-aware UTC ``datetime``
* **amount** → Python ``float``
* **is_international** → ``True`` when ``origin_country != destination_country``
* **is_large_transaction** → ``True`` when ``amount`` ≥ configured threshold
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Raw Transaction — loose validation, type coercion
# ---------------------------------------------------------------------------


class Transaction(BaseModel):
    """A single raw financial transaction as received from upstream feeds.

    All fields undergo automatic type coercion so that CSV string values
    (e.g. ``"1500.00"`` for amount) are accepted without manual casting.

    Attributes:
        transaction_id:     Unique identifier for the transaction.
        account_id:         Account that originated the transaction.
        sender_entity_id:   Entity ID of the sender.
        receiver_entity_id: Entity ID of the receiver.
        amount:             Monetary value of the transaction.
        currency:           ISO 4217 currency code (e.g. ``USD``).
        timestamp:          Date/time the transaction occurred.
        origin_country:     Two-letter ISO country code of the origin.
        destination_country: Two-letter ISO country code of the destination.
        merchant_category:  Merchant category code or description.
        transaction_type:   Type of transaction (wire, ACH, card, etc.).
        channel:            Channel through which the transaction was made
                            (online, branch, ATM, mobile).
        is_international:   Whether the transaction crosses borders.
        risk_flag:          Optional pre-assigned risk label from upstream.
    """

    transaction_id: str
    account_id: str
    sender_entity_id: str
    receiver_entity_id: str
    amount: float
    currency: str
    timestamp: datetime
    origin_country: str
    destination_country: str
    merchant_category: str
    transaction_type: str
    channel: str
    is_international: bool = False
    risk_flag: Optional[str] = None

    model_config = {
        "str_strip_whitespace": True,
        "populate_by_name": True,
    }

    # -- field-level validators ----------------------------------------------

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount(cls, value: object) -> float:
        """Coerce amount to float and reject negatives."""
        try:
            amount = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Cannot convert amount to float: {value!r}") from exc
        if amount < 0:
            raise ValueError(f"Transaction amount must be non-negative, got {amount}")
        return amount

    @field_validator("currency", mode="before")
    @classmethod
    def _uppercase_currency(cls, value: str) -> str:
        """Ensure currency code is uppercased."""
        return str(value).strip().upper()

    @field_validator("origin_country", "destination_country", mode="before")
    @classmethod
    def _uppercase_country(cls, value: str) -> str:
        """Ensure country codes are uppercased (ISO 3166-1 alpha-2)."""
        code = str(value).strip().upper()
        if len(code) != 2:
            raise ValueError(
                f"Country code must be 2 characters (ISO 3166-1 alpha-2), got {code!r}"
            )
        return code

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> datetime:
        """Parse string timestamps and enforce UTC timezone."""
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            dt = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            # Fallback: try common formats
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%m/%d/%Y %H:%M:%S",
                "%Y-%m-%d",
            ):
                try:
                    dt = datetime.strptime(str(value), fmt)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"Cannot parse timestamp: {value!r}")
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    @field_validator("is_international", mode="before")
    @classmethod
    def _coerce_bool(cls, value: object) -> bool:
        """Accept string booleans from CSV (``'True'``, ``'1'``, ``'yes'``)."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        s = str(value).strip().lower()
        if s in ("true", "1", "yes", "t", "y"):
            return True
        if s in ("false", "0", "no", "f", "n", ""):
            return False
        raise ValueError(f"Cannot interpret {value!r} as boolean")


# ---------------------------------------------------------------------------
# Transaction Batch — bulk upload wrapper
# ---------------------------------------------------------------------------


class TransactionBatch(BaseModel):
    """A collection of raw transactions for bulk ingestion.

    Attributes:
        transactions: List of :class:`Transaction` objects.
        source:       Optional label describing the data source
                      (filename, API, etc.).
    """

    transactions: list[Transaction]
    source: Optional[str] = None

    @property
    def count(self) -> int:
        """Number of transactions in the batch."""
        return len(self.transactions)


# ---------------------------------------------------------------------------
# Normalized Transaction — post-processing view
# ---------------------------------------------------------------------------


class NormalizedTransaction(BaseModel):
    """A fully normalized transaction ready for downstream analysis.

    This model is derived from :class:`Transaction` after applying all
    normalization rules (uppercase currency/country, UTC timestamp, derived
    flags).

    Attributes:
        transaction_id:      Unique identifier.
        account_id:          Originating account.
        sender_entity_id:    Sender entity.
        receiver_entity_id:  Receiver entity.
        amount:              Monetary value (float).
        currency:            Uppercased ISO 4217 code.
        timestamp:           UTC-aware datetime.
        origin_country:      Uppercased 2-letter ISO code.
        destination_country: Uppercased 2-letter ISO code.
        merchant_category:   Merchant category.
        transaction_type:    Transaction type.
        channel:             Transaction channel.
        is_international:    Whether origin ≠ destination country.
        is_large_transaction: Whether amount ≥ threshold.
        risk_flag:           Optional upstream risk label.
    """

    transaction_id: str
    account_id: str
    sender_entity_id: str
    receiver_entity_id: str
    amount: float
    currency: str
    timestamp: datetime
    origin_country: str
    destination_country: str
    merchant_category: str
    transaction_type: str
    channel: str
    is_international: bool = False
    is_large_transaction: bool = False
    risk_flag: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _derive_flags(cls, values: dict) -> dict:
        """Derive ``is_international`` and ``is_large_transaction`` flags."""
        # Import threshold lazily to avoid circular import at module level
        try:
            from utils.config import settings
            threshold = settings.LARGE_TRANSACTION_THRESHOLD
        except Exception:
            threshold = 10_000.0

        origin = str(values.get("origin_country", "")).upper()
        dest = str(values.get("destination_country", "")).upper()
        values["is_international"] = origin != dest

        amount = float(values.get("amount", 0))
        values["is_large_transaction"] = amount >= threshold

        return values
