"""
FinSentry - Investigation Case Data Models
================================================

Pydantic models for structured investigation case outputs.

Models
------
RiskIndicator
    A single risk signal detected during case analysis.
Evidence
    A piece of supporting evidence linking transactions and entities.
Case
    A complete investigation case aggregating alerts, graph insights,
    and fraud scores into an investigator-ready package.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class RiskIndicator(BaseModel):
    """A single risk indicator detected during case analysis.

    Attributes:
        indicator_type: Category of risk signal (e.g. ``high_value_transfer``,
                        ``circular_flow``, ``cross_border``).
        severity:       Severity level: ``low``, ``medium``, ``high``,
                        ``critical``.
        description:    Human-readable explanation of the indicator.
    """

    indicator_type: str
    severity: str = "medium"
    description: str = ""


class Evidence(BaseModel):
    """A piece of supporting evidence for an investigation case.

    Attributes:
        evidence_type:        Category of evidence (e.g. ``transaction_pattern``,
                              ``graph_anomaly``, ``entity_cluster``).
        description:          Human-readable summary of the evidence.
        related_transactions: Transaction IDs related to this evidence.
        related_entities:     Entity IDs related to this evidence.
    """

    evidence_type: str
    description: str = ""
    related_transactions: list[str] = Field(default_factory=list)
    related_entities: list[str] = Field(default_factory=list)


class Case(BaseModel):
    """A structured investigation case.

    Aggregates suspicious transactions, fraud scores, graph metrics,
    and supporting evidence into a single investigator-ready case.

    Attributes:
        case_id:           Unique case identifier.
        primary_entity:    The main entity under investigation.
        related_entities:  Other entities involved in the case.
        transactions:      Transaction IDs associated with the case.
        fraud_scores:      Mapping of transaction_id → fraud probability.
        graph_metrics:     Graph-derived metrics for the primary entity.
        risk_indicators:   List of detected risk signals.
        evidence:          Supporting evidence items.
        risk_score:        Overall case risk score in [0, 1].
        created_at:        Timestamp when the case was built.
    """

    case_id: str
    primary_entity: str
    related_entities: list[str] = Field(default_factory=list)
    transactions: list[str] = Field(default_factory=list)
    fraud_scores: dict[str, float] = Field(default_factory=dict)
    graph_metrics: dict[str, float] = Field(default_factory=dict)
    risk_indicators: list[RiskIndicator] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ── Computed investigation properties ─────────────────────────

    @property
    def severity_label(self) -> str:
        """Human-readable case severity: critical / high / medium / low."""
        if self.risk_score >= 0.8:
            return "critical"
        if self.risk_score >= 0.6:
            return "high"
        if self.risk_score >= 0.4:
            return "medium"
        return "low"

    @property
    def entities_involved(self) -> list[str]:
        """All entities associated with this case (primary + related)."""
        return [self.primary_entity] + list(self.related_entities)

    @property
    def transaction_count(self) -> int:
        """Number of transactions in this case."""
        return len(self.transactions)

    @property
    def aml_patterns_detected(self) -> list[str]:
        """Unique AML pattern types from risk indicators."""
        return list(dict.fromkeys(
            ri.indicator_type for ri in self.risk_indicators
        ))
