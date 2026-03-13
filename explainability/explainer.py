"""
FinSentry AI - Fraud Explainability Engine
==========================================

Uses SHAP ``TreeExplainer`` to produce per-feature contribution scores
for predictions made by :class:`~fraud_detection.detector.FraudDetector`.

Classes
-------
FraudExplainer
    Wraps a trained :class:`~fraud_detection.detector.FraudDetector` and
    exposes SHAP-based explanations for individual transactions as well as
    global feature importance.

Usage::

    from fraud_detection.detector import FraudDetector
    from explainability.explainer import FraudExplainer

    detector = FraudDetector()
    detector.train(transactions)

    explainer = FraudExplainer(detector)
    explanation = explainer.explain_transaction(transaction)
    importance = explainer.get_feature_importance()
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import shap

from explainability.models import Explanation, FeatureContribution
from fraud_detection.detector import FraudDetector
from fraud_detection.features import build_feature_matrix
from ingestion.schema import NormalizedTransaction
from utils.logging import get_logger

logger = get_logger("explainability.explainer")


class FraudExplainer:
    """SHAP-based explainability wrapper for :class:`FraudDetector`.

    Initialises a ``shap.TreeExplainer`` from the Random Forest
    classifier inside the supplied (trained) detector and provides
    methods to explain individual transactions and retrieve global
    feature importance.

    Args:
        detector: A trained :class:`~fraud_detection.detector.FraudDetector`
                  instance.  ``detector.is_trained`` must be ``True``.

    Raises:
        RuntimeError: If *detector* has not been trained yet.

    Attributes:
        feature_names_: Ordered list of feature column names (mirrors
                        ``detector.feature_names_``).
    """

    def __init__(self, detector: FraudDetector) -> None:
        if not detector.is_trained:
            raise RuntimeError(
                "FraudDetector has not been trained yet. Call train() first."
            )
        self._detector = detector
        self.feature_names_: list[str] = list(detector.feature_names_)

        # Build the SHAP TreeExplainer from the RF classifier
        self._shap_explainer = shap.TreeExplainer(
            detector._rf_classifier,
            feature_perturbation="tree_path_dependent",
        )

        # Pre-compute the base value for the fraud class so that tests
        # can verify the SHAP additivity property.
        self._fraud_class_idx: int = list(
            detector._rf_classifier.classes_
        ).index(1)
        raw_ev = self._shap_explainer.expected_value
        if isinstance(raw_ev, (list, np.ndarray)):
            self._base_value: float = float(raw_ev[self._fraud_class_idx])
        else:
            self._base_value = float(raw_ev)

        logger.info(
            "FraudExplainer initialised with %d features (base value=%.4f)",
            len(self.feature_names_),
            self._base_value,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def explain_transaction(
        self,
        transaction: NormalizedTransaction,
    ) -> Explanation:
        """Explain the fraud prediction for a single transaction.

        Builds the feature vector for *transaction*, runs the SHAP
        ``TreeExplainer``, and returns a structured :class:`Explanation`
        containing per-feature SHAP contribution scores.

        Args:
            transaction: A normalised transaction to explain.

        Returns:
            An :class:`~explainability.models.Explanation` with the
            anomaly score and one
            :class:`~explainability.models.FeatureContribution` per
            feature.
        """
        X_raw, _ = build_feature_matrix([transaction])
        X_scaled = self._detector._scaler.transform(X_raw)

        # SHAP values: list of arrays for each class in binary RF
        shap_values = self._shap_explainer.shap_values(X_scaled)
        sv = self._extract_fraud_shap_values(shap_values, row=0)

        # Isolation Forest anomaly score (lower = more anomalous).
        # Rounded to 4 d.p. to match FraudDetector.predict() precision.
        anomaly_score = float(
            self._detector._iso_forest.decision_function(X_scaled)[0]
        )

        contributions = [
            FeatureContribution(
                feature_name=name,
                contribution_value=float(val),
            )
            for name, val in zip(self.feature_names_, sv)
        ]

        logger.info(
            "Explained transaction %s (anomaly_score=%.4f, %d contributions)",
            transaction.transaction_id,
            anomaly_score,
            len(contributions),
        )
        return Explanation(
            transaction_id=transaction.transaction_id,
            anomaly_score=round(anomaly_score, 4),
            feature_contributions=contributions,
        )

    def get_feature_importance(self) -> list[FeatureContribution]:
        """Return global feature importance from the Random Forest.

        Uses the mean Gini impurity decrease (``feature_importances_``)
        stored in the trained Random Forest classifier.  Values are
        normalised so they sum to 1.

        Returns:
            A list of :class:`~explainability.models.FeatureContribution`
            objects ordered to match :attr:`feature_names_`, with
            ``contribution_value`` equal to the normalised importance.
        """
        importances: np.ndarray = (
            self._detector._rf_classifier.feature_importances_
        )
        return [
            FeatureContribution(
                feature_name=name,
                contribution_value=float(imp),
            )
            for name, imp in zip(self.feature_names_, importances)
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_fraud_shap_values(
        self,
        shap_values: list[np.ndarray] | np.ndarray,
        row: int = 0,
    ) -> np.ndarray:
        """Extract the SHAP values for the fraud class from *shap_values*.

        SHAP returns different shapes depending on the version and
        the number of classes:

        * Older SHAP / binary RF: ``list[ndarray]`` of length 2, each
          ``(n_samples, n_features)``.
        * Newer SHAP / binary RF 2-D: ``ndarray`` of shape
          ``(n_samples, n_features)``.
        * Newer SHAP / binary RF 3-D: ``ndarray`` of shape
          ``(n_samples, n_features, n_classes)``.

        Args:
            shap_values: Raw output of ``TreeExplainer.shap_values()``.
            row:         Row index to extract (default 0).

        Returns:
            1-D ``ndarray`` of shape ``(n_features,)``.
        """
        sv = np.asarray(shap_values)
        if sv.ndim == 3:
            # (n_samples, n_features, n_classes)
            return sv[row, :, self._fraud_class_idx]
        if sv.ndim == 2:
            # (n_samples, n_features) — single class or already selected
            return sv[row]
        # list-of-arrays from older SHAP: index by class first
        return np.asarray(shap_values[self._fraud_class_idx][row])
