"""
FinSentry - Fraud Detector
==============================

Core fraud-detection engine that trains anomaly-detection and supervised
models on normalised transaction features, then scores new transactions.

Pipeline
--------
1. **Feature extraction** -- delegates to :mod:`fraud_detection.features`.
2. **Anomaly detection** -- Isolation Forest (unsupervised).
3. **Supervised scoring** -- Random Forest classifier trained on synthetic
   labels derived from the anomaly detector's output (bootstraps itself
   when no ground-truth labels are available).
4. **Risk classification** -- maps probability to LOW / MEDIUM / HIGH.

Explainability Hook
-------------------
After training, :attr:`FraudDetector.feature_names_` exposes the ordered
list of feature columns so that downstream explainability modules (SHAP,
LIME) can align their explanations.

Usage::

    from fraud_detection.detector import FraudDetector

    detector = FraudDetector()
    detector.train(normalized_transactions)
    results = detector.predict(normalized_transactions)
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from fraud_detection.features import FEATURE_NAMES, build_feature_matrix
from fraud_detection.models import DetectionResult, FraudScore, RiskLevel
from ingestion.schema import NormalizedTransaction
from utils.config import settings
from utils.logging import get_logger

logger = get_logger("fraud_detection.detector")


class FraudDetector:
    """End-to-end fraud detection engine.

    Combines an **Isolation Forest** for unsupervised anomaly detection
    with a **Random Forest** classifier for calibrated probability
    scoring.

    Args:
        contamination: Expected proportion of anomalies in the dataset
                       (passed to ``IsolationForest``).  Default 0.1.
        n_estimators:  Number of trees in each forest.  Default 100.
        random_state:  Seed for reproducibility.  Default 42.

    Attributes:
        feature_names_: List of feature column names after training.
                        Used by the explainability module.
        is_trained:     Whether :meth:`train` has been called.
    """

    def __init__(
        self,
        contamination: float = 0.1,
        n_estimators: int = 100,
        random_state: int = 42,
    ) -> None:
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state

        # Models (initialised at train time)
        self._iso_forest: Optional[IsolationForest] = None
        self._rf_classifier: Optional[RandomForestClassifier] = None
        self._scaler: Optional[StandardScaler] = None

        # Metadata
        self.feature_names_: list[str] = []
        self.is_trained: bool = False

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        transactions: Sequence[NormalizedTransaction],
        labels: Optional[np.ndarray] = None,
    ) -> None:
        """Train the anomaly detector and supervised classifier.

        If *labels* are not provided, synthetic labels are generated from
        the Isolation Forest predictions (self-supervised bootstrap).

        Args:
            transactions: Normalised transactions to train on.
            labels:       Optional binary labels (1 = fraud, 0 = legit).
                          Shape ``(n_transactions,)``.

        Raises:
            ValueError: If fewer than 5 transactions are supplied.
        """
        if len(transactions) < 5:
            raise ValueError(
                f"Need at least 5 transactions to train, got {len(transactions)}"
            )

        # 1. Build feature matrix
        X_raw, self.feature_names_ = build_feature_matrix(transactions)

        # 2. Scale features
        self._scaler = StandardScaler()
        X = self._scaler.fit_transform(X_raw)

        # 3. Train Isolation Forest (unsupervised)
        self._iso_forest = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self._iso_forest.fit(X)
        logger.info(
            "Isolation Forest trained on %d samples (%d features)",
            X.shape[0],
            X.shape[1],
        )

        # 4. Generate synthetic labels if none provided
        if labels is None:
            iso_preds = self._iso_forest.predict(X)
            # IsolationForest: -1 = anomaly, 1 = normal
            labels = (iso_preds == -1).astype(int)
            logger.info(
                "Generated synthetic labels: %d fraud, %d legit",
                int(labels.sum()),
                int((labels == 0).sum()),
            )

        # 5. Train Random Forest classifier for calibrated probabilities
        self._rf_classifier = RandomForestClassifier(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            class_weight="balanced",
            n_jobs=-1,
        )
        self._rf_classifier.fit(X, labels)
        logger.info("Random Forest classifier trained")

        self.is_trained = True

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(
        self,
        transactions: Sequence[NormalizedTransaction],
    ) -> list[DetectionResult]:
        """Score transactions and return structured detection results.

        Args:
            transactions: Normalised transactions to evaluate.

        Returns:
            A list of :class:`DetectionResult`, one per transaction.

        Raises:
            RuntimeError: If the model has not been trained yet.
        """
        self._ensure_trained()

        X_raw, _ = build_feature_matrix(transactions)
        X = self._scaler.transform(X_raw)

        # Isolation Forest anomaly scores (lower = more anomalous)
        anomaly_scores = self._iso_forest.decision_function(X)

        # Random Forest fraud probabilities
        fraud_probs = self._rf_classifier.predict_proba(X)
        # Column index for the fraud class (label=1)
        fraud_col = list(self._rf_classifier.classes_).index(1)

        results: list[DetectionResult] = []
        for i, txn in enumerate(transactions):
            prob = float(fraud_probs[i, fraud_col])
            risk = FraudScore.classify_risk(prob)

            score = FraudScore(
                transaction_id=txn.transaction_id,
                fraud_probability=float(round(prob, 4)),
                anomaly_score=float(round(float(anomaly_scores[i]), 4)),
                risk_level=risk,
            )
            result = DetectionResult(
                transaction_id=txn.transaction_id,
                features_used=list(self.feature_names_),
                fraud_score=score,
            )
            results.append(result)

        logger.info(
            "Scored %d transactions: %d HIGH, %d MEDIUM, %d LOW",
            len(results),
            sum(1 for r in results if r.fraud_score.risk_level == RiskLevel.HIGH),
            sum(1 for r in results if r.fraud_score.risk_level == RiskLevel.MEDIUM),
            sum(1 for r in results if r.fraud_score.risk_level == RiskLevel.LOW),
        )
        return results

    def score(
        self,
        transactions: Sequence[NormalizedTransaction],
    ) -> list[FraudScore]:
        """Convenience method returning only :class:`FraudScore` objects.

        Args:
            transactions: Normalised transactions.

        Returns:
            A list of :class:`FraudScore` instances.
        """
        return [r.fraud_score for r in self.predict(transactions)]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Persist the trained model to disk.

        Args:
            path: File path for the pickled model bundle.
        """
        self._ensure_trained()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        bundle = {
            "iso_forest": self._iso_forest,
            "rf_classifier": self._rf_classifier,
            "scaler": self._scaler,
            "feature_names": self.feature_names_,
            "contamination": self.contamination,
            "n_estimators": self.n_estimators,
            "random_state": self.random_state,
        }
        with open(path, "wb") as fh:
            pickle.dump(bundle, fh)
        logger.info("Model saved to %s", path)

    def load(self, path: str | Path) -> None:
        """Load a previously saved model from disk.

        Args:
            path: File path to the pickled model bundle.

        Raises:
            FileNotFoundError: If *path* does not exist.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        with open(path, "rb") as fh:
            bundle = pickle.load(fh)
        self._iso_forest = bundle["iso_forest"]
        self._rf_classifier = bundle["rf_classifier"]
        self._scaler = bundle["scaler"]
        self.feature_names_ = bundle["feature_names"]
        self.contamination = bundle["contamination"]
        self.n_estimators = bundle["n_estimators"]
        self.random_state = bundle["random_state"]
        self.is_trained = True
        logger.info("Model loaded from %s", path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_trained(self) -> None:
        """Raise if predict/score is called before training."""
        if not self.is_trained:
            raise RuntimeError(
                "FraudDetector has not been trained yet. Call train() first."
            )
