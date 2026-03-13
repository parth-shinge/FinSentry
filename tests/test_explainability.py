"""
FinSentry AI - Explainability Unit Tests
=========================================

Tests covering:

* FraudExplainer initialisation
* explain_transaction() output structure and SHAP additivity
* get_feature_importance() output structure and normalisation
* Compatibility with FraudDetector

All tests use synthetic NormalizedTransaction objects -- no database or
external data required.

Run::

    cd /path/to/FinSentry
    python -m pytest tests/test_explainability.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from explainability.explainer import FraudExplainer
from explainability.models import Explanation, FeatureContribution
from fraud_detection.detector import FraudDetector
from fraud_detection.features import FEATURE_NAMES
from ingestion.schema import NormalizedTransaction


# ---------------------------------------------------------------------------
# Helpers (mirrors test_fraud_detection.py helpers)
# ---------------------------------------------------------------------------


def _make_txn(
    txn_id: str = "TXN-001",
    account_id: str = "ACC-001",
    amount: float = 500.0,
    origin: str = "US",
    dest: str = "US",
    hour: int = 10,
    is_intl: bool = False,
    is_large: bool = False,
) -> NormalizedTransaction:
    """Create a NormalizedTransaction with sensible defaults."""
    ts = datetime(2025, 1, 15, hour, 0, 0, tzinfo=timezone.utc)
    return NormalizedTransaction(
        transaction_id=txn_id,
        account_id=account_id,
        sender_entity_id="ENT-S001",
        receiver_entity_id="ENT-R001",
        amount=amount,
        currency="USD",
        timestamp=ts,
        origin_country=origin,
        destination_country=dest,
        merchant_category="retail",
        transaction_type="wire",
        channel="online",
        is_international=is_intl,
        is_large_transaction=is_large,
        risk_flag=None,
    )


def _make_batch(n: int = 30) -> list[NormalizedTransaction]:
    """Create a batch of diverse transactions for training."""
    txns: list[NormalizedTransaction] = []
    rng = np.random.default_rng(42)
    for i in range(n):
        if i % 5 == 0:
            txns.append(
                _make_txn(
                    txn_id=f"TXN-{i:04d}",
                    account_id=f"ACC-{i % 3:03d}",
                    amount=float(rng.integers(15000, 100000)),
                    origin="US",
                    dest="KY",
                    hour=int(rng.integers(0, 6)),
                    is_intl=True,
                    is_large=True,
                )
            )
        elif i % 3 == 0:
            txns.append(
                _make_txn(
                    txn_id=f"TXN-{i:04d}",
                    account_id=f"ACC-{i % 5:03d}",
                    amount=float(rng.integers(3000, 9000)),
                    origin="US",
                    dest="MX",
                    hour=int(rng.integers(8, 18)),
                    is_intl=True,
                )
            )
        else:
            txns.append(
                _make_txn(
                    txn_id=f"TXN-{i:04d}",
                    account_id=f"ACC-{i % 7:03d}",
                    amount=float(rng.integers(10, 2000)),
                    origin="US",
                    dest="US",
                    hour=int(rng.integers(8, 20)),
                )
            )
    return txns


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(scope="module")
def trained_detector() -> FraudDetector:
    """Return a detector trained on a synthetic batch (module-scoped)."""
    detector = FraudDetector(contamination=0.15, n_estimators=50, random_state=42)
    detector.train(_make_batch(30))
    return detector


@pytest.fixture(scope="module")
def explainer(trained_detector: FraudDetector) -> FraudExplainer:
    """Return a FraudExplainer wrapping the trained detector."""
    return FraudExplainer(trained_detector)


@pytest.fixture()
def sample_transaction() -> NormalizedTransaction:
    """A single suspicious transaction for explanation tests."""
    return _make_txn(
        txn_id="TXN-SUSP",
        amount=50000.0,
        dest="KY",
        is_intl=True,
        is_large=True,
        hour=2,
    )


# ===========================================================================
# Model tests
# ===========================================================================


class TestExplainabilityModels:
    """Tests for explainability Pydantic data models."""

    def test_feature_contribution_fields(self):
        """FeatureContribution should hold feature_name and contribution_value."""
        fc = FeatureContribution(feature_name="amount", contribution_value=0.42)
        assert fc.feature_name == "amount"
        assert fc.contribution_value == pytest.approx(0.42)

    def test_feature_contribution_negative_value(self):
        """Negative contribution values should be allowed."""
        fc = FeatureContribution(feature_name="transaction_hour", contribution_value=-0.1)
        assert fc.contribution_value < 0

    def test_explanation_fields(self):
        """Explanation should hold transaction_id, anomaly_score, and contributions."""
        contribs = [
            FeatureContribution(feature_name="amount", contribution_value=0.3),
            FeatureContribution(feature_name="transaction_hour", contribution_value=-0.1),
        ]
        exp = Explanation(
            transaction_id="TXN-001",
            anomaly_score=-0.25,
            feature_contributions=contribs,
        )
        assert exp.transaction_id == "TXN-001"
        assert exp.anomaly_score == pytest.approx(-0.25)
        assert len(exp.feature_contributions) == 2

    def test_explanation_empty_contributions(self):
        """Explanation should allow an empty contributions list."""
        exp = Explanation(transaction_id="TXN-002", anomaly_score=0.0)
        assert exp.feature_contributions == []


# ===========================================================================
# FraudExplainer initialisation tests
# ===========================================================================


class TestFraudExplainerInit:
    """Tests for FraudExplainer construction."""

    def test_explainer_requires_trained_detector(self):
        """Creating an explainer with an untrained detector should raise."""
        untrained = FraudDetector()
        with pytest.raises(RuntimeError, match="not been trained"):
            FraudExplainer(untrained)

    def test_explainer_stores_feature_names(self, explainer: FraudExplainer):
        """FraudExplainer should expose the same feature names as the detector."""
        assert explainer.feature_names_ == FEATURE_NAMES

    def test_explainer_has_base_value(self, explainer: FraudExplainer):
        """FraudExplainer should compute a finite base value."""
        assert np.isfinite(explainer._base_value)


# ===========================================================================
# explain_transaction() tests
# ===========================================================================


class TestExplainTransaction:
    """Tests for FraudExplainer.explain_transaction()."""

    def test_returns_explanation_instance(
        self, explainer: FraudExplainer, sample_transaction: NormalizedTransaction
    ):
        """explain_transaction should return an Explanation object."""
        result = explainer.explain_transaction(sample_transaction)
        assert isinstance(result, Explanation)

    def test_transaction_id_matches(
        self, explainer: FraudExplainer, sample_transaction: NormalizedTransaction
    ):
        """Explanation.transaction_id should match the input transaction."""
        result = explainer.explain_transaction(sample_transaction)
        assert result.transaction_id == sample_transaction.transaction_id

    def test_correct_number_of_contributions(
        self, explainer: FraudExplainer, sample_transaction: NormalizedTransaction
    ):
        """Number of feature contributions should equal the number of features."""
        result = explainer.explain_transaction(sample_transaction)
        assert len(result.feature_contributions) == len(FEATURE_NAMES)

    def test_feature_names_in_contributions(
        self, explainer: FraudExplainer, sample_transaction: NormalizedTransaction
    ):
        """Feature names in contributions should match the canonical feature list."""
        result = explainer.explain_transaction(sample_transaction)
        names = [c.feature_name for c in result.feature_contributions]
        assert names == FEATURE_NAMES

    def test_contributions_are_finite(
        self, explainer: FraudExplainer, sample_transaction: NormalizedTransaction
    ):
        """All SHAP contribution values should be finite numbers."""
        result = explainer.explain_transaction(sample_transaction)
        for contrib in result.feature_contributions:
            assert np.isfinite(contrib.contribution_value)

    def test_anomaly_score_is_finite(
        self, explainer: FraudExplainer, sample_transaction: NormalizedTransaction
    ):
        """Anomaly score should be a finite float."""
        result = explainer.explain_transaction(sample_transaction)
        assert np.isfinite(result.anomaly_score)

    def test_feature_contributions_sum_to_prediction_minus_base(
        self,
        explainer: FraudExplainer,
        trained_detector: FraudDetector,
        sample_transaction: NormalizedTransaction,
    ):
        """SHAP additivity: sum of contributions ≈ fraud_probability - base_value."""
        from fraud_detection.features import build_feature_matrix

        explanation = explainer.explain_transaction(sample_transaction)
        contrib_sum = sum(
            c.contribution_value for c in explanation.feature_contributions
        )

        # Compute the model's predicted fraud probability for this transaction
        X_raw, _ = build_feature_matrix([sample_transaction])
        X_scaled = trained_detector._scaler.transform(X_raw)
        fraud_probs = trained_detector._rf_classifier.predict_proba(X_scaled)
        fraud_col = list(trained_detector._rf_classifier.classes_).index(1)
        fraud_prob = float(fraud_probs[0, fraud_col])

        expected = fraud_prob - explainer._base_value
        assert abs(contrib_sum - expected) < 1e-4

    def test_different_transactions_give_different_explanations(
        self, explainer: FraudExplainer
    ):
        """Distinct transactions should generally produce distinct explanations."""
        txn_high_risk = _make_txn(
            txn_id="TXN-HR", amount=80000.0, dest="KY", is_intl=True, is_large=True
        )
        txn_low_risk = _make_txn(
            txn_id="TXN-LR", amount=50.0, dest="US", is_intl=False, is_large=False
        )
        exp_hr = explainer.explain_transaction(txn_high_risk)
        exp_lr = explainer.explain_transaction(txn_low_risk)
        # The two explanations should differ in at least one contribution
        diffs = [
            abs(a.contribution_value - b.contribution_value)
            for a, b in zip(
                exp_hr.feature_contributions, exp_lr.feature_contributions
            )
        ]
        assert max(diffs) > 0


# ===========================================================================
# get_feature_importance() tests
# ===========================================================================


class TestGetFeatureImportance:
    """Tests for FraudExplainer.get_feature_importance()."""

    def test_returns_list_of_feature_contributions(
        self, explainer: FraudExplainer
    ):
        """get_feature_importance should return a list of FeatureContribution."""
        importance = explainer.get_feature_importance()
        assert isinstance(importance, list)
        assert all(isinstance(fi, FeatureContribution) for fi in importance)

    def test_importance_count_matches_features(self, explainer: FraudExplainer):
        """Number of importance entries should equal the number of features."""
        importance = explainer.get_feature_importance()
        assert len(importance) == len(FEATURE_NAMES)

    def test_importance_feature_names(self, explainer: FraudExplainer):
        """Feature names in importance list should match canonical feature list."""
        importance = explainer.get_feature_importance()
        names = [fi.feature_name for fi in importance]
        assert names == FEATURE_NAMES

    def test_importance_values_non_negative(self, explainer: FraudExplainer):
        """Gini importance values should all be non-negative."""
        importance = explainer.get_feature_importance()
        for fi in importance:
            assert fi.contribution_value >= 0.0

    def test_importance_values_sum_to_one(self, explainer: FraudExplainer):
        """Gini importance values should sum to approximately 1.0."""
        importance = explainer.get_feature_importance()
        total = sum(fi.contribution_value for fi in importance)
        assert abs(total - 1.0) < 1e-6


# ===========================================================================
# Compatibility with FraudDetector tests
# ===========================================================================


class TestFraudDetectorCompatibility:
    """Tests verifying compatibility between FraudExplainer and FraudDetector."""

    def test_explainer_works_with_low_estimators(self):
        """FraudExplainer should work with a detector using very few estimators."""
        detector = FraudDetector(n_estimators=10, random_state=0)
        detector.train(_make_batch(20))
        exp = FraudExplainer(detector)
        txn = _make_txn()
        result = exp.explain_transaction(txn)
        assert isinstance(result, Explanation)
        assert len(result.feature_contributions) == len(FEATURE_NAMES)

    def test_explainer_feature_names_match_detector(
        self, explainer: FraudExplainer, trained_detector: FraudDetector
    ):
        """Explainer feature names should always match the detector's feature names."""
        assert explainer.feature_names_ == trained_detector.feature_names_

    def test_explanation_transaction_id_preserved(
        self, explainer: FraudExplainer
    ):
        """Transaction ID should be correctly propagated into the explanation."""
        txn = _make_txn(txn_id="MY-UNIQUE-TXN-ID-9999")
        result = explainer.explain_transaction(txn)
        assert result.transaction_id == "MY-UNIQUE-TXN-ID-9999"

    def test_explanations_generated_for_batch(
        self, explainer: FraudExplainer
    ):
        """Explanations should be generated successfully for multiple transactions."""
        txns = _make_batch(5)
        explanations = [explainer.explain_transaction(t) for t in txns]
        assert len(explanations) == 5
        assert all(isinstance(e, Explanation) for e in explanations)
        assert all(
            len(e.feature_contributions) == len(FEATURE_NAMES)
            for e in explanations
        )
