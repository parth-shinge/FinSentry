"""
FinSentry - Fraud Detection Unit Tests
==========================================

Tests covering:

* Feature extraction (individual features, matrix shape)
* FraudDetector training, prediction, and scoring
* Risk level classification
* Model save / load round-trip

All tests use synthetic NormalizedTransaction objects -- no database or
external data required.

Run::

    cd d:\\FinSentry
    python -m pytest tests/test_fraud_detection.py -v
"""

from __future__ import annotations

import sys
import tempfile
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

from fraud_detection.features import (
    FEATURE_NAMES,
    build_feature_matrix,
    extract_features,
    get_country_risk,
)
from fraud_detection.models import DetectionResult, FraudScore, RiskLevel
from fraud_detection.detector import FraudDetector
from ingestion.schema import NormalizedTransaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_txn(
    txn_id: str = "TXN-001",
    account_id: str = "ACC-001",
    amount: float = 500.0,
    currency: str = "USD",
    origin: str = "US",
    dest: str = "US",
    hour: int = 10,
    is_intl: bool = False,
    is_large: bool = False,
    risk_flag: str | None = None,
) -> NormalizedTransaction:
    """Create a NormalizedTransaction with sensible defaults."""
    ts = datetime(2025, 1, 15, hour, 0, 0, tzinfo=timezone.utc)
    return NormalizedTransaction(
        transaction_id=txn_id,
        account_id=account_id,
        sender_entity_id="ENT-S001",
        receiver_entity_id="ENT-R001",
        amount=amount,
        currency=currency,
        timestamp=ts,
        origin_country=origin,
        destination_country=dest,
        merchant_category="retail",
        transaction_type="wire",
        channel="online",
        is_international=is_intl,
        is_large_transaction=is_large,
        risk_flag=risk_flag,
    )


def _make_batch(n: int = 30) -> list[NormalizedTransaction]:
    """Create a batch of diverse transactions for training.

    Generates a mix of domestic low-value, international high-value,
    and suspicious-pattern transactions.
    """
    txns: list[NormalizedTransaction] = []
    for i in range(n):
        if i % 5 == 0:
            # Suspicious: large international to high-risk country
            txns.append(
                _make_txn(
                    txn_id=f"TXN-{i:04d}",
                    account_id=f"ACC-{i % 3:03d}",
                    amount=float(np.random.randint(15000, 100000)),
                    origin="US",
                    dest="KY",
                    hour=np.random.randint(0, 6),
                    is_intl=True,
                    is_large=True,
                )
            )
        elif i % 3 == 0:
            # Medium risk: international, moderate amount
            txns.append(
                _make_txn(
                    txn_id=f"TXN-{i:04d}",
                    account_id=f"ACC-{i % 5:03d}",
                    amount=float(np.random.randint(3000, 9000)),
                    origin="US",
                    dest="MX",
                    hour=np.random.randint(8, 18),
                    is_intl=True,
                )
            )
        else:
            # Normal domestic transaction
            txns.append(
                _make_txn(
                    txn_id=f"TXN-{i:04d}",
                    account_id=f"ACC-{i % 7:03d}",
                    amount=float(np.random.randint(10, 2000)),
                    origin="US",
                    dest="US",
                    hour=np.random.randint(8, 20),
                )
            )
    return txns


# ===========================================================================
# Feature extraction tests
# ===========================================================================


