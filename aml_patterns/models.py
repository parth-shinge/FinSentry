"""
FinSentry - AML Pattern Detection Models
=============================================

Data models for Anti-Money Laundering pattern detection results.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class PatternDetection(BaseModel):
    """A detected AML pattern in transaction data.

    Attributes:
        pattern_type:       Category of AML pattern detected.
        confidence:         Confidence score in [0, 1].
        severity:           Severity level: low, medium, high, critical.
        description:        Human-readable explanation of the pattern.
        involved_entities:  Entity IDs involved in the pattern.
        involved_transactions: Transaction IDs involved.
        total_amount:       Aggregate monetary value of the pattern.
        time_window_hours:  Duration over which the pattern was observed.
        indicators:         Specific sub-indicators that triggered detection.
        detected_at:        Timestamp of detection.
    """

    pattern_type: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    severity: str = "medium"
    description: str = ""
    involved_entities: list[str] = Field(default_factory=list)
    involved_transactions: list[str] = Field(default_factory=list)
    total_amount: float = Field(ge=0.0, default=0.0)
    time_window_hours: float = Field(ge=0.0, default=0.0)
    indicators: list[str] = Field(default_factory=list)
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
