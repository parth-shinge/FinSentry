"""
FinSentry AI - Context Builder
================================

Converts raw :class:`~graph_rag.retriever.RetrievedContext` into structured
text sections suitable for SAR report generation.

The builder transforms graph intelligence, fraud scores, and evidence into
human-readable narrative blocks that the :class:`~sar_generator.generator.SARGenerator`
can insert into SAR report templates.

Usage::

    from graph_rag.context_builder import ContextBuilder

    builder = ContextBuilder()
    sections = builder.build_context(retrieved_context, case)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from case_builder.models import Case
from graph_rag.retriever import RetrievedContext
from utils.logging import get_logger

logger = get_logger("graph_rag.context_builder")


# ---------------------------------------------------------------------------
# Structured context output
# ---------------------------------------------------------------------------


@dataclass
class InvestigationContext:
    """Structured narrative context for SAR generation.

    Each field contains a pre-formatted text block ready for insertion
    into a SAR report template.

    Attributes:
        case_summary:              High-level case overview.
        entities_involved:         Description of entities and their roles.
        suspicious_transactions:   Summary of suspicious transaction patterns.
        graph_patterns:            Graph-derived intelligence findings.
        risk_indicators:           List of detected risk signals.
        supporting_evidence:       Evidence items supporting the investigation.
    """

    case_summary: str = ""
    entities_involved: str = ""
    suspicious_transactions: str = ""
    graph_patterns: str = ""
    risk_indicators: str = ""
    supporting_evidence: str = ""


# ---------------------------------------------------------------------------
# Context Builder
# ---------------------------------------------------------------------------


class ContextBuilder:
    """Builds structured narrative context from retrieved graph intelligence.

    Converts raw metrics, paths, and cycles into human-readable text
    sections for SAR report generation.
    """

    def build_context(
        self,
        retrieved: RetrievedContext,
        case: Case,
    ) -> InvestigationContext:
        """Build a full investigation context from retrieved data and case.

        Args:
            retrieved: Raw graph context from :class:`GraphRetriever`.
            case:      The investigation case.

        Returns:
            An :class:`InvestigationContext` with formatted text blocks.
        """
        ctx = InvestigationContext(
            case_summary=self._build_case_summary(case),
            entities_involved=self._build_entities_section(retrieved, case),
            suspicious_transactions=self._build_transactions_section(retrieved, case),
            graph_patterns=self._build_graph_patterns_section(retrieved),
            risk_indicators=self._build_risk_indicators_section(case),
            supporting_evidence=self._build_evidence_section(case),
        )

        logger.info("Built investigation context for case %s", case.case_id)
        return ctx

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_case_summary(self, case: Case) -> str:
        """Generate a high-level case summary."""
        lines = [
            f"Investigation Case {case.case_id}",
            f"Primary Subject: {case.primary_entity}",
            f"Overall Risk Score: {case.risk_score:.2f}",
            f"Total Transactions Under Review: {len(case.transactions)}",
            f"Related Entities: {len(case.related_entities)}",
            f"Evidence Items: {len(case.evidence)}",
            f"Risk Indicators: {len(case.risk_indicators)}",
        ]

        # Highest fraud score
        if case.fraud_scores:
            max_fraud = max(case.fraud_scores.values())
            lines.append(f"Peak Fraud Probability: {max_fraud:.4f}")

        return "\n".join(lines)

    def _build_entities_section(
        self, retrieved: RetrievedContext, case: Case
    ) -> str:
        """Describe entities involved and their graph metrics."""
        lines = [f"Primary Entity: {case.primary_entity}"]

        if case.related_entities:
            lines.append(
                f"Related Entities ({len(case.related_entities)}): "
                + ", ".join(case.related_entities[:10])
            )

        # Entity metrics from graph
        for m in retrieved.entity_metrics:
            lines.append(
                f"  {m.entity_id}: degree_centrality={m.degree_centrality:.4f}, "
                f"pagerank={m.pagerank:.4f}, "
                f"in={m.in_degree}, out={m.out_degree}, "
                f"community={m.community_id}"
            )

        # High-risk neighbors
        if retrieved.high_risk_neighbors:
            lines.append(
                f"High-Risk Neighbors: "
                + ", ".join(retrieved.high_risk_neighbors[:10])
            )

        return "\n".join(lines)

    def _build_transactions_section(
        self, retrieved: RetrievedContext, case: Case
    ) -> str:
        """Summarize suspicious transactions."""
        lines = [f"Transactions Under Review: {len(case.transactions)}"]

        if case.fraud_scores:
            avg_fraud = sum(case.fraud_scores.values()) / len(case.fraud_scores)
            lines.append(f"Average Fraud Probability: {avg_fraud:.4f}")

        # Show top suspicious transactions
        sorted_scores = sorted(
            case.fraud_scores.items(), key=lambda x: x[1], reverse=True
        )
        for tid, score in sorted_scores[:5]:
            lines.append(f"  {tid}: fraud_probability={score:.4f}")

        # Transaction details from retrieved context
        if retrieved.related_transactions:
            total_amount = sum(t.amount for t in retrieved.related_transactions)
            intl_count = sum(
                1 for t in retrieved.related_transactions if t.is_international
            )
            currencies = set(t.currency for t in retrieved.related_transactions)
            countries = set()
            for t in retrieved.related_transactions:
                countries.add(t.origin_country)
                countries.add(t.destination_country)

            lines.append(f"Total Transaction Value: ${total_amount:,.2f}")
            lines.append(f"International Transactions: {intl_count}")
            lines.append(f"Currencies: {', '.join(sorted(currencies))}")
            lines.append(f"Jurisdictions: {', '.join(sorted(countries))}")

        return "\n".join(lines)

    def _build_graph_patterns_section(self, retrieved: RetrievedContext) -> str:
        """Describe graph-derived patterns."""
        lines = ["Graph Intelligence Findings:"]

        # Community membership
        if retrieved.community:
            comm = retrieved.community
            lines.append(
                f"Community {comm.community_id}: "
                f"{comm.member_count} members, "
                f"avg fraud density={comm.avg_fraud_density:.4f}, "
                f"high-risk members={comm.high_risk_count}"
            )

        # Suspicious paths
        if retrieved.suspicious_paths:
            lines.append(f"Suspicious Paths ({len(retrieved.suspicious_paths)}):")
            for path in retrieved.suspicious_paths[:5]:
                lines.append(
                    f"  {path.source} -> {path.target}: "
                    f"{path.path_length} hops, "
                    f"${path.total_amount:,.2f}, "
                    f"max_fraud={path.max_fraud_score:.4f}"
                )

        # Cycles
        if retrieved.cycles:
            lines.append(f"Circular Flows ({len(retrieved.cycles)}):")
            for cycle in retrieved.cycles[:5]:
                lines.append(f"  {' -> '.join(cycle)} -> {cycle[0]}")

        # Entity risk scores
        if retrieved.entity_risk_scores:
            lines.append("Entity Risk Scores:")
            sorted_scores = sorted(
                retrieved.entity_risk_scores,
                key=lambda s: s.overall_risk_score,
                reverse=True,
            )
            for ers in sorted_scores[:5]:
                lines.append(
                    f"  {ers.entity_id}: "
                    f"risk={ers.overall_risk_score:.4f}, "
                    f"centrality={ers.centrality_score:.4f}, "
                    f"cycles={ers.cycle_participation_count}"
                )

        return "\n".join(lines)

    def _build_risk_indicators_section(self, case: Case) -> str:
        """Format risk indicators."""
        if not case.risk_indicators:
            return "No risk indicators detected."

        lines = [f"Risk Indicators ({len(case.risk_indicators)}):"]
        for ri in case.risk_indicators:
            lines.append(
                f"  [{ri.severity.upper()}] {ri.indicator_type}: {ri.description}"
            )
        return "\n".join(lines)

    def _build_evidence_section(self, case: Case) -> str:
        """Format supporting evidence."""
        if not case.evidence:
            return "No supporting evidence collected."

        lines = [f"Supporting Evidence ({len(case.evidence)}):"]
        for ev in case.evidence:
            lines.append(f"  [{ev.evidence_type}] {ev.description}")
            if ev.related_transactions:
                lines.append(
                    f"    Transactions: {', '.join(ev.related_transactions[:5])}"
                )
            if ev.related_entities:
                lines.append(
                    f"    Entities: {', '.join(ev.related_entities[:5])}"
                )
        return "\n".join(lines)
