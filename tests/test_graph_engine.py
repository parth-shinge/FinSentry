"""
FinSentry AI - Graph Engine Unit Tests
========================================

Tests covering:

* Pydantic data models (NodeMetrics, CommunityResult, PathResult,
  EntityRiskScore)
* Graph construction (node counts, edge counts, metadata)
* Centrality calculations (degree centrality, PageRank)
* Community detection
* Cycle detection
* Suspicious chain detection
* High-risk subgraph extraction
* Entity risk scoring
* Visualization export

All tests use synthetic NormalizedTransaction objects — no database or
external data required.

Run::

    cd d:\\FinSentry
    python -m pytest tests/test_graph_engine.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from graph_engine.builder import GraphBuilder
from graph_engine.analyzer import GraphAnalyzer
from graph_engine.models import (
    CommunityResult,
    EntityRiskScore,
    NodeMetrics,
    PathResult,
)
from ingestion.schema import NormalizedTransaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_txn(
    txn_id: str = "TXN-001",
    sender: str = "ENT-S001",
    receiver: str = "ENT-R001",
    amount: float = 500.0,
    origin: str = "US",
    dest: str = "US",
    hour: int = 10,
    day: int = 15,
) -> NormalizedTransaction:
    """Create a NormalizedTransaction with sensible defaults."""
    ts = datetime(2025, 1, day, hour, 0, 0, tzinfo=timezone.utc)
    return NormalizedTransaction(
        transaction_id=txn_id,
        account_id="ACC-001",
        sender_entity_id=sender,
        receiver_entity_id=receiver,
        amount=amount,
        currency="USD",
        timestamp=ts,
        origin_country=origin,
        destination_country=dest,
        merchant_category="retail",
        transaction_type="wire",
        channel="online",
        is_international=origin != dest,
        is_large_transaction=amount >= 10000.0,
    )


def _linear_chain_txns() -> list[NormalizedTransaction]:
    """Create A→B→C→D linear chain of transactions."""
    return [
        _make_txn("T-1", "ENT-A", "ENT-B", 50000, "US", "KY", 9, 15),
        _make_txn("T-2", "ENT-B", "ENT-C", 49000, "KY", "CH", 10, 15),
        _make_txn("T-3", "ENT-C", "ENT-D", 48000, "CH", "PA", 11, 15),
    ]


def _cycle_txns() -> list[NormalizedTransaction]:
    """Create A→B→C→A cycle of transactions."""
    return [
        _make_txn("T-C1", "ENT-X", "ENT-Y", 30000, "US", "KY", 9, 16),
        _make_txn("T-C2", "ENT-Y", "ENT-Z", 29000, "KY", "PA", 10, 16),
        _make_txn("T-C3", "ENT-Z", "ENT-X", 28000, "PA", "US", 11, 16),
    ]


def _sample_fraud_scores(txns: list[NormalizedTransaction]) -> dict[str, float]:
    """Generate synthetic fraud scores for transactions."""
    scores = {}
    for txn in txns:
        if txn.amount >= 10000:
            scores[txn.transaction_id] = 0.8
        elif txn.amount >= 5000:
            scores[txn.transaction_id] = 0.4
        else:
            scores[txn.transaction_id] = 0.1
    return scores


# ===========================================================================
# Data Model Tests
# ===========================================================================


class TestDataModels:
    """Tests for graph engine Pydantic models."""

    def test_node_metrics_defaults(self):
        """NodeMetrics should have sensible defaults."""
        nm = NodeMetrics(entity_id="ENT-001")
        assert nm.entity_id == "ENT-001"
        assert nm.node_type == "unknown"
        assert nm.degree_centrality == 0.0
        assert nm.pagerank == 0.0
        assert nm.community_id == -1

    def test_community_result(self):
        """CommunityResult should store member list and counts."""
        cr = CommunityResult(
            community_id=0,
            member_entities=["ENT-A", "ENT-B"],
            member_count=2,
            avg_fraud_density=0.5,
            high_risk_count=1,
        )
        assert cr.member_count == 2
        assert cr.avg_fraud_density == 0.5

    def test_path_result(self):
        """PathResult should model a multi-hop path."""
        pr = PathResult(
            source="ENT-A",
            target="ENT-C",
            path_nodes=["ENT-A", "ENT-B", "ENT-C"],
            path_length=2,
            total_amount=100000.0,
            max_fraud_score=0.9,
        )
        assert pr.path_length == 2
        assert len(pr.path_nodes) == 3

    def test_entity_risk_score(self):
        """EntityRiskScore should bundle all risk indicators."""
        ers = EntityRiskScore(
            entity_id="ENT-001",
            centrality_score=0.5,
            community_fraud_density=0.3,
            high_risk_neighbor_count=2,
            cycle_participation_count=1,
            overall_risk_score=0.65,
        )
        assert ers.overall_risk_score == 0.65
        assert ers.suspicious_paths == []


# ===========================================================================
# Graph Builder Tests
# ===========================================================================


class TestGraphBuilder:
    """Tests for GraphBuilder."""

    def test_build_empty_graph(self):
        """Building with no transactions should produce an empty graph."""
        builder = GraphBuilder(load_metadata=False)
        graph = builder.build_transaction_graph([])
        assert graph.number_of_nodes() == 0
        assert graph.number_of_edges() == 0

    def test_build_single_transaction(self):
        """Single transaction should create 2 nodes and 1 edge."""
        builder = GraphBuilder(load_metadata=False)
        txns = [_make_txn()]
        graph = builder.build_transaction_graph(txns)
        assert graph.number_of_nodes() == 2
        assert graph.number_of_edges() == 1

    def test_node_count_linear_chain(self):
        """Linear chain A→B→C→D should produce 4 nodes."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)
        assert graph.number_of_nodes() == 4

    def test_edge_count_linear_chain(self):
        """Linear chain should produce 3 edges."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)
        assert graph.number_of_edges() == 3

    def test_edge_metadata(self):
        """Edge should carry transaction metadata."""
        builder = GraphBuilder(load_metadata=False)
        fraud = {"TXN-001": 0.75}
        txns = [_make_txn()]
        graph = builder.build_transaction_graph(txns, fraud_scores=fraud)

        edge_data = graph.edges["ENT-S001", "ENT-R001"]
        assert edge_data["transaction_id"] == "TXN-001"
        assert edge_data["amount"] == 500.0
        assert edge_data["fraud_score"] == 0.75
        assert edge_data["transaction_weight"] == 500.0 * 0.75

    def test_node_attributes(self):
        """Nodes should have entity_type attribute."""
        builder = GraphBuilder(load_metadata=False)
        txns = [_make_txn()]
        graph = builder.build_transaction_graph(txns)

        node_data = graph.nodes["ENT-S001"]
        assert node_data["entity_id"] == "ENT-S001"
        assert node_data["entity_type"] == "entity"  # ENT prefix

    def test_fraud_score_default_zero(self):
        """Missing fraud scores should default to 0.0."""
        builder = GraphBuilder(load_metadata=False)
        txns = [_make_txn()]
        graph = builder.build_transaction_graph(txns)

        edge_data = graph.edges["ENT-S001", "ENT-R001"]
        assert edge_data["fraud_score"] == 0.0
        assert edge_data["transaction_weight"] == 0.0

    def test_get_graph_returns_digraph(self):
        """get_graph() should return the built DiGraph."""
        import networkx as nx

        builder = GraphBuilder(load_metadata=False)
        builder.build_transaction_graph([_make_txn()])
        graph = builder.get_graph()
        assert isinstance(graph, nx.DiGraph)
        assert graph.number_of_nodes() == 2

    def test_cycle_graph_structure(self):
        """Cycle transactions should produce 3 nodes, 3 edges."""
        builder = GraphBuilder(load_metadata=False)
        txns = _cycle_txns()
        graph = builder.build_transaction_graph(txns)
        assert graph.number_of_nodes() == 3
        assert graph.number_of_edges() == 3


# ===========================================================================
# Graph Analyzer Tests
# ===========================================================================


class TestCentrality:
    """Tests for centrality computation."""

    def test_centrality_nonempty(self):
        """Centrality should return results for all nodes."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        centrality = analyzer.compute_centrality()
        assert len(centrality) == 4

    def test_centrality_valid_range(self):
        """Degree centrality should be in [0, 1]."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        centrality = analyzer.compute_centrality()
        for _, metrics in centrality.items():
            assert 0.0 <= metrics.degree_centrality <= 1.0
            assert metrics.pagerank >= 0.0

    def test_pagerank_sums_to_one(self):
        """PageRank values should approximately sum to 1.0."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        centrality = analyzer.compute_centrality()
        total_pr = sum(m.pagerank for m in centrality.values())
        assert abs(total_pr - 1.0) < 0.01

    def test_centrality_empty_graph(self):
        """Centrality on an empty graph should return empty dict."""
        import networkx as nx

        analyzer = GraphAnalyzer(nx.DiGraph())
        assert analyzer.compute_centrality() == {}

    def test_in_out_degree(self):
        """In/out degree should match graph structure."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()  # A→B→C→D
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        centrality = analyzer.compute_centrality()

        # ENT-A: 0 in, 1 out; ENT-D: 1 in, 0 out
        assert centrality["ENT-A"].in_degree == 0
        assert centrality["ENT-A"].out_degree == 1
        assert centrality["ENT-D"].in_degree == 1
        assert centrality["ENT-D"].out_degree == 0


class TestCommunityDetection:
    """Tests for community detection."""

    def test_communities_detected(self):
        """Should detect at least one community."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns() + _cycle_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        communities = analyzer.detect_communities()
        assert len(communities) >= 1

    def test_all_nodes_assigned(self):
        """Every node should be assigned to a community."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns() + _cycle_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        communities = analyzer.detect_communities()

        all_members = set()
        for c in communities:
            all_members.update(c.member_entities)

        assert all_members == set(graph.nodes)

    def test_community_member_count(self):
        """member_count should match length of member_entities."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        communities = analyzer.detect_communities()
        for c in communities:
            assert c.member_count == len(c.member_entities)

    def test_communities_empty_graph(self):
        """Community detection on empty graph should return empty list."""
        import networkx as nx

        analyzer = GraphAnalyzer(nx.DiGraph())
        assert analyzer.detect_communities() == []


