"""
FinSentry AI - SAR Generator Data Models
==========================================

Pydantic models for Suspicious Activity Report outputs.

Models
------
SARReport
    A complete SAR report with all required sections for FinCEN BSA
    filing compliance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class SARReport(BaseModel):
    """A structured Suspicious Activity Report (SAR).

    Contains all sections required for regulatory filing, including
    subject information, suspicious activity narrative, transaction
    evidence, and risk assessment.

    Attributes:
        report_id:                       Unique SAR identifier.
        case_id:                         Originating investigation case.
        subject_entity:                  Primary entity under investigation.
        report_date:                     Report creation timestamp (UTC).
        suspicious_activity_description: Narrative describing the suspicious
                                         activity observed.
        transaction_summary:             Summary of related transactions.
        evidence_summary:                Summary of supporting evidence.
        risk_assessment:                 Overall risk assessment narrative.
        recommended_action:              Recommended next steps for
                                         investigators.
        entities_involved:               Other entities involved.
        jurisdictions:                   Jurisdictions touched by the activity.
        total_amount:                    Sum of suspicious transaction amounts.
        risk_score:                      Numeric risk score from case builder.
    """

    report_id: str
    case_id: str
    subject_entity: str
    report_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    suspicious_activity_description: str = ""
    transaction_summary: str = ""
    evidence_summary: str = ""
    risk_assessment: str = ""
    recommended_action: str = ""
    entities_involved: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    total_amount: float = Field(ge=0.0, default=0.0)
    risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
