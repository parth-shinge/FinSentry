"""
FinSentry AI - SAR Report Generator
======================================

Generates Suspicious Activity Reports (SARs) from investigation cases
and graph-derived context.

The generator orchestrates the full SAR creation pipeline:

1. **Retrieve** graph context via :class:`~graph_rag.retriever.GraphRetriever`.
2. **Build** structured narrative context via
   :class:`~graph_rag.context_builder.ContextBuilder`.
3. **Render** SAR sections using templates from
   :mod:`sar_generator.templates`.
4. **Assemble** the final :class:`SARReport`.

Usage::

    from sar_generator.generator import SARGenerator

    generator = SARGenerator(graph, analyzer)
    report = generator.generate_sar(case, transactions)
"""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

import networkx as nx

from case_builder.models import Case
from fraud_detection.models import DetectionResult
from graph_engine.analyzer import GraphAnalyzer
from graph_rag.context_builder import ContextBuilder, InvestigationContext
from graph_rag.retriever import GraphRetriever
from ingestion.schema import NormalizedTransaction
from sar_generator import templates
from sar_generator.models import SARReport
from utils.logging import get_logger

logger = get_logger("sar_generator.generator")


class SARGenerator:
    """Generates Suspicious Activity Reports from investigation cases.

    Orchestrates graph retrieval, context building, and template rendering
    to produce a structured :class:`SARReport`.

    Args:
        graph:    Transaction NetworkX DiGraph.
        analyzer: A configured :class:`GraphAnalyzer` instance.
    """

    def __init__(
        self,
        graph: nx.DiGraph,
        analyzer: GraphAnalyzer,
    ) -> None:
        self._graph = graph
        self._analyzer = analyzer
        self._retriever = GraphRetriever(graph, analyzer)
        self._context_builder = ContextBuilder()

    def generate_sar(
        self,
        case: Case,
        transactions: Sequence[NormalizedTransaction],
        fraud_results: Optional[Sequence[DetectionResult]] = None,
    ) -> SARReport:
        """Generate a complete SAR report for an investigation case.

        Args:
            case:          The investigation case to report on.
            transactions:  Full transaction dataset.
            fraud_results: Optional fraud detection results for enrichment.

        Returns:
            A :class:`SARReport` populated with all sections.
        """
        # 1. Retrieve graph context
        retrieved = self._retriever.retrieve(case, transactions, fraud_results)

        # 2. Build investigation context
        ctx = self._context_builder.build_context(retrieved, case)

        # 3. Render SAR sections
        report = self._assemble_report(ctx, case, transactions)

        logger.info(
            "Generated SAR %s for case %s (risk=%.4f)",
            report.report_id,
            case.case_id,
            case.risk_score,
        )
        return report

    def generate_multiple(
        self,
        cases: Sequence[Case],
        transactions: Sequence[NormalizedTransaction],
        fraud_results: Optional[Sequence[DetectionResult]] = None,
    ) -> list[SARReport]:
        """Generate SAR reports for multiple cases.

        Args:
            cases:         Investigation cases.
            transactions:  Full transaction dataset.
            fraud_results: Optional fraud detection results.

        Returns:
            List of :class:`SARReport` instances.
        """
        reports = []
        for case in cases:
            report = self.generate_sar(case, transactions, fraud_results)
            reports.append(report)
        logger.info("Generated %d SAR reports", len(reports))
        return reports

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _assemble_report(
        self,
        ctx: InvestigationContext,
        case: Case,
        transactions: Sequence[NormalizedTransaction],
    ) -> SARReport:
        """Assemble a SARReport from rendered template sections."""
        report_id = f"SAR-{uuid.uuid4().hex[:8].upper()}"

        # Compute jurisdictions from case transactions
        case_txn_ids = set(case.transactions)
        jurisdictions: set[str] = set()
        total_amount = 0.0
        for txn in transactions:
            if txn.transaction_id in case_txn_ids:
                jurisdictions.add(txn.origin_country)
                jurisdictions.add(txn.destination_country)
                total_amount += txn.amount

        return SARReport(
            report_id=report_id,
            case_id=case.case_id,
            subject_entity=case.primary_entity,
            suspicious_activity_description=templates.suspicious_activity_description(ctx, case),
            transaction_summary=templates.transaction_evidence(ctx, case),
            evidence_summary=templates.subject_information(ctx, case),
            risk_assessment=templates.risk_summary(ctx, case),
            recommended_action=templates.recommended_action(ctx, case),
            entities_involved=[case.primary_entity] + list(case.related_entities),
            jurisdictions=sorted(jurisdictions),
            total_amount=total_amount,
            risk_score=case.risk_score,
        )
