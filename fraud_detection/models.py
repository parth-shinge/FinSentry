"""
FinSentry - Fraud Detection Data Models
===========================================

Pydantic models for fraud detection outputs.

Models
------
FraudScore
    Per-transaction fraud assessment with probability, anomaly score,
    and categorical risk level.
DetectionResult
    Extended result bundling a ``FraudScore`` with the feature names
    that contributed to the prediction.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Categorical risk classification for a transaction.

    Values:
        LOW:    Fraud probability < 0.3
        MEDIUM: Fraud probability in [0.3, 0.7)
        HIGH:   Fraud probability >= 0.7
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FraudScore(BaseModel):
    """Fraud assessment for a single transaction.

    Attributes:
        transaction_id:    Unique transaction identifier.
        fraud_probability: Probability of fraud in [0, 1].
        anomaly_score:     Raw anomaly score from Isolation Forest
                           (lower = more anomalous).
        risk_level:        Categorical risk (LOW / MEDIUM / HIGH).
    """

    transaction_id: str
    fraud_probability: float = Field(ge=0.0, le=1.0)
    anomaly_score: float
    risk_level: RiskLevel

    @staticmethod
    def classify_risk(probability: float) -> RiskLevel:
        """Map a fraud probability to a categorical risk level.

        Args:
            probability: Fraud probability in [0, 1].

        Returns:
            ``RiskLevel.HIGH`` if >= 0.7,
            ``RiskLevel.MEDIUM`` if >= 0.3,
            ``RiskLevel.LOW`` otherwise.
        """
        if probability >= 0.7:
            return RiskLevel.HIGH
        if probability >= 0.3:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


class DetectionResult(BaseModel):
    """Extended fraud detection result for a transaction.

    Bundles the :class:`FraudScore` with metadata about which features
    were used, enabling downstream explainability.

    Attributes:
        transaction_id: Unique transaction identifier.
        features_used:  List of feature column names the model evaluated.
        fraud_score:    The fraud assessment (:class:`FraudScore`).
    """

    transaction_id: str
    features_used: list[str]
    fraud_score: FraudScore
