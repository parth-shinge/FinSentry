"""
FinSentry AI - Graph Analyzer
================================

Performs graph intelligence analysis on the financial transaction network.

Algorithms
----------
* **Centrality** — Degree centrality and PageRank.
* **Community detection** — Greedy modularity optimisation.
* **Cycle detection** — Simple cycle enumeration up to a configurable
  length (identifies circular money flows).
* **Shortest path** — Dijkstra shortest path between entities.
* **Suspicious chain detection** — Multi-hop, timestamp-ordered paths
  with high aggregate amounts (laundering chain detection).
* **High-risk subgraph extraction** — Subgraph of edges whose fraud
  score exceeds a threshold.
* **Entity risk scoring** — Composite risk score combining centrality,
  community fraud density, neighbor risk, and cycle participation.

Usage::

    from graph_engine.analyzer import GraphAnalyzer

    analyzer = GraphAnalyzer(graph)
    centrality = analyzer.compute_centrality()
    communities = analyzer.detect_communities()
    risk_scores = analyzer.compute_entity_risk_scores()
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import networkx as nx  # type: ignore[import-untyped]
from networkx.algorithms.community import greedy_modularity_communities  # type: ignore[import-untyped]

from graph_engine.models import (
    CommunityResult,
    EntityRiskScore,
    NodeMetrics,
    PathResult,
)
from utils.logging import get_logger

logger = get_logger("graph_engine.analyzer")


class GraphAnalyzer:
    """Graph intelligence engine for financial transaction networks.

    Wraps a ``networkx.DiGraph`` and exposes algorithms for centrality
    analysis, community detection, cycle detection, suspicious chain
    identification, and entity risk scoring.

    Args:
        graph: A directed graph built by :class:`GraphBuilder`.
    """

    def __init__(self, graph: nx.DiGraph) -> None:
        self._graph: nx.DiGraph = graph
        self._centrality: Dict[str, NodeMetrics] = {}
        self._communities: List[CommunityResult] = []
        self._node_community_map: Dict[str, int] = {}
        self._cycles: List[List[str]] = []

    # ------------------------------------------------------------------
    # Centrality
    # ------------------------------------------------------------------

    def compute_centrality(self) -> Dict[str, NodeMetrics]:
        """Compute degree centrality and PageRank for all nodes.

        Returns:
            Mapping of entity_id → :class:`NodeMetrics`.
        """
        if self._graph.number_of_nodes() == 0:
            logger.info("Empty graph — skipping centrality computation")
            return {}

        degree_cent: Dict[str, float] = dict(nx.degree_centrality(self._graph))
        pr: Dict[str, float] = dict(nx.pagerank(self._graph, weight="transaction_weight"))

        self._centrality = {}
        for node in list(self._graph.nodes):
            node_str: str = str(node)
            data: Dict[str, Any] = dict(self._graph.nodes[node_str])
            community_id: int = self._node_community_map.get(node_str, -1)
            self._centrality[node_str] = NodeMetrics(
                entity_id=node_str,
                node_type=str(data.get("entity_type", "unknown")),
                degree_centrality=float(round(float(degree_cent.get(node_str, 0.0)), 6)),
                pagerank=float(round(float(pr.get(node_str, 0.0)), 6)),
                in_degree=int(self._graph.in_degree(node_str)),
                out_degree=int(self._graph.out_degree(node_str)),
                community_id=community_id,
            )

        logger.info("Computed centrality for %d nodes", len(self._centrality))
        return self._centrality

    # ------------------------------------------------------------------
    # Community Detection
    # ------------------------------------------------------------------

    def detect_communities(self) -> List[CommunityResult]:
        """Detect communities using greedy modularity optimisation.

        Operates on the undirected view of the graph (required by the
        modularity algorithm).

        Returns:
            List of :class:`CommunityResult` objects.
        """
        if self._graph.number_of_nodes() == 0:
            logger.info("Empty graph — skipping community detection")
            return []

        undirected = self._graph.to_undirected()
        communities: Any = greedy_modularity_communities(undirected)

        self._communities = []
        self._node_community_map = {}

        for idx, community_set in enumerate(communities):
            members: List[str] = sorted(str(m) for m in community_set)
            for m in members:
                self._node_community_map[m] = idx

            # Compute fraud density for edges within the community
            edge_fraud_scores: List[float] = []
            for u in members:
                for v in members:
                    if self._graph.has_edge(u, v):
                        edge_data: Dict[str, Any] = dict(self._graph.edges[u, v])
                        edge_fraud_scores.append(float(edge_data.get("fraud_score", 0.0)))

            avg_fraud: float = (
                sum(edge_fraud_scores) / len(edge_fraud_scores) if edge_fraud_scores else 0.0
            )
            high_risk: int = sum(
                1
                for m in members
                if str(self._graph.nodes[m].get("risk_rating", "")) == "high"
            )

            self._communities.append(
                CommunityResult(
                    community_id=idx,
                    member_entities=members,
                    member_count=len(members),
                    avg_fraud_density=float(round(avg_fraud, 4)),
                    high_risk_count=high_risk,
                )
            )

        logger.info("Detected %d communities", len(self._communities))

        # Update community IDs in centrality if already computed
        for node_key, cid in self._node_community_map.items():
            if node_key in self._centrality:
                self._centrality[node_key].community_id = cid

        return self._communities

    # ------------------------------------------------------------------
    # Cycle Detection
    # ------------------------------------------------------------------

    def detect_cycles(self, max_length: int = 6) -> List[List[str]]:
        """Detect simple cycles (circular money flows) in the graph.

        Args:
            max_length: Maximum cycle length to consider.  Longer cycles
                        are filtered out.

        Returns:
            List of cycles, where each cycle is a list of entity IDs.
        """
        if self._graph.number_of_nodes() == 0:
            logger.info("Empty graph — skipping cycle detection")
            return []

        raw_cycles: Any = nx.simple_cycles(self._graph)
        all_cycles: List[List[str]] = [[str(n) for n in c] for c in raw_cycles]
        self._cycles = [c for c in all_cycles if len(c) <= max_length]

        logger.info(
            "Found %d cycles (max length %d, %d total)",
            len(self._cycles),
            max_length,
            len(all_cycles),
        )
        return self._cycles

    # ------------------------------------------------------------------
    # Shortest Path
    # ------------------------------------------------------------------

    def find_shortest_paths(
        self, source: str, target: str
    ) -> Optional[PathResult]:
        """Find the shortest path between two entities.

        Uses Dijkstra's algorithm with edge weight ``transaction_weight``.

        Args:
            source: Source entity ID.
            target: Target entity ID.

        Returns:
            A :class:`PathResult` if a path exists, otherwise ``None``.
        """
        if source not in self._graph or target not in self._graph:
            return None

        try:
            raw_path: Any = nx.shortest_path(
                self._graph, source, target, weight="transaction_weight"
            )
            path: List[str] = [str(n) for n in raw_path]
        except nx.NetworkXNoPath:
            return None

        total_amount: float = 0.0
        max_fraud: float = 0.0
        for i in range(len(path) - 1):
            edge: Dict[str, Any] = dict(self._graph.edges[path[i], path[i + 1]])
            total_amount += float(edge.get("amount", 0.0))
            max_fraud = max(max_fraud, float(edge.get("fraud_score", 0.0)))

        return PathResult(
            source=source,
            target=target,
            path_nodes=path,
            path_length=len(path) - 1,
            total_amount=float(round(total_amount, 2)),
            max_fraud_score=float(round(max_fraud, 4)),
        )

    # ------------------------------------------------------------------
    # Suspicious Chain Detection
    # ------------------------------------------------------------------

    def detect_suspicious_chains(
        self,
        min_amount: float = 10000.0,
        min_hops: int = 3,
    ) -> List[PathResult]:
        """Identify suspicious multi-hop transaction chains.

        A chain is suspicious when it spans at least ``min_hops`` hops,
        each edge carries at least ``min_amount``, and transactions are
        ordered by timestamp (layering pattern).

        Args:
            min_amount: Minimum amount per edge.
            min_hops:   Minimum number of hops in the chain.

        Returns:
            List of :class:`PathResult` for each suspicious chain.
        """
        if self._graph.number_of_nodes() == 0:
            return []

        chains: List[PathResult] = []

        # Start DFS from every node
        for raw_node in list(self._graph.nodes):
            start: str = str(raw_node)
            self._dfs_chains(
                current=start,
                path=[start],
                last_timestamp=None,
                total_amount=0.0,
                max_fraud=0.0,
                min_amount=min_amount,
                min_hops=min_hops,
                chains=chains,
                visited={start},
            )

        logger.info(
            "Detected %d suspicious chains (min_amount=%.0f, min_hops=%d)",
            len(chains),
            min_amount,
            min_hops,
        )
        return chains

    def _dfs_chains(
        self,
        current: str,
        path: List[str],
        last_timestamp: Optional[str],
        total_amount: float,
        max_fraud: float,
        min_amount: float,
        min_hops: int,
        chains: List[PathResult],
        visited: Set[str],
    ) -> None:
        """Recursive DFS for timestamp-ordered transaction chains."""
        # Record chain if it meets criteria
        if len(path) - 1 >= min_hops:
            chains.append(
                PathResult(
                    source=path[0],
                    target=path[-1],
                    path_nodes=list(path),
                    path_length=len(path) - 1,
                    total_amount=float(round(total_amount, 2)),
                    max_fraud_score=float(round(max_fraud, 4)),
                )
            )

        # Explore successors
        successors: List[str] = [str(n) for n in self._graph.successors(current)]
        for neighbor in successors:
            if neighbor in visited:
                continue

            edge: Dict[str, Any] = dict(self._graph.edges[current, neighbor])
            edge_amount: float = float(edge.get("amount", 0.0))
            edge_timestamp: str = str(edge.get("timestamp", ""))
            edge_fraud: float = float(edge.get("fraud_score", 0.0))

            # Enforce minimum amount per hop
            if edge_amount < min_amount:
                continue

            # Enforce timestamp ordering
            if last_timestamp is not None and edge_timestamp < last_timestamp:
                continue

            visited.add(neighbor)
            self._dfs_chains(
                current=neighbor,
                path=path + [neighbor],
                last_timestamp=edge_timestamp,
                total_amount=total_amount + edge_amount,
                max_fraud=max(max_fraud, edge_fraud),
                min_amount=min_amount,
                min_hops=min_hops,
                chains=chains,
                visited=visited,
            )
            visited.discard(neighbor)

    # ------------------------------------------------------------------
    # High-Risk Subgraph
    # ------------------------------------------------------------------

    def extract_high_risk_subgraph(
        self, threshold: float = 0.5
    ) -> nx.DiGraph:
        """Extract a subgraph containing only high fraud-score edges.

        Args:
            threshold: Minimum fraud score for an edge to be included.

        Returns:
            A new ``DiGraph`` containing only edges with
            ``fraud_score >= threshold`` and their incident nodes.
        """
        high_risk_edges: List[Any] = [
            (u, v, d)
            for u, v, d in self._graph.edges(data=True)
            if float(d.get("fraud_score", 0.0)) >= threshold
        ]

        subgraph: nx.DiGraph = nx.DiGraph()
        subgraph.add_edges_from(high_risk_edges)

        # Copy node attributes
        for node in list(subgraph.nodes):
            if node in self._graph.nodes:
                subgraph.nodes[node].update(self._graph.nodes[node])

        logger.info(
            "Extracted high-risk subgraph: %d nodes, %d edges (threshold=%.2f)",
            subgraph.number_of_nodes(),
            subgraph.number_of_edges(),
            threshold,
        )
        return subgraph

    # ------------------------------------------------------------------
    # Entity Risk Scoring
    # ------------------------------------------------------------------

    def compute_entity_risk_scores(
        self,
        fraud_scores: Optional[Dict[str, float]] = None,
    ) -> List[EntityRiskScore]:
        """Compute composite risk scores for all entities.

        Combines:
        * Centrality (degree + PageRank)
        * Community fraud density
        * High-risk neighbor count
        * Cycle participation count

        Each factor is normalised and weighted to produce an overall
        score in [0, 1].

        Args:
            fraud_scores: Optional transaction-level fraud scores for
                          enriching neighbor risk calculation.

        Returns:
            List of :class:`EntityRiskScore` sorted by risk (descending).
        """
        if self._graph.number_of_nodes() == 0:
            return []

        # Ensure centrality and communities are computed
        if not self._centrality:
            self.compute_centrality()
        if not self._communities:
            self.detect_communities()
        if not self._cycles:
            self.detect_cycles()

        fraud_scores = fraud_scores or {}

        # Build cycle participation map
        cycle_counts: Dict[str, int] = {}
        for cycle in self._cycles:
            for cnode in cycle:
                prev: int = cycle_counts.get(cnode, 0)
                cycle_counts[cnode] = prev + 1

        # Community fraud density map
        community_fraud: Dict[int, float] = {
            c.community_id: c.avg_fraud_density for c in self._communities
        }

        # Pre-compute max degree across graph
        max_neighbors: int = max(
            (int(self._graph.degree(n)) for n in self._graph.nodes),
            default=0,
        )

        # Pre-compute max cycle count
        max_cycles: int = max(cycle_counts.values(), default=1) if cycle_counts else 1

        results: List[EntityRiskScore] = []

        for raw_node in list(self._graph.nodes):
            node_str: str = str(raw_node)
            metrics: Optional[NodeMetrics] = self._centrality.get(node_str)
            if metrics is None:
                continue

            # 1. Centrality score (weighted combination)
            centrality_score: float = (
                0.4 * metrics.degree_centrality + 0.6 * metrics.pagerank
            )

            # 2. Community fraud density
            cid: int = self._node_community_map.get(node_str, -1)
            comm_fraud: float = community_fraud.get(cid, 0.0)

            # 3. High-risk neighbor count
            high_risk_neighbors: int = 0
            predecessors: List[str] = [str(p) for p in self._graph.predecessors(node_str)]
            for pred in predecessors:
                pred_edge: Dict[str, Any] = dict(self._graph.edges[pred, node_str])
                if float(pred_edge.get("fraud_score", 0.0)) >= 0.5:
                    high_risk_neighbors = high_risk_neighbors + 1
            successors: List[str] = [str(s) for s in self._graph.successors(node_str)]
            for succ in successors:
                succ_edge: Dict[str, Any] = dict(self._graph.edges[node_str, succ])
                if float(succ_edge.get("fraud_score", 0.0)) >= 0.5:
                    high_risk_neighbors = high_risk_neighbors + 1

            # 4. Cycle participation
            cycle_count: int = cycle_counts.get(node_str, 0)

            # Overall risk score: weighted combination, clamped to [0, 1]
            # Weights: centrality 20%, community fraud 30%,
            #          neighbor risk 25%, cycle participation 25%
            neighbor_norm: float = (
                float(high_risk_neighbors) / float(max_neighbors) if max_neighbors > 0 else 0.0
            )
            cycle_norm: float = (
                float(cycle_count) / float(max_cycles) if max_cycles > 0 else 0.0
            )

            overall: float = (
                0.20 * min(centrality_score * 10, 1.0)  # scale up centrality
                + 0.30 * min(comm_fraud, 1.0)
                + 0.25 * min(neighbor_norm, 1.0)
                + 0.25 * min(cycle_norm, 1.0)
            )
            overall = float(round(min(max(overall, 0.0), 1.0), 4))

            results.append(
                EntityRiskScore(
                    entity_id=node_str,
                    centrality_score=float(round(centrality_score, 6)),
                    community_fraud_density=float(round(comm_fraud, 4)),
                    high_risk_neighbor_count=high_risk_neighbors,
                    cycle_participation_count=cycle_count,
                    overall_risk_score=overall,
                    suspicious_paths=[],
                )
            )

        # Sort by risk descending
        results.sort(key=lambda r: r.overall_risk_score, reverse=True)

        logger.info("Computed risk scores for %d entities", len(results))
        return results

    # ------------------------------------------------------------------
    # Visualization Export
    # ------------------------------------------------------------------

    def export_graph_for_visualization(self) -> Dict[str, Any]:
        """Export graph data for visualization (Plotly / PyVis).

        Returns:
            A dict with ``nodes`` and ``edges`` lists suitable for
            front-end rendering.

            Each node includes: ``id``, ``label``, ``entity_type``,
            ``pagerank``, ``risk_score``.

            Each edge includes: ``source``, ``target``, ``amount``,
            ``fraud_score``.
        """
        nodes: List[Dict[str, Any]] = []
        for raw_node, data in self._graph.nodes(data=True):
            node_str: str = str(raw_node)
            metrics: Optional[NodeMetrics] = self._centrality.get(node_str)
            nodes.append(
                {
                    "id": node_str,
                    "label": str(data.get("name", node_str)),
                    "entity_type": str(data.get("entity_type", "unknown")),
                    "pagerank": metrics.pagerank if metrics else 0.0,
                    "risk_score": str(data.get("risk_rating", "unknown")),
                }
            )

        edges: List[Dict[str, Any]] = []
        for u, v, data in self._graph.edges(data=True):
            edges.append(
                {
                    "source": str(u),
                    "target": str(v),
                    "amount": float(data.get("amount", 0.0)),
                    "fraud_score": float(data.get("fraud_score", 0.0)),
                }
            )

        logger.info(
            "Exported %d nodes and %d edges for visualization",
            len(nodes),
            len(edges),
        )
        return {"nodes": nodes, "edges": edges}