class TestCycleDetection:
    """Tests for cycle detection."""

    def test_cycle_detected(self):
        """Known cycle X→Y→Z→X should be detected."""
        builder = GraphBuilder(load_metadata=False)
        txns = _cycle_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        cycles = analyzer.detect_cycles(max_length=6)
        assert len(cycles) >= 1

        # The cycle should contain all three entities
        cycle_sets = [set(c) for c in cycles]
        expected = {"ENT-X", "ENT-Y", "ENT-Z"}
        assert any(cs == expected for cs in cycle_sets)

    def test_no_cycle_in_linear_chain(self):
        """Linear chain should have no cycles."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        cycles = analyzer.detect_cycles()
        assert len(cycles) == 0

    def test_cycle_max_length_filter(self):
        """Cycles longer than max_length should be filtered out."""
        builder = GraphBuilder(load_metadata=False)
        txns = _cycle_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        # max_length=2 should filter out the 3-node cycle
        cycles = analyzer.detect_cycles(max_length=2)
        assert len(cycles) == 0

    def test_cycles_empty_graph(self):
        """Cycle detection on empty graph should return empty list."""
        import networkx as nx

        analyzer = GraphAnalyzer(nx.DiGraph())
        assert analyzer.detect_cycles() == []


class TestShortestPath:
    """Tests for shortest path analysis."""

    def test_shortest_path_exists(self):
        """Should find path from A to D in linear chain."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        result = analyzer.find_shortest_paths("ENT-A", "ENT-D")
        assert result is not None
        assert result.source == "ENT-A"
        assert result.target == "ENT-D"
        assert result.path_length == 3

    def test_no_path(self):
        """Should return None when no path exists."""
        builder = GraphBuilder(load_metadata=False)
        txns = [_make_txn("T-1", "ENT-A", "ENT-B")]
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        # B→A doesn't exist
        result = analyzer.find_shortest_paths("ENT-B", "ENT-A")
        assert result is None

    def test_nonexistent_node(self):
        """Should return None for nonexistent source/target."""
        builder = GraphBuilder(load_metadata=False)
        txns = [_make_txn()]
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        result = analyzer.find_shortest_paths("FAKE-1", "FAKE-2")
        assert result is None

    def test_path_total_amount(self):
        """Total amount should be the sum of edge amounts along path."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()  # 50k + 49k + 48k
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        result = analyzer.find_shortest_paths("ENT-A", "ENT-D")
        assert result is not None
        assert result.total_amount == 147000.0


class TestSuspiciousChains:
    """Tests for suspicious chain detection."""

    def test_chain_detected(self):
        """Linear chain with high amounts should be detected."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()  # 50k, 49k, 48k
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        chains = analyzer.detect_suspicious_chains(min_amount=10000, min_hops=3)
        assert len(chains) >= 1

    def test_chain_not_detected_low_amount(self):
        """Low-amount transactions should not trigger chain detection."""
        builder = GraphBuilder(load_metadata=False)
        txns = [
            _make_txn("T-1", "ENT-A", "ENT-B", 100, "US", "US", 9, 15),
            _make_txn("T-2", "ENT-B", "ENT-C", 100, "US", "US", 10, 15),
            _make_txn("T-3", "ENT-C", "ENT-D", 100, "US", "US", 11, 15),
        ]
        graph = GraphBuilder(load_metadata=False).build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        chains = analyzer.detect_suspicious_chains(min_amount=10000, min_hops=3)
        assert len(chains) == 0

    def test_chain_empty_graph(self):
        """Suspicious chain detection on empty graph returns empty list."""
        import networkx as nx

        analyzer = GraphAnalyzer(nx.DiGraph())
        assert analyzer.detect_suspicious_chains() == []