class TestFeatureExtraction:
    """Tests for fraud_detection.features."""

    def test_extract_features_length(self):
        """Should return one feature dict per transaction."""
        txns = [_make_txn(), _make_txn(txn_id="TXN-002")]
        feats = extract_features(txns)
        assert len(feats) == 2

    def test_feature_keys(self):
        """Each feature dict should contain all expected keys."""
        feats = extract_features([_make_txn()])
        assert set(feats[0].keys()) == set(FEATURE_NAMES)

    def test_amount_feature(self):
        """Amount feature should match the transaction amount."""
        feats = extract_features([_make_txn(amount=1234.56)])
        assert feats[0]["amount"] == 1234.56

    def test_is_international_feature(self):
        """is_international should be 1.0 for cross-border txns."""
        intl = _make_txn(origin="US", dest="GB", is_intl=True)
        dom = _make_txn(origin="US", dest="US", is_intl=False)
        feats = extract_features([intl, dom])
        assert feats[0]["is_international"] == 1.0
        assert feats[1]["is_international"] == 0.0

    def test_country_risk_score(self):
        """High-risk destinations should have higher scores."""
        high = _make_txn(dest="KY")
        low = _make_txn(dest="US")
        feats = extract_features([high, low])
        assert feats[0]["country_risk_score"] > feats[1]["country_risk_score"]

    def test_empty_transactions(self):
        """Empty input should return empty list."""
        assert extract_features([]) == []

    def test_get_country_risk_known(self):
        """Known country codes should return mapped scores."""
        assert get_country_risk("KY") == 0.9
        assert get_country_risk("US") == 0.1

    def test_get_country_risk_unknown(self):
        """Unknown country codes should return the default score."""
        score = get_country_risk("ZZ")
        assert score == 0.2  # DEFAULT_COUNTRY_RISK


class TestFeatureMatrix:
    """Tests for build_feature_matrix."""

    def test_matrix_shape(self):
        """Matrix should have (n_txns, n_features) shape."""
        txns = _make_batch(10)
        X, names = build_feature_matrix(txns)
        assert X.shape == (10, len(FEATURE_NAMES))

    def test_feature_names_returned(self):
        """Feature names should match the canonical list."""
        _, names = build_feature_matrix([_make_txn()])
        assert names == FEATURE_NAMES

    def test_empty_matrix(self):
        """Empty input should return 0-row matrix."""
        X, names = build_feature_matrix([])
        assert X.shape[0] == 0
        assert X.shape[1] == len(FEATURE_NAMES)


# ===========================================================================
# Model tests
# ===========================================================================


class TestFraudModels:
    """Tests for Pydantic fraud output models."""

    def test_risk_level_low(self):
        """Probability < 0.3 should map to LOW."""
        assert FraudScore.classify_risk(0.1) == RiskLevel.LOW

    def test_risk_level_medium(self):
        """Probability in [0.3, 0.7) should map to MEDIUM."""
        assert FraudScore.classify_risk(0.5) == RiskLevel.MEDIUM

    def test_risk_level_high(self):
        """Probability >= 0.7 should map to HIGH."""
        assert FraudScore.classify_risk(0.85) == RiskLevel.HIGH

    def test_risk_level_boundary_030(self):
        """Exactly 0.3 should be MEDIUM."""
        assert FraudScore.classify_risk(0.3) == RiskLevel.MEDIUM

    def test_risk_level_boundary_070(self):
        """Exactly 0.7 should be HIGH."""
        assert FraudScore.classify_risk(0.7) == RiskLevel.HIGH

    def test_fraud_score_model(self):
        """FraudScore should serialize all fields."""
        fs = FraudScore(
            transaction_id="TXN-001",
            fraud_probability=0.85,
            anomaly_score=-0.5,
            risk_level=RiskLevel.HIGH,
        )
        assert fs.transaction_id == "TXN-001"
        assert fs.fraud_probability == 0.85

    def test_detection_result_model(self):
        """DetectionResult should bundle score and feature names."""
        fs = FraudScore(
            transaction_id="TXN-001",
            fraud_probability=0.2,
            anomaly_score=0.1,
            risk_level=RiskLevel.LOW,
        )
        dr = DetectionResult(
            transaction_id="TXN-001",
            features_used=["amount", "hour"],
            fraud_score=fs,
        )
        assert len(dr.features_used) == 2
        assert dr.fraud_score.risk_level == RiskLevel.LOW


# ===========================================================================
# Detector tests
# ===========================================================================


