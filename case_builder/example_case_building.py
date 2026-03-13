#!/usr/bin/env python
"""
FinSentry AI - Example Case Building Script
==============================================

Demonstrates the end-to-end investigation case building pipeline:

1. Load and normalise transactions from the sample CSV.
2. Train the FraudDetector and score every transaction.
3. Build a transaction graph and compute entity risk scores.
4. Build investigation cases from all detection outputs.
5. Print the highest-risk cases with evidence and risk indicators.

Usage::

    cd d:\\FinSentry
    python case_builder/example_case_building.py
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
from case_builder.builder import CaseBuilder  # noqa: E402
from fraud_detection.detector import FraudDetector  # noqa: E402
from graph_engine.builder import GraphBuilder  # noqa: E402
from graph_engine.analyzer import GraphAnalyzer  # noqa: E402
from ingestion.loader import TransactionLoader  # noqa: E402
from utils.logging import get_logger  # noqa: E402

logger = get_logger("case_builder.example")


def main() -> None:
    """Run the example investigation case building pipeline."""
    data_file = _PROJECT_ROOT / "data" / "sample_transactions.csv"
    if not data_file.exists():
        print(f"ERROR: Sample dataset not found at {data_file}")
        sys.exit(1)

    print("=" * 70)
    print("  FinSentry AI - Investigation Case Builder Example")
    print("=" * 70)
    print()

    # -- 1. Load transactions -----------------------------------------------
    loader = TransactionLoader()
    loader.load_csv(data_file)
    transactions = loader.normalized
    print(f"  Loaded {len(transactions)} normalised transactions")

    # -- 2. Fraud detection --------------------------------------------------
    print("  Training FraudDetector...")
    detector = FraudDetector(contamination=0.15, n_estimators=100, random_state=42)
    detector.train(transactions)
    fraud_results = detector.predict(transactions)

    fraud_scores = {
        r.transaction_id: r.fraud_score.fraud_probability for r in fraud_results
    }
    high_count = sum(1 for p in fraud_scores.values() if p >= 0.5)
    print(f"  Scored {len(fraud_scores)} transactions ({high_count} high-risk)")

    # -- 3. Graph analysis ---------------------------------------------------
    print("  Building transaction graph...")
    graph_builder = GraphBuilder()
    graph = graph_builder.build_transaction_graph(transactions, fraud_scores)
    print(f"  Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

    analyzer = GraphAnalyzer(graph)
    analyzer.compute_centrality()
    analyzer.detect_communities()
    analyzer.detect_cycles()
    entity_risk_scores = analyzer.compute_entity_risk_scores(fraud_scores)
    print(f"  Computed risk scores for {len(entity_risk_scores)} entities")
    print()

    # -- 4. Build investigation cases ----------------------------------------
    print("  Building investigation cases...")
    case_builder = CaseBuilder(fraud_threshold=0.5, high_value_threshold=10_000.0)
    cases = case_builder.build_cases(
        transactions=transactions,
        fraud_results=fraud_results,
        entity_risk_scores=entity_risk_scores,
        graph=graph,
    )
    print(f"  Built {len(cases)} investigation case(s)")
    print()

    # -- 5. Print case summaries ---------------------------------------------
    for i, case in enumerate(cases, start=1):
        print(f"  {'-' * 64}")
        print(f"  Case {i}: {case.case_id}")
        print(f"  {'-' * 64}")
        print(f"    Primary Entity   : {case.primary_entity}")
        print(f"    Related Entities : {len(case.related_entities)}")
        print(f"    Transactions     : {len(case.transactions)}")
        print(f"    Risk Score       : {case.risk_score:.4f}")
        print()

        if case.risk_indicators:
            print("    Risk Indicators:")
            for ri in case.risk_indicators:
                print(
                    f"      [{ri.severity.upper():>8}] "
                    f"{ri.indicator_type}: {ri.description}"
                )
            print()

        if case.evidence:
            print("    Evidence:")
            for ev in case.evidence:
                print(f"      • [{ev.evidence_type}] {ev.description}")
            print()

        if case.fraud_scores:
            avg_prob = sum(case.fraud_scores.values()) / len(case.fraud_scores)
            max_prob = max(case.fraud_scores.values())
            print(
                f"    Fraud Scores: avg={avg_prob:.4f}, "
                f"max={max_prob:.4f}, "
                f"txns={len(case.fraud_scores)}"
            )

        if case.graph_metrics:
            print("    Graph Metrics:")
            for key, val in case.graph_metrics.items():
                print(f"      {key}: {val:.4f}")

        print()

    print("=" * 70)
    print("  Investigation case building complete [OK]")
    print("=" * 70)


if __name__ == "__main__":
    main()
