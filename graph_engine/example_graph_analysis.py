#!/usr/bin/env python
"""
FinSentry AI - Example Graph Analysis Script
===============================================

Demonstrates the end-to-end graph intelligence pipeline:

1. Load and normalise transactions from the sample CSV.
2. Train the FraudDetector and score every transaction.
3. Build a directed transaction graph with fraud scores.
4. Run graph intelligence analysis (centrality, communities, cycles).
5. Compute entity risk scores.
6. Print the most suspicious entities and detected cycles.

Usage::

    cd d:\\FinSentry
    python graph_engine/example_graph_analysis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.project_path import PROJECT_ROOT  # noqa: E402
from fraud_detection.detector import FraudDetector  # noqa: E402
from graph_engine.builder import GraphBuilder  # noqa: E402
from graph_engine.analyzer import GraphAnalyzer  # noqa: E402
from ingestion.loader import TransactionLoader  # noqa: E402
from utils.logging import get_logger  # noqa: E402

logger = get_logger("graph_engine.example")


def main() -> None:
    """Run the example graph intelligence pipeline."""
    data_file = _PROJECT_ROOT / "data" / "sample_transactions.csv"
    if not data_file.exists():
        print(f"ERROR: Sample dataset not found at {data_file}")
        sys.exit(1)

    print("=" * 70)
    print("  FinSentry AI - Graph Intelligence Engine Example")
    print("=" * 70)
    print()

    # -- 1. Load transactions -----------------------------------------------
    loader = TransactionLoader()
    loader.load_csv(data_file)
    transactions = loader.normalized
    print(f"  Loaded {len(transactions)} normalised transactions")
    print()

    # -- 2. Train Fraud Detector & score transactions -----------------------
    print("  Training FraudDetector...")
    detector = FraudDetector(contamination=0.15, n_estimators=100, random_state=42)
    detector.train(transactions)
    results = detector.predict(transactions)

    fraud_scores = {
        r.transaction_id: r.fraud_score.fraud_probability for r in results
    }
    print(f"  Scored {len(fraud_scores)} transactions")
    print()

    # -- 3. Build transaction graph ------------------------------------------
    print("  Building transaction graph...")
    builder = GraphBuilder()
    graph = builder.build_transaction_graph(transactions, fraud_scores)
    print(f"  Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print()

    # -- 4. Run graph analysis -----------------------------------------------
    analyzer = GraphAnalyzer(graph)

    print("  Computing centrality metrics...")
    centrality = analyzer.compute_centrality()

    print("  Detecting communities...")
    communities = analyzer.detect_communities()
    print(f"  Found {len(communities)} communities")

    print("  Detecting cycles (circular money flows)...")
    cycles = analyzer.detect_cycles(max_length=6)
    print(f"  Found {len(cycles)} cycles")

    print("  Detecting suspicious chains...")
    chains = analyzer.detect_suspicious_chains(min_amount=10000.0, min_hops=3)
    print(f"  Found {len(chains)} suspicious chains")
    print()

    # -- 5. Compute entity risk scores --------------------------------------
    print("  Computing entity risk scores...")
    risk_scores = analyzer.compute_entity_risk_scores(fraud_scores)
    print()

    # -- 6. Print results ----------------------------------------------------
    top_n = 10
    print(f"  -- Top {min(top_n, len(risk_scores))} Most Suspicious Entities --")
    print(
        f"  {'Rank':<5} {'Entity ID':<12} {'Centrality':>11} "
        f"{'CommFraud':>10} {'HRNeighb':>9} {'Cycles':>7} {'Risk':>8}"
    )
    print("  " + "-" * 66)

    for rank, rs in enumerate(risk_scores[:top_n], start=1):
        print(
            f"  {rank:<5} {rs.entity_id:<12} "
            f"{rs.centrality_score:>11.6f} "
            f"{rs.community_fraud_density:>10.4f} "
            f"{rs.high_risk_neighbor_count:>9d} "
            f"{rs.cycle_participation_count:>7d} "
            f"{rs.overall_risk_score:>8.4f}"
        )

    print()

    # -- 7. Print detected cycles -------------------------------------------
    if cycles:
        print(f"  -- Detected Cycles (showing first {min(5, len(cycles))}) --")
        for i, cycle in enumerate(cycles[:5]):
            print(f"    Cycle {i + 1}: {' → '.join(cycle)} → {cycle[0]}")
        print()

    # -- 8. Print suspicious chains -----------------------------------------
    if chains:
        print(f"  -- Suspicious Chains (showing first {min(5, len(chains))}) --")
        for i, chain in enumerate(chains[:5]):
            print(
                f"    Chain {i + 1}: {' → '.join(chain.path_nodes)} "
                f"(${chain.total_amount:,.2f}, "
                f"max fraud: {chain.max_fraud_score:.4f})"
            )
        print()

    # -- 9. Community summary ------------------------------------------------
    if communities:
        print("  -- Community Summary --")
        for c in communities:
            print(
                f"    Community {c.community_id}: "
                f"{c.member_count} members, "
                f"fraud density: {c.avg_fraud_density:.4f}, "
                f"high-risk: {c.high_risk_count}"
            )
        print()

    # -- 10. Visualization export demo ---------------------------------------
    viz_data = analyzer.export_graph_for_visualization()
    print(
        f"  Visualization export: {len(viz_data['nodes'])} nodes, "
        f"{len(viz_data['edges'])} edges"
    )
    print()

    print("=" * 70)
    print("  Graph intelligence analysis complete [OK]")
    print("=" * 70)


if __name__ == "__main__":
    main()
