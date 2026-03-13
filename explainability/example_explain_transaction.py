#!/usr/bin/env python
"""
FinSentry AI - Example Explainability Script
=============================================

Demonstrates the end-to-end explainability pipeline:

1. Load and normalise transactions from the sample CSV.
2. Train the FraudDetector (Isolation Forest + Random Forest).
3. Score every transaction and find the most suspicious one.
4. Explain that transaction with SHAP via FraudExplainer.
5. Print global feature importance.

Usage::

    cd /path/to/FinSentry
    python explainability/example_explain_transaction.py
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

from explainability.explainer import FraudExplainer  # noqa: E402
from fraud_detection.detector import FraudDetector  # noqa: E402
from fraud_detection.models import RiskLevel  # noqa: E402
from ingestion.loader import TransactionLoader  # noqa: E402
from utils.logging import get_logger  # noqa: E402

logger = get_logger("explainability.example")


def main() -> None:
    """Run the example explainability pipeline."""
    data_file = _PROJECT_ROOT / "data" / "sample_transactions.csv"
    if not data_file.exists():
        print(f"ERROR: Sample dataset not found at {data_file}")
        sys.exit(1)

    print("=" * 70)
    print("  FinSentry AI - Explainability Example")
    print("=" * 70)
    print()

    # -- 1. Load transactions -----------------------------------------------
    loader = TransactionLoader()
    loader.load_csv(data_file)
    transactions = loader.normalized
    print(f"  Loaded {len(transactions)} normalised transactions")
    print()

    # -- 2. Train fraud detector --------------------------------------------
    print("  Training FraudDetector (IsolationForest + RandomForest)...")
    detector = FraudDetector(
        contamination=0.15,
        n_estimators=100,
        random_state=42,
    )
    detector.train(transactions)
    print(f"  Model trained with features: {detector.feature_names_}")
    print()

    # -- 3. Score all transactions and find the most suspicious one ---------
    results = detector.predict(transactions)
    top_result = max(results, key=lambda r: r.fraud_score.fraud_probability)

    high = sum(1 for r in results if r.fraud_score.risk_level == RiskLevel.HIGH)
    medium = sum(1 for r in results if r.fraud_score.risk_level == RiskLevel.MEDIUM)
    low = sum(1 for r in results if r.fraud_score.risk_level == RiskLevel.LOW)
    print("  -- Risk Distribution --")
    print(f"    HIGH   : {high}")
    print(f"    MEDIUM : {medium}")
    print(f"    LOW    : {low}")
    print()

    print("  -- Top Suspicious Transaction --")
    fs = top_result.fraud_score
    print(f"    Transaction ID    : {fs.transaction_id}")
    print(f"    Fraud Probability : {fs.fraud_probability:.4f}")
    print(f"    Anomaly Score     : {fs.anomaly_score:.4f}")
    print(f"    Risk Level        : {fs.risk_level.value}")
    print()

    # -- 4. Explain the most suspicious transaction -------------------------
    print("  Initialising FraudExplainer (SHAP TreeExplainer)...")
    explainer = FraudExplainer(detector)
    print()

    # Find the NormalizedTransaction object that matches the top result
    top_txn = next(
        t for t in transactions if t.transaction_id == top_result.transaction_id
    )
    explanation = explainer.explain_transaction(top_txn)

    print("  -- SHAP Feature Contributions --")
    print(
        f"  {'Feature':<35} {'Contribution':>12}"
    )
    print("  " + "-" * 50)
    sorted_contribs = sorted(
        explanation.feature_contributions,
        key=lambda c: abs(c.contribution_value),
        reverse=True,
    )
    for contrib in sorted_contribs:
        bar = "+" if contrib.contribution_value >= 0 else "-"
        print(
            f"  {contrib.feature_name:<35} "
            f"{contrib.contribution_value:>+12.6f}  {bar}"
        )
    print()

    # -- 5. Global feature importance ---------------------------------------
    print("  -- Global Feature Importance (Random Forest) --")
    print(
        f"  {'Feature':<35} {'Importance':>10}"
    )
    print("  " + "-" * 48)
    importance = explainer.get_feature_importance()
    for fi in sorted(importance, key=lambda x: x.contribution_value, reverse=True):
        print(f"  {fi.feature_name:<35} {fi.contribution_value:>10.6f}")
    print()

    print("=" * 70)
    print("  Explainability example complete [OK]")
    print("=" * 70)


if __name__ == "__main__":
    main()
