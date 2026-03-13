"""
FinSentry - Investigation Case Builder Package
====================================================

Converts raw fraud alerts, graph insights, and transaction data into
structured investigation cases ready for analyst review.

Modules:
    builder  -- CaseBuilder (group, expand, score, evidence).
    models   -- Pydantic output models (Case, Evidence, RiskIndicator).
"""

from case_builder.models import Case, Evidence, RiskIndicator
from case_builder.builder import CaseBuilder

__all__ = [
    "CaseBuilder",
    "Case",
    "Evidence",
    "RiskIndicator",
]
