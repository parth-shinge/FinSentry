"""
FinSentry - Explainability Package
======================================

SHAP-based explainability for the FinSentry fraud-detection engine.

Modules:
    models    -- Pydantic output models (FeatureContribution, Explanation).
    explainer -- FraudExplainer (SHAP TreeExplainer wrapper).
"""

from explainability.models import Explanation, FeatureContribution
from explainability.explainer import FraudExplainer

__all__ = [
    "FraudExplainer",
    "FeatureContribution",
    "Explanation",
]
