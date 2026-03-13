"""
FinSentry - Pipeline Orchestration Service
===============================================

Manages in-memory application state and orchestrates the full
FinSentry pipeline across API requests.

Functions
---------
run_investigation_pipeline
    Fraud detection → Graph building → Graph analysis → Case building.
generate_sar_for_case
    SAR report generation for a specific case.
validate_sar_report
    Compliance validation of a SAR report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

from case_builder.builder import CaseBuilder
from case_builder.models import Case
from compliance_validator.models import ValidationResult
from compliance_validator.validator import ComplianceValidator
from fraud_detection.detector import FraudDetector
from fraud_detection.models import DetectionResult, RiskLevel
from graph_engine.analyzer import GraphAnalyzer
from graph_engine.builder import GraphBuilder
from ingestion.schema import NormalizedTransaction
from sar_generator.generator import SARGenerator
from sar_generator.models import SARReport
from utils.logging import get_logger

logger = get_logger("api.services.pipeline")


# ---------------------------------------------------------------------------
# In-memory application state
# ---------------------------------------------------------------------------


@dataclass
class AppState:
    """In-memory state shared across API requests.

    Attributes:
        transactions:   Loaded and normalised transactions.
        detector:       Trained FraudDetector instance.
        fraud_results:  Results from last detection run.
        graph:          Transaction NetworkX DiGraph.
        analyzer:       GraphAnalyzer wrapping the graph.
        cases:          Generated investigation cases (keyed by case_id).
        sar_reports:    Generated SAR reports (keyed by report_id).
    """

    transactions: list[NormalizedTransaction] = field(default_factory=list)
    detector: Optional[FraudDetector] = None
    fraud_results: list[DetectionResult] = field(default_factory=list)
    graph: Optional[nx.DiGraph] = None
    analyzer: Optional[GraphAnalyzer] = None
    cases: dict[str, Case] = field(default_factory=dict)
    sar_reports: dict[str, SARReport] = field(default_factory=dict)


# Global singleton state
state = AppState()


def get_state() -> AppState:
    """Return the global application state."""
    return state


def reset_state() -> None:
    """Reset the global state (used in tests)."""
    global state
    state = AppState()


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def run_detection(
    contamination: float = 0.15,
    n_estimators: int = 100,
) -> list[DetectionResult]:
    """Train the FraudDetector on loaded transactions and score them.

    Args:
        contamination: IsolationForest contamination parameter.
        n_estimators:  Number of trees.

    Returns:
        List of DetectionResult.

    Raises:
        ValueError: If no transactions are loaded.
    """
    if not state.transactions:
        raise ValueError("No transactions loaded. Call /ingest first.")

    detector = FraudDetector(
        contamination=contamination,
        n_estimators=n_estimators,
        random_state=42,
    )
    detector.train(state.transactions)
    results = detector.predict(state.transactions)

    state.detector = detector
    state.fraud_results = results

    logger.info(
        "Detection complete: %d results (%d HIGH, %d MEDIUM, %d LOW)",
        len(results),
        sum(1 for r in results if r.fraud_score.risk_level == RiskLevel.HIGH),
        sum(1 for r in results if r.fraud_score.risk_level == RiskLevel.MEDIUM),
        sum(1 for r in results if r.fraud_score.risk_level == RiskLevel.LOW),
    )
    return results


def run_investigation_pipeline(
    fraud_threshold: float = 0.5,
) -> list[Case]:
    """Run the full investigation pipeline.

    Steps:
    1. Fraud detection (if not already done).
    2. Build transaction graph.
    3. Analyse graph (centrality, communities, cycles, risk scores).
    4. Build investigation cases.

    Args:
        fraud_threshold: Minimum fraud probability for case inclusion.

    Returns:
        List of generated Case objects.

    Raises:
        ValueError: If no transactions are loaded.
    """
    if not state.transactions:
        raise ValueError("No transactions loaded. Call /ingest first.")

    # 1. Ensure detection has been run
    if not state.fraud_results:
        run_detection()

    # 2. Build transaction graph
    fraud_score_map = {
        r.transaction_id: r.fraud_score.fraud_probability
        for r in state.fraud_results
    }
    builder = GraphBuilder(load_metadata=True)
    graph = builder.build_transaction_graph(
        state.transactions, fraud_score_map
    )
    state.graph = graph

    # 3. Analyse graph
    analyzer = GraphAnalyzer(graph)
    analyzer.compute_centrality()
    analyzer.detect_communities()
    analyzer.detect_cycles()
    entity_risk_scores = analyzer.compute_entity_risk_scores()
    state.analyzer = analyzer

    # 4. Build cases
    case_builder = CaseBuilder(fraud_threshold=fraud_threshold)
    cases = case_builder.build_cases(
        transactions=state.transactions,
        fraud_results=state.fraud_results,
        entity_risk_scores=entity_risk_scores,
        graph=graph,
    )

    state.cases = {c.case_id: c for c in cases}

    logger.info("Investigation pipeline complete: %d cases generated", len(cases))
    return cases


def generate_sar_for_case(case_id: str) -> SARReport:
    """Generate a SAR report for a specific investigation case.

    Args:
        case_id: The case ID to generate a report for.

    Returns:
        Generated SARReport.

    Raises:
        ValueError: If the case or required pipeline state is missing.
    """
    if case_id not in state.cases:
        raise ValueError(f"Case '{case_id}' not found.")
    if state.graph is None or state.analyzer is None:
        raise ValueError("Pipeline has not been run. Call /investigate first.")

    case = state.cases[case_id]
    generator = SARGenerator(state.graph, state.analyzer)
    report = generator.generate_sar(
        case=case,
        transactions=state.transactions,
        fraud_results=state.fraud_results,
    )

    state.sar_reports[report.report_id] = report
    logger.info("Generated SAR %s for case %s", report.report_id, case_id)
    return report


def validate_sar_report(report: SARReport) -> ValidationResult:
    """Validate a SAR report against compliance rules.

    Args:
        report: The SARReport to validate.

    Returns:
        ValidationResult with violations.
    """
    validator = ComplianceValidator()
    result = validator.validate(report)
    logger.info(
        "Validated SAR %s: valid=%s (%d errors, %d warnings)",
        report.report_id,
        result.is_valid,
        result.error_count,
        result.warning_count,
    )
    return result
