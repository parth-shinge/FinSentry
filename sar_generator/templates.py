"""
FinSentry - SAR Report Templates
=====================================

Provides template functions that render structured investigation context
into the narrative sections of a Suspicious Activity Report (SAR).

Each template function takes an :class:`~graph_rag.context_builder.InvestigationContext`
and a :class:`~case_builder.models.Case` and returns a formatted text block.

Templates
---------
* ``subject_information``         -- Who is being reported.
* ``suspicious_activity_description`` -- What was observed.
* ``transaction_evidence``        -- Supporting transaction details.
* ``risk_summary``                -- Overall risk assessment.
* ``recommended_action``          -- Suggested next steps.
"""

from __future__ import annotations

from case_builder.models import Case
from graph_rag.context_builder import InvestigationContext


# ---------------------------------------------------------------------------
# Template functions
# ---------------------------------------------------------------------------


def subject_information(ctx: InvestigationContext, case: Case) -> str:
    """Render the subject information section of a SAR.

    Describes the primary entity, related entities, and their roles.

    Args:
        ctx:  Investigation context with entity details.
        case: The investigation case.

    Returns:
        Formatted subject information text.
    """
    lines = [
        "SUBJECT INFORMATION",
        "=" * 40,
        f"Primary Subject Entity: {case.primary_entity}",
        f"Case Reference: {case.case_id}",
        f"Case Risk Score: {case.risk_score:.4f}",
        "",
    ]

    if case.related_entities:
        lines.append(f"Associated Entities ({len(case.related_entities)}):")
        for entity in case.related_entities[:15]:
            lines.append(f"  - {entity}")
        if len(case.related_entities) > 15:
            lines.append(f"  ... and {len(case.related_entities) - 15} more")
        lines.append("")

    lines.append("Entity Analysis:")
    lines.append(ctx.entities_involved)

    return "\n".join(lines)


def suspicious_activity_description(
    ctx: InvestigationContext, case: Case
) -> str:
    """Render the suspicious activity narrative.

    Combines transaction patterns, graph intelligence, and risk
    indicators into a cohesive description of suspicious behavior.

    Args:
        ctx:  Investigation context with pattern analysis.
        case: The investigation case.

    Returns:
        Formatted suspicious activity description.
    """
    lines = [
        "SUSPICIOUS ACTIVITY DESCRIPTION",
        "=" * 40,
        "",
        ctx.case_summary,
        "",
        "--- Transaction Patterns ---",
        ctx.suspicious_transactions,
        "",
        "--- Network Analysis ---",
        ctx.graph_patterns,
        "",
    ]

    # Add risk indicator narratives
    if case.risk_indicators:
        lines.append("--- Detected Risk Signals ---")
        for ri in case.risk_indicators:
            severity_label = ri.severity.upper()
            lines.append(f"  [{severity_label}] {ri.indicator_type}: {ri.description}")
        lines.append("")

    return "\n".join(lines)


def transaction_evidence(ctx: InvestigationContext, case: Case) -> str:
    """Render the transaction evidence section.

    Lists suspicious transactions with fraud scores, amounts, and
    jurisdictional details.

    Args:
        ctx:  Investigation context with transaction details.
        case: The investigation case.

    Returns:
        Formatted transaction evidence text.
    """
    lines = [
        "TRANSACTION EVIDENCE",
        "=" * 40,
        "",
        ctx.suspicious_transactions,
        "",
    ]

    # Detailed transaction list
    if case.fraud_scores:
        sorted_scores = sorted(
            case.fraud_scores.items(), key=lambda x: x[1], reverse=True
        )
        lines.append(f"Flagged Transactions ({len(sorted_scores)}):")
        for tid, score in sorted_scores[:20]:
            risk_label = (
                "HIGH" if score >= 0.7 else "MEDIUM" if score >= 0.3 else "LOW"
            )
            lines.append(f"  {tid}: probability={score:.4f} [{risk_label}]")
        if len(sorted_scores) > 20:
            lines.append(f"  ... and {len(sorted_scores) - 20} additional transactions")
        lines.append("")

    lines.append("Supporting Evidence:")
    lines.append(ctx.supporting_evidence)

    return "\n".join(lines)


def risk_summary(ctx: InvestigationContext, case: Case) -> str:
    """Render the risk assessment summary.

    Provides an overall assessment combining fraud scores, graph
    metrics, and risk indicators.

    Args:
        ctx:  Investigation context.
        case: The investigation case.

    Returns:
        Formatted risk assessment text.
    """
    lines = [
        "RISK ASSESSMENT",
        "=" * 40,
        "",
        f"Overall Case Risk Score: {case.risk_score:.4f}",
        "",
    ]

    # Risk level classification
    if case.risk_score >= 0.7:
        lines.append("Risk Classification: HIGH -- Immediate attention required.")
    elif case.risk_score >= 0.4:
        lines.append("Risk Classification: MEDIUM -- Enhanced monitoring recommended.")
    else:
        lines.append("Risk Classification: LOW -- Standard review cycle.")

    lines.append("")

    # Graph-derived risk metrics
    if case.graph_metrics:
        lines.append("Graph-Based Risk Metrics:")
        for metric, value in case.graph_metrics.items():
            lines.append(f"  {metric}: {value:.4f}")
        lines.append("")

    # Risk indicators
    lines.append(ctx.risk_indicators)

    return "\n".join(lines)


def recommended_action(ctx: InvestigationContext, case: Case) -> str:
    """Render the recommended action section.

    Suggests next steps based on the risk level, evidence, and
    graph analysis.

    Args:
        ctx:  Investigation context.
        case: The investigation case.

    Returns:
        Formatted recommended action text.
    """
    lines = [
        "RECOMMENDED ACTIONS",
        "=" * 40,
        "",
    ]

    if case.risk_score >= 0.7:
        lines.extend([
            "1. File SAR immediately with FinCEN.",
            "2. Escalate to senior compliance officer for review.",
            "3. Place enhanced monitoring on all associated accounts.",
            "4. Coordinate with law enforcement if criminal activity is suspected.",
            "5. Preserve all transaction records and communication logs.",
        ])
    elif case.risk_score >= 0.4:
        lines.extend([
            "1. Complete enhanced due diligence on primary subject.",
            "2. Review all related entity accounts for additional activity.",
            "3. Schedule follow-up review within 30 days.",
            "4. Consider placing transaction monitoring alerts on accounts.",
        ])
    else:
        lines.extend([
            "1. Continue standard monitoring.",
            "2. Flag for periodic review in next quarterly cycle.",
            "3. No immediate regulatory action required.",
        ])

    # Entity-specific actions
    if case.related_entities:
        lines.append("")
        lines.append(
            f"Note: {len(case.related_entities)} related entities should be "
            f"included in the investigation scope."
        )

    return "\n".join(lines)
