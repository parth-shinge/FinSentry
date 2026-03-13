"""
FinSentry - Explainability Data Models
==========================================

Pydantic models for fraud-detection explanation outputs.

Models
------
FeatureContribution
    The SHAP contribution of a single feature to a prediction.
Explanation
    A complete explanation for one transaction, bundling the anomaly
    score with all per-feature SHAP contributions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FeatureContribution(BaseModel):
    """SHAP contribution of a single feature to a fraud prediction.

    Attributes:
        feature_name:       Name of the feature (e.g. ``"amount"``).
        contribution_value: SHAP value for this feature.  Positive values
                            push the prediction toward fraud; negative
                            values push it away from fraud.
    """

    feature_name: str
    contribution_value: float


class Explanation(BaseModel):
    """Full SHAP-based explanation for a single transaction.

    Attributes:
        transaction_id:        Unique transaction identifier.
        anomaly_score:         Raw anomaly score from the Isolation Forest
                               (lower values indicate more anomalous).
        feature_contributions: Ordered list of per-feature SHAP
                               contributions, one entry per feature used
                               by the underlying model.
    """

    transaction_id: str
    anomaly_score: float
    feature_contributions: list[FeatureContribution] = Field(
        default_factory=list
    )