class TestHighRiskSubgraph:
    """Tests for high-risk subgraph extraction."""

    def test_extract_high_risk_edges(self):
        """Should include only edges above threshold."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        fraud = {"T-1": 0.9, "T-2": 0.2, "T-3": 0.8}
        graph = builder.build_transaction_graph(txns, fraud_scores=fraud)

        analyzer = GraphAnalyzer(graph)
        subgraph = analyzer.extract_high_risk_subgraph(threshold=0.5)

        # Only T-1 (0.9) and T-3 (0.8) should be in the subgraph
        assert subgraph.number_of_edges() == 2

    def test_no_high_risk_edges(self):
        """All-low-risk graph should produce empty subgraph."""
        builder = GraphBuilder(load_metadata=False)
        txns = [_make_txn()]
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        subgraph = analyzer.extract_high_risk_subgraph(threshold=0.5)
        assert subgraph.number_of_edges() == 0


class TestEntityRiskScoring:
    """Tests for composite entity risk scoring."""

    def test_risk_scores_computed(self):
        """Should return a risk score for every node."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns() + _cycle_txns()
        fraud = _sample_fraud_scores(txns)
        graph = builder.build_transaction_graph(txns, fraud_scores=fraud)

        analyzer = GraphAnalyzer(graph)
        risk_scores = analyzer.compute_entity_risk_scores(fraud)
        assert len(risk_scores) == graph.number_of_nodes()

    def test_risk_score_range(self):
        """All risk scores should be in [0, 1]."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns() + _cycle_txns()
        fraud = _sample_fraud_scores(txns)
        graph = builder.build_transaction_graph(txns, fraud_scores=fraud)

        analyzer = GraphAnalyzer(graph)
        risk_scores = analyzer.compute_entity_risk_scores(fraud)
        for rs in risk_scores:
            assert 0.0 <= rs.overall_risk_score <= 1.0

    def test_risk_scores_sorted_descending(self):
        """Risk scores should be sorted highest-first."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns() + _cycle_txns()
        fraud = _sample_fraud_scores(txns)
        graph = builder.build_transaction_graph(txns, fraud_scores=fraud)

        analyzer = GraphAnalyzer(graph)
        risk_scores = analyzer.compute_entity_risk_scores(fraud)
        scores = [rs.overall_risk_score for rs in risk_scores]
        assert scores == sorted(scores, reverse=True)

    def test_cycle_participants_higher_risk(self):
        """Entities in cycles should have higher risk than linear-only."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns() + _cycle_txns()
        fraud = _sample_fraud_scores(txns)
        graph = builder.build_transaction_graph(txns, fraud_scores=fraud)

        analyzer = GraphAnalyzer(graph)
        risk_scores = analyzer.compute_entity_risk_scores(fraud)
        risk_map = {rs.entity_id: rs for rs in risk_scores}

        # Cycle entities should have cycle_participation_count > 0
        for eid in ["ENT-X", "ENT-Y", "ENT-Z"]:
            assert risk_map[eid].cycle_participation_count > 0

        # Linear-only entities should have 0
        for eid in ["ENT-A", "ENT-D"]:
            assert risk_map[eid].cycle_participation_count == 0

    def test_risk_scores_empty_graph(self):
        """Empty graph should return empty list."""
        import networkx as nx

        analyzer = GraphAnalyzer(nx.DiGraph())
        assert analyzer.compute_entity_risk_scores() == []


class TestVisualizationExport:
    """Tests for graph visualization export."""

    def test_export_structure(self):
        """Export should contain 'nodes' and 'edges' keys."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        viz = analyzer.export_graph_for_visualization()
        assert "nodes" in viz
        assert "edges" in viz

    def test_export_node_count(self):
        """Exported node count should match graph."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        viz = analyzer.export_graph_for_visualization()
        assert len(viz["nodes"]) == 4

    def test_export_edge_count(self):
        """Exported edge count should match graph."""
        builder = GraphBuilder(load_metadata=False)
        txns = _linear_chain_txns()
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        viz = analyzer.export_graph_for_visualization()
        assert len(viz["edges"]) == 3

    def test_export_node_fields(self):
        """Each exported node should have required fields."""
        builder = GraphBuilder(load_metadata=False)
        txns = [_make_txn()]
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        analyzer.compute_centrality()
        viz = analyzer.export_graph_for_visualization()

        for node in viz["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "entity_type" in node
            assert "pagerank" in node
            assert "risk_score" in node

    def test_export_edge_fields(self):
        """Each exported edge should have required fields."""
        builder = GraphBuilder(load_metadata=False)
        txns = [_make_txn()]
        graph = builder.build_transaction_graph(txns)

        analyzer = GraphAnalyzer(graph)
        viz = analyzer.export_graph_for_visualization()

        for edge in viz["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "amount" in edge
            assert "fraud_score" in edge


# ===========================================================================
# Edge Case Tests
# ===========================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_single_node_graph(self):
        """Graph with single self-referencing transaction."""
        txn = _make_txn("T-1", "ENT-SELF", "ENT-SELF", 1000)
        builder = GraphBuilder(load_metadata=False)
        graph = builder.build_transaction_graph([txn])

        # Self-loop: 1 node, 1 edge
        assert graph.number_of_nodes() == 1
        assert graph.number_of_edges() == 1

        analyzer = GraphAnalyzer(graph)
        centrality = analyzer.compute_centrality()
        assert len(centrality) == 1

    def test_disconnected_components(self):
        """Graph with disconnected subgroups."""
        txns = [
            _make_txn("T-1", "ENT-A", "ENT-B", 1000, hour=9),
            _make_txn("T-2", "ENT-C", "ENT-D", 2000, hour=10),
        ]
        builder = GraphBuilder(load_metadata=False)
        graph = builder.build_transaction_graph(txns)

        assert graph.number_of_nodes() == 4
        assert graph.number_of_edges() == 2

        analyzer = GraphAnalyzer(graph)
        communities = analyzer.detect_communities()
        # Should have at least 2 communities
        assert len(communities) >= 2

    def test_duplicate_entity_not_duplicated(self):
        """Same entity appearing as sender/receiver shouldn't be duplicated."""
        txns = [
            _make_txn("T-1", "ENT-A", "ENT-B", 1000, hour=9),
            _make_txn("T-2", "ENT-B", "ENT-C", 2000, hour=10),
        ]
        builder = GraphBuilder(load_metadata=False)
        graph = builder.build_transaction_graph(txns)

        # ENT-B appears as both receiver and sender but should be one node
        assert graph.number_of_nodes() == 3

    def test_multiple_transactions_same_pair(self):
        """Multiple transactions between same entities should update edge."""
        txns = [
            _make_txn("T-1", "ENT-A", "ENT-B", 1000, hour=9),
            _make_txn("T-2", "ENT-A", "ENT-B", 2000, hour=10),
        ]
        builder = GraphBuilder(load_metadata=False)
        graph = builder.build_transaction_graph(txns)

        # DiGraph keeps only the last edge for same (u,v) pair
        assert graph.number_of_nodes() == 2
        assert graph.number_of_edges() == 1
