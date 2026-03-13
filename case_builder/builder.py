"""
FinSentry - Investigation Case Builder
============================================

Aggregates suspicious transactions, graph intelligence insights, and
fraud scores into structured investigation cases.

The builder converts raw detection outputs into investigator-ready cases
by:

1. Identifying high-risk transactions above a configurable threshold.
2. Grouping them by shared entities (sender / receiver overlap).
3. Expanding the entity set using graph-neighbor lookups.
4. Collecting supporting evidence (cross-border flows, value patterns,
   circular transactions, entity clusters).
5. Computing a composite case risk score.

Usage::

    from case_builder.builder import CaseBuilder

    builder = CaseBuilder()
    cases = builder.build_cases(transactions, fraud_results, entity_risk_scores)
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, Sequence

import networkx as nx

from case_builder.models import Case, Evidence, RiskIndicator
from fraud_detection.models import DetectionResult
from graph_engine.models import EntityRiskScore
from ingestion.schema import NormalizedTransaction
from utils.logging import get_logger

logger = get_logger("case_builder.builder")

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
_DEFAULT_FRAUD_THRESHOLD = 0.5
_HIGH_VALUE_THRESHOLD = 10_000.0
_CRITICAL_FRAUD_THRESHOLD = 0.8


class CaseBuilder:
    """Builds structured investigation cases from detection outputs.

    Groups high-risk transactions and entities into actionable cases
    with supporting evidence and composite risk scores.

    Args:
        fraud_threshold: Minimum fraud probability for a transaction to
                         be considered suspicious.  Default ``0.5``.
        high_value_threshold: Amount above which a transfer is flagged
                              as high-value.  Default ``10_000``.
    """

    def __init__(
        self,
        fraud_threshold: float = _DEFAULT_FRAUD_THRESHOLD,
        high_value_threshold: float = _HIGH_VALUE_THRESHOLD,
    ) -> None:
        self.fraud_threshold = fraud_threshold
        self.high_value_threshold = high_value_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_cases(
        self,
        transactions: Sequence[NormalizedTransaction],
        fraud_results: Sequence[DetectionResult],
        entity_risk_scores: Optional[Sequence[EntityRiskScore]] = None,
        graph: Optional[nx.DiGraph] = None,
    ) -> list[Case]:
        """Build investigation cases from detection outputs.

        Args:
            transactions:       Normalised transactions.
            fraud_results:      Fraud detection results (one per txn).
            entity_risk_scores: Optional graph-based risk scores.
            graph:              Optional transaction graph for neighbor
                                expansion.

        Returns:
            List of :class:`Case` objects sorted by risk (descending).
        """
        # Build lookup maps
        txn_map = {t.transaction_id: t for t in transactions}
        fraud_map = {
            r.transaction_id: r.fraud_score.fraud_probability
            for r in fraud_results
        }
        risk_map = (
            {rs.entity_id: rs for rs in entity_risk_scores}
            if entity_risk_scores
            else {}
        )

        # Step 1: Identify high-risk transactions
        high_risk_txn_ids = [
            tid
            for tid, prob in fraud_map.items()
            if prob >= self.fraud_threshold
        ]

        if not high_risk_txn_ids:
            logger.info("No transactions above fraud threshold %.2f", self.fraud_threshold)
            return []

        logger.info(
            "Found %d high-risk transactions (threshold=%.2f)",
            len(high_risk_txn_ids),
            self.fraud_threshold,
        )

        # Step 2: Group by shared entities
        entity_groups = self._group_by_entities(high_risk_txn_ids, txn_map)

        # Step 3: Build cases
        cases: list[Case] = []
        for primary_entity, txn_ids in entity_groups.items():
            # Expand related entities
            related = self._expand_related_entities(
                primary_entity, txn_ids, txn_map, graph
            )

            # Collect all transactions for the case
            case_txn_ids = list(txn_ids)
            case_fraud_scores = {
                tid: fraud_map.get(tid, 0.0) for tid in case_txn_ids
            }

            # Graph metrics for primary entity
            graph_metrics: dict[str, float] = {}
            if primary_entity in risk_map:
                ers = risk_map[primary_entity]
                graph_metrics = {
                    "centrality_score": ers.centrality_score,
                    "community_fraud_density": ers.community_fraud_density,
                    "cycle_participation": float(ers.cycle_participation_count),
                    "overall_graph_risk": ers.overall_risk_score,
                }

            # Generate evidence
            case_txns = [txn_map[tid] for tid in case_txn_ids if tid in txn_map]
            evidence = self._generate_evidence(
                case_txns, case_fraud_scores, primary_entity, related, graph
            )

            # Generate risk indicators
            risk_indicators = self._generate_risk_indicators(
                case_txns, case_fraud_scores, graph_metrics
            )

            # Compute case risk score
            risk_score = self._compute_case_risk(
                case_fraud_scores, graph_metrics, risk_indicators, case_txns
            )

            case = Case(
                case_id=f"CASE-{uuid.uuid4().hex[:8].upper()}",
                primary_entity=primary_entity,
                related_entities=sorted(related),
                transactions=case_txn_ids,
                fraud_scores=case_fraud_scores,
                graph_metrics=graph_metrics,
                risk_indicators=risk_indicators,
                evidence=evidence,
                risk_score=risk_score,
                created_at=datetime.now(timezone.utc),
            )
            cases.append(case)

        # Sort by risk descending
        cases.sort(key=lambda c: c.risk_score, reverse=True)

        logger.info("Built %d investigation cases", len(cases))
        return cases

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------

    def _group_by_entities(
        self,
        txn_ids: list[str],
        txn_map: dict[str, NormalizedTransaction],
    ) -> dict[str, set[str]]:
        """Group transactions by their most prominent entity.

        Each entity that appears as sender in a high-risk transaction
        becomes a candidate primary entity.  Transactions are assigned
        to the sender entity.

        Returns:
            Mapping of primary_entity → set of transaction IDs.
        """
        groups: dict[str, set[str]] = defaultdict(set)

        for tid in txn_ids:
            txn = txn_map.get(tid)
            if txn is None:
                continue
            groups[txn.sender_entity_id].add(tid)

        return dict(groups)

    # ------------------------------------------------------------------
    # Entity Expansion
    # ------------------------------------------------------------------

    def _expand_related_entities(
        self,
        primary: str,
        txn_ids: set[str],
        txn_map: dict[str, NormalizedTransaction],
        graph: Optional[nx.DiGraph],
    ) -> set[str]:
        """Expand the set of related entities beyond direct transactions.

        Includes:
        * Receiver entities from associated transactions.
        * One-hop graph neighbors of the primary entity.

        Returns:
            Set of related entity IDs (excluding the primary).
        """
        related: set[str] = set()

        # Direct transaction counterparties
        for tid in txn_ids:
            txn = txn_map.get(tid)
            if txn is None:
                continue
            related.add(txn.sender_entity_id)
            related.add(txn.receiver_entity_id)

        # Graph-based neighbor expansion
        if graph is not None and primary in graph:
            for neighbor in graph.successors(primary):
                related.add(neighbor)
            for neighbor in graph.predecessors(primary):
                related.add(neighbor)

        related.discard(primary)
        return related

    # ------------------------------------------------------------------
    # Evidence Generation
    # ------------------------------------------------------------------

    def _generate_evidence(
        self,
        transactions: list[NormalizedTransaction],
        fraud_scores: dict[str, float],
        primary_entity: str,
        related_entities: set[str],
        graph: Optional[nx.DiGraph],
    ) -> list[Evidence]:
        """Automatically generate evidence items for a case.

        Detects:
        * High-value transfers
        * Cross-border flows
        * Circular transaction patterns (via graph cycles)
        * Dense entity clusters
        """
        evidence: list[Evidence] = []

        # 1. High-value transfers
        high_value = [
            t for t in transactions if t.amount >= self.high_value_threshold
        ]
        if high_value:
            evidence.append(
                Evidence(
                    evidence_type="high_value_transfer",
                    description=(
                        f"{len(high_value)} transaction(s) exceeding "
                        f"${self.high_value_threshold:,.0f}"
                    ),
                    related_transactions=[t.transaction_id for t in high_value],
                    related_entities=[primary_entity],
                )
            )

        # 2. Cross-border flows
        cross_border = [t for t in transactions if t.is_international]
        if cross_border:
            countries = set()
            for t in cross_border:
                countries.add(t.origin_country)
                countries.add(t.destination_country)
            evidence.append(
                Evidence(
                    evidence_type="cross_border_flow",
                    description=(
                        f"{len(cross_border)} cross-border transaction(s) "
                        f"spanning {len(countries)} jurisdictions: "
                        f"{', '.join(sorted(countries))}"
                    ),
                    related_transactions=[
                        t.transaction_id for t in cross_border
                    ],
                    related_entities=sorted(related_entities),
                )
            )

        # 3. Circular patterns (via graph)
        if graph is not None and primary_entity in graph:
            try:
                cycles = [
                    c
                    for c in nx.simple_cycles(graph)
                    if primary_entity in c and len(c) <= 6
                ]
                if cycles:
                    cycle_entities = set()
                    for cycle in cycles:
                        cycle_entities.update(cycle)
                    evidence.append(
                        Evidence(
                            evidence_type="circular_flow",
                            description=(
                                f"{len(cycles)} circular transaction "
                                f"pattern(s) involving {primary_entity}"
                            ),
                            related_transactions=[],
                            related_entities=sorted(cycle_entities),
                        )
                    )
            except Exception:
                pass  # Cycle detection may timeout on large graphs

        # 4. Dense entity clusters
        if len(related_entities) >= 3:
            evidence.append(
                Evidence(
                    evidence_type="entity_cluster",
                    description=(
                        f"Dense cluster of {len(related_entities)} related "
                        f"entities around {primary_entity}"
                    ),
                    related_transactions=[
                        t.transaction_id for t in transactions
                    ],
                    related_entities=sorted(related_entities),
                )
            )

        # 5. Critical fraud scores
        critical_txns = [
            tid
            for tid, score in fraud_scores.items()
            if score >= _CRITICAL_FRAUD_THRESHOLD
        ]
        if critical_txns:
            evidence.append(
                Evidence(
                    evidence_type="critical_fraud_score",
                    description=(
                        f"{len(critical_txns)} transaction(s) with fraud "
                        f"probability >= {_CRITICAL_FRAUD_THRESHOLD}"
                    ),
                    related_transactions=critical_txns,
                    related_entities=[primary_entity],
                )
            )

        return evidence

    # ------------------------------------------------------------------
    # Risk Indicators
    # ------------------------------------------------------------------

    def _generate_risk_indicators(
        self,
        transactions: list[NormalizedTransaction],
        fraud_scores: dict[str, float],
        graph_metrics: dict[str, float],
    ) -> list[RiskIndicator]:
        """Generate risk indicator flags for a case."""
        indicators: list[RiskIndicator] = []

        # High-value transfers
        if any(t.amount >= self.high_value_threshold for t in transactions):
            max_amount = max(t.amount for t in transactions)
            indicators.append(
                RiskIndicator(
                    indicator_type="high_value_transfer",
                    severity="high",
                    description=(
                        f"Transactions include amounts up to "
                        f"${max_amount:,.2f}"
                    ),
                )
            )

        # Cross-border activity
        intl_count = sum(1 for t in transactions if t.is_international)
        if intl_count > 0:
            indicators.append(
                RiskIndicator(
                    indicator_type="cross_border",
                    severity="high" if intl_count >= 3 else "medium",
                    description=(
                        f"{intl_count} cross-border transaction(s) detected"
                    ),
                )
            )

        # Rapid succession (multiple transactions within same day)
        if len(transactions) >= 3:
            timestamps = sorted(t.timestamp for t in transactions)
            for i in range(len(timestamps) - 2):
                delta = (timestamps[i + 2] - timestamps[i]).total_seconds()
                if delta <= 3600:  # 3 txns within 1 hour
                    indicators.append(
                        RiskIndicator(
                            indicator_type="rapid_succession",
                            severity="high",
                            description=(
                                "Multiple transactions in rapid succession "
                                "(3+ within 1 hour)"
                            ),
                        )
                    )
                    break

        # Graph-based: cycle participation
        cycle_count = graph_metrics.get("cycle_participation", 0)
        if cycle_count > 0:
            indicators.append(
                RiskIndicator(
                    indicator_type="circular_flow",
                    severity="critical",
                    description=(
                        f"Entity participates in {int(cycle_count)} "
                        f"circular transaction pattern(s)"
                    ),
                )
            )

        # High average fraud score
        if fraud_scores:
            avg_fraud = sum(fraud_scores.values()) / len(fraud_scores)
            if avg_fraud >= _CRITICAL_FRAUD_THRESHOLD:
                indicators.append(
                    RiskIndicator(
                        indicator_type="high_fraud_concentration",
                        severity="critical",
                        description=(
                            f"Average fraud probability {avg_fraud:.2f} "
                            f"across {len(fraud_scores)} transaction(s)"
                        ),
                    )
                )

        return indicators

    # ------------------------------------------------------------------
    # Risk Scoring
    # ------------------------------------------------------------------

    def _compute_case_risk(
        self,
        fraud_scores: dict[str, float],
        graph_metrics: dict[str, float],
        risk_indicators: list[RiskIndicator],
        transactions: list[NormalizedTransaction],
    ) -> float:
        """Compute a composite case risk score in [0, 1].

        Weighted combination:
        * 35% — average fraud probability
        * 25% — entity graph risk score
        * 20% — risk indicator severity
        * 20% — transaction volume / value signal
        """
        # 1. Average fraud probability (35%)
        avg_fraud = (
            sum(fraud_scores.values()) / len(fraud_scores)
            if fraud_scores
            else 0.0
        )

        # 2. Entity graph risk (25%)
        graph_risk = graph_metrics.get("overall_graph_risk", 0.0)

        # 3. Risk indicator severity (20%)
        severity_weights = {
            "low": 0.1,
            "medium": 0.3,
            "high": 0.6,
            "critical": 1.0,
        }
        if risk_indicators:
            indicator_score = max(
                severity_weights.get(ri.severity, 0.3)
                for ri in risk_indicators
            )
        else:
            indicator_score = 0.0

        # 4. Transaction volume / value signal (20%)
        total_amount = sum(t.amount for t in transactions) if transactions else 0.0
        txn_count = len(transactions)
        # Normalize: high volume = higher risk
        volume_signal = min(txn_count / 10.0, 1.0)  # cap at 10 txns
        value_signal = min(total_amount / 100_000.0, 1.0)  # cap at 100k
        txn_signal = 0.5 * volume_signal + 0.5 * value_signal

        overall = (
            0.35 * avg_fraud
            + 0.25 * graph_risk
            + 0.20 * indicator_score
            + 0.20 * txn_signal
        )
        return round(min(max(overall, 0.0), 1.0), 4)
