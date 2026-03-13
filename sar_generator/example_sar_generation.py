#!/usr/bin/env python
"""
FinSentry - Example SAR Generation Script
===============================================

Demonstrates the full end-to-end pipeline:

1. Load and normalise transactions (ingestion)
2. Run fraud detection
3. Build transaction graph and analyse it
4. Build investigation cases
5. Generate SAR report for the highest-risk case

Usage::

    cd d:\\FinSentry
    python sar_generator/example_sar_generation.py
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

from case_builder.builder import CaseBuilder
from fraud_detection.detector import FraudDetector
from graph_engine.analyzer import GraphAnalyzer
from graph_engine.builder import GraphBuilder
from ingestion.loader import TransactionLoader
from sar_generator.generator import SARGenerator
from utils.logging import get_logger

logger = get_logger("sar_generator.example")


def main() -> None:
    """Run the full pipeline and generate a SAR report."""
    data_file = _PROJECT_ROOT / "data" / "sample_transactions.csv"
    if not data_file.exists():
        print(f"ERROR: Sample dataset not found at {data_file}")
        sys.exit(1)

    print("=" * 70)
    print("  FinSentry - SAR Report Generation Example")
    print("=" * 70)
    print()

    # -- 1. Ingestion ------------------------------------------------------
    print("  [1/5] Loading and normalising transactions...")
    loader = TransactionLoader()
    loader.load_csv(data_file)
    transactions = loader.normalized
    print(f"        {len(transactions)} transactions loaded")
    print()

    # -- 2. Fraud Detection ------------------------------------------------
    print("  [2/5] Running fraud detection...")
    detector = FraudDetector(contamination=0.15, n_estimators=50, random_state=42)
    detector.train(transactions)
    fraud_results = detector.predict(transactions)
    high_risk = sum(
        1 for r in fraud_results if r.fraud_score.fraud_probability >= 0.7
    )
    print(f"        {high_risk} high-risk transactions detected")
    print()

    # -- 3. Graph Analysis -------------------------------------------------
    print("  [3/5] Building and analysing transaction graph...")
    # GraphBuilder expects fraud_scores as dict[str, float]
    fraud_score_map = {
        r.transaction_id: r.fraud_score.fraud_probability
        for r in fraud_results
    }
    gb = GraphBuilder()
    graph = gb.build_transaction_graph(transactions, fraud_score_map)
    analyzer = GraphAnalyzer(graph)
    entity_scores = analyzer.compute_entity_risk_scores()
    print(f"        Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print()

    # -- 4. Case Building --------------------------------------------------
    print("  [4/5] Building investigation cases...")
    case_builder = CaseBuilder(fraud_threshold=0.4)
    cases = case_builder.build_cases(
        transactions, fraud_results, entity_scores, graph
    )
    print(f"        {len(cases)} cases generated")
    print()

    if not cases:
        print("  No cases generated. Try lowering the fraud threshold.")
        return

    # -- 5. SAR Generation -------------------------------------------------
    top_case = cases[0]
    print(f"  [5/5] Generating SAR for highest-risk case: {top_case.case_id}")
    print(f"        Primary entity: {top_case.primary_entity}")
    print(f"        Risk score: {top_case.risk_score:.4f}")
    print()

    sar_gen = SARGenerator(graph, analyzer)
    report = sar_gen.generate_sar(top_case, transactions, fraud_results)

    # Print the report
    print("-" * 70)
    print(f"  SAR Report: {report.report_id}")
    print(f"  Case:       {report.case_id}")
    print(f"  Subject:    {report.subject_entity}")
    print(f"  Date:       {report.report_date.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Risk Score: {report.risk_score:.4f}")
    print(f"  Amount:     ${report.total_amount:,.2f}")
    print(f"  Entities:   {len(report.entities_involved)}")
    print(f"  Jurisdictions: {', '.join(report.jurisdictions)}")
    print("-" * 70)
    print()

    # Print key sections
    print("  -- RISK ASSESSMENT --")
    for line in report.risk_assessment.split("\n")[:15]:
        print(f"  {line}")
    print()

    print("  -- RECOMMENDED ACTIONS --")
    for line in report.recommended_action.split("\n")[:10]:
        print(f"  {line}")
    print()

    print("=" * 70)
    print("  SAR generation complete [OK]")
    print("=" * 70)


if __name__ == "__main__":
    main()
