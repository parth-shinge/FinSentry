"""
FinSentry - Risk Explainer
================================

Generates human-readable explanations for entity risk scores.

Analyses the contributing factors behind a risk score and produces
a structured explanation with a ranked list of risk drivers.

Usage::

    from explainability.risk_explainer import RiskExplainer

    explainer = RiskExplainer()
    explanation = explainer.explain_entity_risk(
        entity_id, entity_risk_score, transactions, graph
    )
"""

from __future__ import annotations

from typing import Optional, Sequence

import networkx as nx

from graph_engine.models import EntityRiskScore
from ingestion.schema import NormalizedTransaction
from utils.logging import get_logger

logger = get_logger("explainability.risk_explainer")


class RiskDriver:
    """A single factor contributing to an entity's risk score."""

    def __init__(self, factor: str, weight: float, detail: str = "") -> None:
        self.factor = factor
        self.weight = weight
        self.detail = detail

    def __repr__(self) -> str:
        return f"RiskDriver({self.factor!r}, weight={self.weight:.2f})"


class RiskExplanation:
    """Structured explanation for an entity's risk score."""

    def __init__(
        self,
        entity_id: str,
        risk_score: float,
        drivers: list[RiskDriver],
    ) -> None:
        self.entity_id = entity_id
        self.risk_score = risk_score
        self.drivers = sorted(drivers, key=lambda d: d.weight, reverse=True)

    def to_text(self) -> str:
        """Render as readable text block."""
        lines = [f"Risk Score: {self.risk_score:.2f}", "", "Drivers:", ""]
        for d in self.drivers:
            detail = f" — {d.detail}" if d.detail else ""
            lines.append(f"  \u2022 {d.factor}{detail}")
        return "\n".join(lines)


class RiskExplainer:
    """Generates human-readable explanations for entity risk scores."""

    def explain_entity_risk(
        self,
        entity_id: str,
        entity_risk: EntityRiskScore,
        transactions: Sequence[NormalizedTransaction],
        graph: Optional[nx.DiGraph] = None,
    ) -> RiskExplanation:
        """Produce a risk explanation for a single entity.

        Args:
            entity_id:    The entity to explain.
            entity_risk:  Graph-based risk score for the entity.
            transactions: Full transaction dataset.
            graph:        Optional transaction graph.

        Returns:
            A :class:`RiskExplanation` with ranked drivers.
        """
        drivers: list[RiskDriver] = []

        # Gather entity transactions
        entity_txns = [
            t for t in transactions
            if t.sender_entity_id == entity_id
            or t.receiver_entity_id == entity_id
        ]

        # --- Driver: Cross-border transfers ---
        cross_border = [t for t in entity_txns if t.is_international]
        if cross_border:
            countries = set()
            for t in cross_border:
                countries.add(t.origin_country)
                countries.add(t.destination_country)
            drivers.append(RiskDriver(
                factor="Cross-border transfers",
                weight=0.3 + min(len(cross_border) * 0.05, 0.2),
                detail=f"{len(cross_border)} international transaction(s) across {', '.join(sorted(countries))}",
            ))

        # --- Driver: High transaction amount ---
        if entity_txns:
            total_value = sum(t.amount for t in entity_txns)
            max_txn = max(t.amount for t in entity_txns)
            if max_txn >= 10_000:
                drivers.append(RiskDriver(
                    factor="High transaction amount",
                    weight=min(max_txn / 100_000, 0.5),
                    detail=f"Max single transaction ${max_txn:,.2f}, total ${total_value:,.2f}",
                ))

        # --- Driver: Rapid transfer chain ---
        if len(entity_txns) >= 3:
            sorted_txns = sorted(entity_txns, key=lambda t: t.timestamp)
            for i in range(len(sorted_txns) - 2):
                delta = (sorted_txns[i + 2].timestamp - sorted_txns[i].timestamp).total_seconds()
                if delta <= 3600:
                    drivers.append(RiskDriver(
                        factor="Rapid transfer chain",
                        weight=0.35,
                        detail=f"{len(entity_txns)} transactions with rapid succession detected",
                    ))
                    break

        # --- Driver: Graph centrality ---
        if entity_risk.centrality_score > 0.1:
            drivers.append(RiskDriver(
                factor="High graph centrality",
                weight=entity_risk.centrality_score,
                detail=f"Centrality score {entity_risk.centrality_score:.3f}",
            ))

        # --- Driver: Suspicious graph cluster ---
        if entity_risk.community_fraud_density > 0.1:
            drivers.append(RiskDriver(
                factor="Suspicious graph cluster",
                weight=entity_risk.community_fraud_density,
                detail=f"Community fraud density {entity_risk.community_fraud_density:.3f}",
            ))

        # --- Driver: Cycle participation ---
        if entity_risk.cycle_participation_count > 0:
            drivers.append(RiskDriver(
                factor="Circular transaction patterns",
                weight=0.3 + min(entity_risk.cycle_participation_count * 0.1, 0.2),
                detail=f"Participates in {entity_risk.cycle_participation_count} cycle(s)",
            ))

        # --- Driver: High-risk neighbors ---
        if entity_risk.high_risk_neighbor_count > 0:
            drivers.append(RiskDriver(
                factor="High-risk network connections",
                weight=0.2 + min(entity_risk.high_risk_neighbor_count * 0.05, 0.2),
                detail=f"{entity_risk.high_risk_neighbor_count} high-risk neighbor(s)",
            ))

        explanation = RiskExplanation(
            entity_id=entity_id,
            risk_score=entity_risk.overall_risk_score,
            drivers=drivers,
        )

        logger.info(
            "Generated risk explanation for %s: score=%.2f, %d drivers",
            entity_id, entity_risk.overall_risk_score, len(drivers),
        )
        return explanation

    def explain_multiple(
        self,
        entity_risks: Sequence[EntityRiskScore],
        transactions: Sequence[NormalizedTransaction],
        graph: Optional[nx.DiGraph] = None,
    ) -> list[RiskExplanation]:
        """Generate risk explanations for multiple entities."""
        explanations = []
        for er in entity_risks:
            explanation = self.explain_entity_risk(
                er.entity_id, er, transactions, graph
            )
            explanations.append(explanation)
        return explanations
