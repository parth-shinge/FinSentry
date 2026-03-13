"""
FinSentry - Fraud Detection Package
=======================================

Machine-learning and rule-based fraud detection for financial transactions.

Modules:
    features  -- Feature extraction and matrix building.
    detector  -- FraudDetector (Isolation Forest + Random Forest).
    models    -- Pydantic output models (FraudScore, DetectionResult).
"""

from fraud_detection.models import DetectionResult, FraudScore, RiskLevel
from fraud_detection.detector import FraudDetector

__all__ = [
    "FraudDetector",
    "FraudScore",
    "DetectionResult",
    "RiskLevel",
]