class TestFraudDetector:
    """Tests for the FraudDetector class."""

    @pytest.fixture()
    def trained_detector(self) -> FraudDetector:
        """Return a detector trained on a synthetic batch."""
        detector = FraudDetector(contamination=0.15, n_estimators=50, random_state=42)
        txns = _make_batch(30)
        detector.train(txns)
        return detector

    @pytest.fixture()
    def sample_txns(self) -> list[NormalizedTransaction]:
        """A small batch for prediction."""
        return _make_batch(10)

    def test_train_sets_trained_flag(self, trained_detector: FraudDetector):
        """After training, is_trained should be True."""
        assert trained_detector.is_trained is True

    def test_train_stores_feature_names(self, trained_detector: FraudDetector):
        """Feature names should be stored after training."""
        assert trained_detector.feature_names_ == FEATURE_NAMES

    def test_predict_returns_results(
        self, trained_detector: FraudDetector, sample_txns
    ):
        """predict() should return one DetectionResult per transaction."""
        results = trained_detector.predict(sample_txns)
        assert len(results) == len(sample_txns)
        assert all(isinstance(r, DetectionResult) for r in results)

    def test_predict_fraud_probability_range(
        self, trained_detector: FraudDetector, sample_txns
    ):
        """Fraud probabilities should be in [0, 1]."""
        results = trained_detector.predict(sample_txns)
        for r in results:
            assert 0.0 <= r.fraud_score.fraud_probability <= 1.0

    def test_predict_risk_levels_valid(
        self, trained_detector: FraudDetector, sample_txns
    ):
        """Risk levels should only be LOW, MEDIUM, or HIGH."""
        results = trained_detector.predict(sample_txns)
        valid_levels = {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}
        for r in results:
            assert r.fraud_score.risk_level in valid_levels

    def test_score_returns_fraud_scores(
        self, trained_detector: FraudDetector, sample_txns
    ):
        """score() should return FraudScore objects."""
        scores = trained_detector.score(sample_txns)
        assert len(scores) == len(sample_txns)
        assert all(isinstance(s, FraudScore) for s in scores)

    def test_predict_before_train_raises(self):
        """Calling predict on an untrained detector should raise."""
        detector = FraudDetector()
        with pytest.raises(RuntimeError, match="not been trained"):
            detector.predict([_make_txn()])

    def test_train_too_few_raises(self):
        """Training with fewer than 5 transactions should raise."""
        detector = FraudDetector()
        with pytest.raises(ValueError, match="at least 5"):
            detector.train([_make_txn()])

    def test_features_used_in_results(
        self, trained_detector: FraudDetector, sample_txns
    ):
        """Each result should include the feature names used."""
        results = trained_detector.predict(sample_txns)
        for r in results:
            assert r.features_used == FEATURE_NAMES

    def test_save_and_load(self, trained_detector: FraudDetector, sample_txns):
        """Model should produce identical results after save/load."""
        results_before = trained_detector.predict(sample_txns)

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "model.pkl"
            trained_detector.save(model_path)

            new_detector = FraudDetector()
            new_detector.load(model_path)

        results_after = new_detector.predict(sample_txns)

        for before, after in zip(results_before, results_after):
            assert before.fraud_score.fraud_probability == after.fraud_score.fraud_probability
            assert before.fraud_score.risk_level == after.fraud_score.risk_level

    def test_load_nonexistent_raises(self):
        """Loading from a nonexistent path should raise."""
        detector = FraudDetector()
        with pytest.raises(FileNotFoundError):
            detector.load("/nonexistent/model.pkl")

    def test_train_with_labels(self):
        """Training with explicit labels should work."""
        txns = _make_batch(20)
        labels = np.array([1 if i % 5 == 0 else 0 for i in range(20)])
        detector = FraudDetector(n_estimators=20, random_state=42)
        detector.train(txns, labels=labels)
        assert detector.is_trained
        results = detector.predict(txns)
        assert len(results) == 20
