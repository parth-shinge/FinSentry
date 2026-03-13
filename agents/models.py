"""
FinSentry - Agent Data Models
===================================

Pydantic and dataclass models for orchestrator outputs.

Models
------
TimelineEvent
    A single chronological event in a case timeline.
InvestigationResult
    Complete output from a full pipeline investigation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, Field

from case_builder.models import Case
from compliance_validator.models import ValidationResult
from explainability.models import Explanation
from fraud_detection.models import DetectionResult
from graph_engine.models import EntityRiskScore
from sar_generator.models import SARReport

if TYPE_CHECKING:
    from aml_patterns.models import PatternDetection
    from explainability.risk_explainer import RiskExplanation
    from investigation_narrative.generator import InvestigationNarrative


# ---------------------------------------------------------------------------
# Timeline Event
# ---------------------------------------------------------------------------


class TimelineEvent(BaseModel):
    """A single chronological event in a transaction investigation timeline.

    Attributes:
        timestamp:      ISO-format timestamp of the event.
        event_type:     Category of event (deposit, transfer, offshore_movement,
                        withdrawal, flagged_transaction).
        description:    Human-readable description of what occurred.
        transaction_id: Associated transaction ID, if applicable.
        sender:         Sender entity ID.
        receiver:       Receiver entity ID.
        amount:         Transaction amount.
        currency:       Currency code.
        origin_country: Origin jurisdiction.
        destination_country: Destination jurisdiction.
        fraud_score:    Fraud probability, if available.
        risk_level:     Risk classification (LOW/MEDIUM/HIGH), if available.
    """

    timestamp: str
    event_type: str
    description: str
    transaction_id: Optional[str] = None
    sender: Optional[str] = None
    receiver: Optional[str] = None
    amount: float = 0.0
    currency: str = "USD"
    origin_country: str = ""
    destination_country: str = ""
    fraud_score: Optional[float] = None
    risk_level: Optional[str] = None


# ---------------------------------------------------------------------------
# Investigation Result
# ---------------------------------------------------------------------------


@dataclass
class InvestigationResult:
    """Complete output from a full FinSentry pipeline investigation.

    Bundles all intermediate and final results from each stage of the
    pipeline so that downstream consumers (API, dashboards, reports)
    have unified access.

    Attributes:
        transactions_processed: Number of transactions analysed.
        fraud_results:          Per-transaction fraud detection results.
        explanations:           SHAP-based explanations for high-risk transactions.
        graph_metrics:          Entity-level graph risk scores.
        cases:                  Generated investigation cases.
        sar_reports:            Generated SAR reports.
        validation_results:     Compliance validation results per SAR.
    """

    transactions_processed: int = 0
    fraud_results: list[DetectionResult] = field(default_factory=list)
    explanations: list[Explanation] = field(default_factory=list)
    graph_metrics: list[EntityRiskScore] = field(default_factory=list)
    cases: list[Case] = field(default_factory=list)
    sar_reports: list[SARReport] = field(default_factory=list)
    validation_results: list[ValidationResult] = field(default_factory=list)
    aml_patterns: list[Any] = field(default_factory=list)
    risk_explanations: list[Any] = field(default_factory=list)
    narratives: list[Any] = field(default_factory=list)

    @property
    def high_risk_count(self) -> int:
        """Number of HIGH-risk transactions."""
        return sum(
            1 for r in self.fraud_results
            if r.fraud_score.risk_level.value == "HIGH"
        )

    @property
    def total_cases(self) -> int:
        """Number of investigation cases generated."""
        return len(self.cases)

    @property
    def all_reports_valid(self) -> bool:
        """True if all SAR reports passed compliance validation."""
        return all(v.is_valid for v in self.validation_results)
