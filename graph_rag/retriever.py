"""
FinSentry - Graph Retriever
================================

Extracts relevant subgraph context for a given investigation case by
querying the transaction graph and entity risk scores.

The retriever bridges the **Case Builder** and the **SAR Generator** by
pulling graph-derived intelligence into a structured form that the
:class:`~graph_rag.context_builder.ContextBuilder` can format for report
generation.

Usage::

    from graph_rag.retriever import GraphRetriever

    retriever = GraphRetriever(graph, analyzer)
    context = retriever.retrieve(case, transactions, fraud_results)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import networkx as nx

from case_builder.models import Case
from fraud_detection.models import DetectionResult
from graph_engine.analyzer import GraphAnalyzer
from graph_engine.models import CommunityResult, EntityRiskScore, NodeMetrics, PathResult
from ingestion.schema import NormalizedTransaction
from utils.logging import get_logger

logger = get_logger("graph_rag.retriever")


# ---------------------------------------------------------------------------
# Retrieved context container
# ---------------------------------------------------------------------------


@dataclass
class RetrievedContext:
    """Raw graph intelligence pulled for a single investigation case.

    Attributes:
        case_id:                   Originating case identifier.
        primary_entity:            Entity under investigation.
        entity_metrics:            Node-level metrics for involved entities.
        community:                 Community the primary entity belongs to.
        suspicious_paths:          Shortest paths with high fraud exposure.
        cycles:                    Circular flows involving the primary entity.
        related_transactions:      Transactions directly involving case entities.
        entity_risk_scores:        Graph-based risk scores for involved entities.
        high_risk_neighbors:       Neighbor entities with elevated risk.
    """

    case_id: str = ""
    primary_entity: str = ""
    entity_metrics: list[NodeMetrics] = field(default_factory=list)
    community: Optional[CommunityResult] = None
    suspicious_paths: list[PathResult] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    related_transactions: list[NormalizedTransaction] = field(default_factory=list)
    entity_risk_scores: list[EntityRiskScore] = field(default_factory=list)
    high_risk_neighbors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Graph Retriever
# ---------------------------------------------------------------------------


class GraphRetriever:
    """Retrieves relevant graph context for an investigation case.

    Combines node metrics, community membership, suspicious paths,
    and cycle participation into a :class:`RetrievedContext` that
    downstream modules (SAR generator) can consume.

    Args:
        graph:    The transaction NetworkX DiGraph.
        analyzer: A configured :class:`GraphAnalyzer` instance.
    """

    def __init__(
        self,
        graph: nx.DiGraph,
        analyzer: GraphAnalyzer,
    ) -> None:
        self._graph = graph
        self._analyzer = analyzer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(
        self,
        case: Case,
        transactions: Sequence[NormalizedTransaction],
        fraud_results: Optional[Sequence[DetectionResult]] = None,
    ) -> RetrievedContext:
        """Pull all relevant graph context for a case.

        Args:
            case:           The investigation case.
            transactions:   Full transaction dataset (used to filter
                            case-related records).
            fraud_results:  Optional fraud results for enrichment.

        Returns:
            A :class:`RetrievedContext` populated with graph intelligence.
        """
        ctx = RetrievedContext(
            case_id=case.case_id,
            primary_entity=case.primary_entity,
        )

        # 1. Retrieve entity metrics
        ctx.entity_metrics = self._retrieve_entity_metrics(case)

        # 2. Retrieve community membership
        ctx.community = self._retrieve_community(case)

        # 3. Retrieve suspicious paths
        ctx.suspicious_paths = self._retrieve_paths(case)

        # 4. Detect cycles
        ctx.cycles = self._retrieve_cycles(case)

        # 5. Filter related transactions
        ctx.related_transactions = self._retrieve_related_transactions(
            case, transactions
        )

        # 6. Compute entity risk scores
        ctx.entity_risk_scores = self._retrieve_entity_risk_scores(case)

        # 7. Identify high-risk neighbors
        ctx.high_risk_neighbors = self._retrieve_high_risk_neighbors(case)

        logger.info(
            "Retrieved context for case %s: %d metrics, %d paths, %d cycles, %d txns",
            case.case_id,
            len(ctx.entity_metrics),
            len(ctx.suspicious_paths),
            len(ctx.cycles),
            len(ctx.related_transactions),
        )
        return ctx

    def retrieve_case_entities(self, case: Case) -> list[str]:
        """Return all entity IDs involved in a case.

        Args:
            case: The investigation case.

        Returns:
            Combined list of primary + related entities.
        """
        entities = [case.primary_entity] + list(case.related_entities)
        return sorted(set(entities))

    def retrieve_related_transactions(
        self,
        case: Case,
        transactions: Sequence[NormalizedTransaction],
    ) -> list[NormalizedTransaction]:
        """Filter transactions to only those involving case entities.

        Args:
            case:         The investigation case.
            transactions: Full transaction dataset.

        Returns:
            Filtered list of transactions.
        """
        return self._retrieve_related_transactions(case, transactions)

    def retrieve_graph_metrics(self, case: Case) -> dict[str, float]:
        """Return graph metrics for the primary entity.

        Args:
            case: The investigation case.

        Returns:
            Dictionary of metric name -> value.
        """
        metrics = self._analyzer.compute_centrality()
        for entity_id, m in metrics.items():
            if entity_id == case.primary_entity:
                return {
                    "degree_centrality": m.degree_centrality,
                    "pagerank": m.pagerank,
                    "in_degree": float(m.in_degree),
                    "out_degree": float(m.out_degree),
                    "community_id": float(m.community_id),
                }
        return {}

    # ------------------------------------------------------------------
    # Internal retrieval methods
    # ------------------------------------------------------------------

    def _retrieve_entity_metrics(self, case: Case) -> list[NodeMetrics]:
        """Compute node metrics for all case-related entities."""
        all_metrics = self._analyzer.compute_centrality()
        entities = set(self.retrieve_case_entities(case))
        return [m for eid, m in all_metrics.items() if eid in entities]

    def _retrieve_community(self, case: Case) -> Optional[CommunityResult]:
        """Find the community that the primary entity belongs to."""
        communities = self._analyzer.detect_communities()
        for comm in communities:
            if case.primary_entity in comm.member_entities:
                return comm
        return None

    def _retrieve_paths(self, case: Case) -> list[PathResult]:
        """Find suspicious shortest paths between case entities."""
        paths: list[PathResult] = []
        entities = self.retrieve_case_entities(case)

        for i, src in enumerate(entities):
            for tgt in entities[i + 1:]:
                if src == tgt:
                    continue
                if src not in self._graph or tgt not in self._graph:
                    continue
                try:
                    sp = nx.shortest_path(self._graph, src, tgt)
                    # Compute total amount along the path
                    total_amount = 0.0
                    max_fraud = 0.0
                    for u, v in zip(sp[:-1], sp[1:]):
                        edge_data = self._graph.get_edge_data(u, v, default={})
                        total_amount += edge_data.get("total_amount", 0.0)
                        max_fraud = max(max_fraud, edge_data.get("fraud_score", 0.0))

                    paths.append(
                        PathResult(
                            source=src,
                            target=tgt,
                            path_nodes=sp,
                            path_length=len(sp) - 1,
                            total_amount=total_amount,
                            max_fraud_score=min(max_fraud, 1.0),
                        )
                    )
                except nx.NetworkXNoPath:
                    continue

        return paths

    def _retrieve_cycles(self, case: Case) -> list[list[str]]:
        """Detect circular flows involving the primary entity."""
        if case.primary_entity not in self._graph:
            return []
        try:
            cycles = [
                c
                for c in nx.simple_cycles(self._graph)
                if case.primary_entity in c and len(c) <= 6
            ]
            return cycles[:10]  # cap at 10 cycles
        except Exception:
            return []

    def _retrieve_related_transactions(
        self,
        case: Case,
        transactions: Sequence[NormalizedTransaction],
    ) -> list[NormalizedTransaction]:
        """Filter transactions to those involving case entities."""
        case_txn_ids = set(case.transactions)
        entities = set(self.retrieve_case_entities(case))

        result = []
        for txn in transactions:
            if txn.transaction_id in case_txn_ids:
                result.append(txn)
            elif (
                txn.sender_entity_id in entities
                or txn.receiver_entity_id in entities
            ):
                result.append(txn)
        return result

    def _retrieve_entity_risk_scores(self, case: Case) -> list[EntityRiskScore]:
        """Compute entity risk scores for case entities."""
        all_scores = self._analyzer.compute_entity_risk_scores()
        entities = set(self.retrieve_case_entities(case))
        return [s for s in all_scores if s.entity_id in entities]

    def _retrieve_high_risk_neighbors(self, case: Case) -> list[str]:
        """Identify high-risk neighbors of the primary entity."""
        if case.primary_entity not in self._graph:
            return []

        neighbors = set()
        for n in self._graph.successors(case.primary_entity):
            neighbors.add(n)
        for n in self._graph.predecessors(case.primary_entity):
            neighbors.add(n)

        # Filter to those with high fraud scores on edges
        high_risk = []
        for neighbor in neighbors:
            edge_data = self._graph.get_edge_data(
                case.primary_entity, neighbor, default={}
            )
            rev_data = self._graph.get_edge_data(
                neighbor, case.primary_entity, default={}
            )
            max_fraud = max(
                edge_data.get("fraud_score", 0.0),
                rev_data.get("fraud_score", 0.0),
            )
            if max_fraud >= 0.3:
                high_risk.append(neighbor)

        return sorted(high_risk)
