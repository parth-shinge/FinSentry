"""
FinSentry AI - Feature Engineering
====================================

Extracts numerical features from normalised transactions and builds
feature matrices suitable for scikit-learn models.

Feature Catalogue
-----------------

=================================  ========================================
Feature                            Description
=================================  ========================================
``amount``                         Raw monetary value.
``transaction_hour``               Hour-of-day (0-23) from timestamp.
``is_international``               1 if cross-border, else 0.
``is_large_transaction``           1 if amount >= threshold, else 0.
``country_risk_score``             Risk weight for destination country.
``amount_zscore``                  Z-score of amount within the batch.
``account_transaction_frequency``  Number of transactions per account.
``time_since_last_transaction``    Seconds since the account's previous txn.
=================================  ========================================

Usage::

    from fraud_detection.features import build_feature_matrix
    from ingestion.schema import NormalizedTransaction

    matrix, feature_names = build_feature_matrix(transactions)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

import numpy as np

from ingestion.schema import NormalizedTransaction
from utils.logging import get_logger

logger = get_logger("fraud_detection.features")

# ---------------------------------------------------------------------------
# Country risk scoring
# ---------------------------------------------------------------------------

#: ISO-2 country code -> risk weight.  Higher = riskier.
#: Countries not listed default to 0.1 (low risk).
COUNTRY_RISK_SCORES: dict[str, float] = {
    # High-risk jurisdictions (offshore financial centres, FATF grey-list)
    "KY": 0.9,   # Cayman Islands
    "PA": 0.9,   # Panama
    "BS": 0.85,  # Bahamas
    "JE": 0.8,   # Jersey
    "GG": 0.8,   # Guernsey
    "IM": 0.8,   # Isle of Man
    "AE": 0.75,  # UAE
    "HK": 0.7,   # Hong Kong
    "SG": 0.6,   # Singapore
    "CH": 0.6,   # Switzerland
    # Medium-risk
    "RU": 0.7,   # Russia
    "CN": 0.5,   # China
    "NG": 0.65,  # Nigeria
    "MX": 0.55,  # Mexico
    # Low-risk
    "US": 0.1,
    "GB": 0.1,
    "DE": 0.1,
    "FR": 0.1,
    "IT": 0.15,
    "NL": 0.1,
}

DEFAULT_COUNTRY_RISK = 0.2


def get_country_risk(country_code: str) -> float:
    """Return the risk score for an ISO-2 country code.

    Args:
        country_code: Two-letter ISO 3166-1 alpha-2 code (uppercased).

    Returns:
        Risk weight in [0, 1].
    """
    return COUNTRY_RISK_SCORES.get(country_code.upper(), DEFAULT_COUNTRY_RISK)


# ---------------------------------------------------------------------------
# Per-transaction feature extraction
# ---------------------------------------------------------------------------


def extract_features(
    transactions: Sequence[NormalizedTransaction],
) -> list[dict[str, float]]:
    """Extract a feature dictionary for every transaction.

    This function computes both per-record features (amount, hour,
    country risk) and batch-level statistics (z-score, frequency,
    time-since-last).

    Args:
        transactions: Sequence of normalised transactions.

    Returns:
        A list of ``dict[str, float]``, one per transaction, keyed by
        feature name.
    """
    if not transactions:
        return []

    # -- pre-compute batch-level statistics ---------------------------------
    amounts = np.array([t.amount for t in transactions], dtype=np.float64)
    mean_amount = float(np.mean(amounts)) if len(amounts) > 0 else 0.0
    std_amount = float(np.std(amounts)) if len(amounts) > 1 else 1.0
    if std_amount == 0:
        std_amount = 1.0  # avoid division by zero

    # Per-account: transaction count & sorted timestamps
    account_txns: dict[str, list[datetime]] = {}
    for txn in transactions:
        account_txns.setdefault(txn.account_id, []).append(txn.timestamp)
    # Sort timestamps per account for time-since-last calculation
    for acc_id in account_txns:
        account_txns[acc_id].sort()

    account_freq: dict[str, int] = {
        acc: len(ts) for acc, ts in account_txns.items()
    }

    # -- extract per-transaction features -----------------------------------
    features: list[dict[str, float]] = []

    for txn in transactions:
        hour = txn.timestamp.hour if txn.timestamp else 0
        z_score = (txn.amount - mean_amount) / std_amount

        # Time since last transaction for this account (seconds)
        acc_timestamps = account_txns.get(txn.account_id, [])
        idx = _find_index(acc_timestamps, txn.timestamp)
        if idx > 0:
            delta = (txn.timestamp - acc_timestamps[idx - 1]).total_seconds()
        else:
            delta = 0.0  # first transaction for this account

        feat = {
            "amount": txn.amount,
            "transaction_hour": float(hour),
            "is_international": 1.0 if txn.is_international else 0.0,
            "is_large_transaction": 1.0 if txn.is_large_transaction else 0.0,
            "country_risk_score": get_country_risk(txn.destination_country),
            "amount_zscore": z_score,
            "account_transaction_frequency": float(
                account_freq.get(txn.account_id, 1)
            ),
            "time_since_last_transaction": delta,
        }
        features.append(feat)

    logger.info("Extracted %d feature vectors (%d dims each)", len(features), len(features[0]))
    return features


def _find_index(sorted_timestamps: list[datetime], target: datetime) -> int:
    """Return the index of *target* in *sorted_timestamps* (linear scan)."""
    for i, ts in enumerate(sorted_timestamps):
        if ts == target:
            return i
    return 0


# ---------------------------------------------------------------------------
# Feature matrix builder
# ---------------------------------------------------------------------------

#: Canonical ordering of feature columns.
FEATURE_NAMES: list[str] = [
    "amount",
    "transaction_hour",
    "is_international",
    "is_large_transaction",
    "country_risk_score",
    "amount_zscore",
    "account_transaction_frequency",
    "time_since_last_transaction",
]


def build_feature_matrix(
    transactions: Sequence[NormalizedTransaction],
) -> tuple[np.ndarray, list[str]]:
    """Build a 2-D numpy feature matrix from normalised transactions.

    Args:
        transactions: Sequence of normalised transactions.

    Returns:
        A tuple of ``(X, feature_names)`` where ``X`` has shape
        ``(n_transactions, n_features)`` and ``feature_names`` is the
        ordered list of column names.
    """
    feature_dicts = extract_features(transactions)
    if not feature_dicts:
        return np.empty((0, len(FEATURE_NAMES)), dtype=np.float64), list(FEATURE_NAMES)

    X = np.array(
        [[fd[name] for name in FEATURE_NAMES] for fd in feature_dicts],
        dtype=np.float64,
    )
    logger.info("Built feature matrix with shape %s", X.shape)
    return X, list(FEATURE_NAMES)
