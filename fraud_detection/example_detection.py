#!/usr/bin/env python
"""
FinSentry AI - Example Fraud Detection Script
===============================================

Demonstrates the end-to-end fraud detection pipeline:

1. Load and normalise transactions from the sample CSV.
2. Train the FraudDetector (Isolation Forest + Random Forest).
3. Score every transaction.
4. Print the top suspicious transactions ranked by fraud probability.

Usage::

    cd d:\\FinSentry
    python fraud_detection/example_detection.py
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

from utils.project_path import PROJECT_ROOT  # noqa: E402
from fraud_detection.detector import FraudDetector  # noqa: E402
from fraud_detection.models import RiskLevel  # noqa: E402
from ingestion.loader import TransactionLoader  # noqa: E402
from utils.logging import get_logger  # noqa: E402

logger = get_logger("fraud_detection.example")


def main() -> None:
    """Run the example fraud detection pipeline."""
    # -- 1. Load transactions via the ingestion layer ----------------------
    data_file = _PROJECT_ROOT / "data" / "sample_transactions.csv"
    if not data_file.exists():
        print(f"ERROR: Sample dataset not found at {data_file}")
        sys.exit(1)

    print("=" * 70)
    print("  FinSentry AI - Fraud Detection Example")
    print("=" * 70)
    print()

    loader = TransactionLoader()
    loader.load_csv(data_file)
    transactions = loader.normalized

    print(f"  Loaded {len(transactions)} normalised transactions")
    print()

    # -- 2. Train the fraud detector ---------------------------------------
    print("  Training FraudDetector (IsolationForest + RandomForest)...")
    detector = FraudDetector(
        contamination=0.15,
        n_estimators=100,
        random_state=42,
    )
    detector.train(transactions)
    print(f"  Model trained with features: {detector.feature_names_}")
    print()

    # -- 3. Score all transactions -----------------------------------------
    results = detector.predict(transactions)

    high = [r for r in results if r.fraud_score.risk_level == RiskLevel.HIGH]
    medium = [r for r in results if r.fraud_score.risk_level == RiskLevel.MEDIUM]
    low = [r for r in results if r.fraud_score.risk_level == RiskLevel.LOW]

    print("  -- Risk Distribution --")
    print(f"    HIGH   : {len(high)}")
    print(f"    MEDIUM : {len(medium)}")
    print(f"    LOW    : {len(low)}")
    print()

    # -- 4. Print top suspicious transactions ------------------------------
    sorted_results = sorted(
        results,
        key=lambda r: r.fraud_score.fraud_probability,
        reverse=True,
    )

    top_n = 10
    print(f"  -- Top {top_n} Most Suspicious Transactions --")
    print(
        f"  {'Rank':<5} {'Transaction ID':<14} {'Probability':>11} "
        f"{'Anomaly':>9} {'Risk':<8}"
    )
    print("  " + "-" * 52)

    for rank, result in enumerate(sorted_results[:top_n], start=1):
        fs = result.fraud_score
        print(
            f"  {rank:<5} {fs.transaction_id:<14} "
            f"{fs.fraud_probability:>11.4f} "
            f"{fs.anomaly_score:>9.4f} "
            f"{fs.risk_level.value:<8}"
        )

    print()

    # -- 5. Show details of the top suspicious transaction -----------------
    top = sorted_results[0]
    print("  -- Most Suspicious Transaction Details --")
    print(f"    Transaction ID     : {top.transaction_id}")
    print(f"    Fraud Probability  : {top.fraud_score.fraud_probability:.4f}")
    print(f"    Anomaly Score      : {top.fraud_score.anomaly_score:.4f}")
    print(f"    Risk Level         : {top.fraud_score.risk_level.value}")
    print(f"    Features Evaluated : {len(top.features_used)}")
    print()

    print("=" * 70)
    print("  Fraud detection complete [OK]")
    print("=" * 70)


if __name__ == "__main__":
    main()
