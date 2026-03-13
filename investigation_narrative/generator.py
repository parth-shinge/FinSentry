"""
FinSentry - Investigation Narrative Generator
===================================================

Generates human-readable investigation narratives from case data,
transaction patterns, and graph analysis results.

Produces a structured case summary text suitable for inclusion in
SAR reports, case files, and investigator briefings.

Usage::

    from investigation_narrative.generator import NarrativeGenerator

    gen = NarrativeGenerator()
    narrative = gen.generate_narrative(case, transactions, aml_patterns)
"""

from __future__ import annotations

from typing import Optional, Sequence

from case_builder.models import Case
from ingestion.schema import NormalizedTransaction
from utils.logging import get_logger

logger = get_logger("investigation_narrative.generator")


class InvestigationNarrative:
    """A generated investigation narrative for a case."""

    def __init__(
        self,
        case_id: str,
        entity_id: str,
        summary: str,
        activity_description: str,
        pattern_descriptions: list[str],
        jurisdictions: list[str],
        total_amount: float,
    ) -> None:
        self.case_id = case_id
        self.entity_id = entity_id
        self.summary = summary
        self.activity_description = activity_description
        self.pattern_descriptions = pattern_descriptions
        self.jurisdictions = jurisdictions
        self.total_amount = total_amount

    def to_text(self) -> str:
        """Render full narrative as text."""
        parts = [self.summary]
        if self.activity_description:
            parts.append(self.activity_description)
        for desc in self.pattern_descriptions:
            parts.append(desc)
        return " ".join(parts)


class NarrativeGenerator:
    """Generates investigation narratives from case and transaction data."""

    def generate_narrative(
        self,
        case: Case,
        transactions: Sequence[NormalizedTransaction],
        aml_patterns: Optional[list] = None,
    ) -> InvestigationNarrative:
        """Generate a narrative for a single investigation case.

        Args:
            case:          The investigation case.
            transactions:  Full transaction dataset.
            aml_patterns:  Optional detected AML patterns (PatternDetection objects).

        Returns:
            An :class:`InvestigationNarrative`.
        """
        case_txn_ids = set(case.transactions)
        case_txns = [t for t in transactions if t.transaction_id in case_txn_ids]

        # Compute jurisdictions
        jurisdictions: set[str] = set()
        total_amount = 0.0
        for t in case_txns:
            jurisdictions.add(t.origin_country)
            jurisdictions.add(t.destination_country)
            total_amount += t.amount

        cross_border = [t for t in case_txns if t.is_international]
        intermediary_countries = set()
        for t in cross_border:
            intermediary_countries.add(t.destination_country)

        # Build summary sentence
        summary = self._build_summary(
            case.primary_entity,
            case_txns,
            cross_border,
            sorted(intermediary_countries),
        )

        # Build activity description
        activity = self._build_activity_description(case, case_txns)

        # Build pattern descriptions from AML detections
        pattern_descs = self._build_pattern_descriptions(
            case.primary_entity, aml_patterns
        )

        narrative = InvestigationNarrative(
            case_id=case.case_id,
            entity_id=case.primary_entity,
            summary=summary,
            activity_description=activity,
            pattern_descriptions=pattern_descs,
            jurisdictions=sorted(jurisdictions),
            total_amount=round(total_amount, 2),
        )

        logger.info(
            "Generated narrative for case %s (entity %s)",
            case.case_id, case.primary_entity,
        )
        return narrative

    def generate_multiple(
        self,
        cases: Sequence[Case],
        transactions: Sequence[NormalizedTransaction],
        aml_patterns: Optional[list] = None,
    ) -> list[InvestigationNarrative]:
        """Generate narratives for multiple cases."""
        narratives = []
        for case in cases:
            # Filter AML patterns relevant to this case's entities
            relevant_patterns = None
            if aml_patterns:
                case_entities = {case.primary_entity} | set(case.related_entities)
                relevant_patterns = [
                    p for p in aml_patterns
                    if any(e in case_entities for e in getattr(p, "involved_entities", []))
                ]
            narrative = self.generate_narrative(case, transactions, relevant_patterns)
            narratives.append(narrative)
        return narratives

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        entity_id: str,
        case_txns: list[NormalizedTransaction],
        cross_border: list[NormalizedTransaction],
        intermediary_countries: list[str],
    ) -> str:
        """Build the opening summary sentence."""
        if cross_border and intermediary_countries:
            country_str = " and ".join(intermediary_countries[:3])
            if len(intermediary_countries) > 3:
                country_str += f" and {len(intermediary_countries) - 3} other jurisdiction(s)"
            return (
                f"Entity {entity_id} participated in multiple cross-border "
                f"transactions routed through intermediary entities in "
                f"{country_str} indicating potential layering activity."
            )

        if len(case_txns) >= 3:
            total = sum(t.amount for t in case_txns)
            return (
                f"Entity {entity_id} conducted {len(case_txns)} transactions "
                f"totaling ${total:,.2f} exhibiting suspicious patterns "
                f"warranting further investigation."
            )

        total = sum(t.amount for t in case_txns)
        return (
            f"Entity {entity_id} is associated with ${total:,.2f} in "
            f"suspicious transactions flagged for investigation."
        )

    def _build_activity_description(
        self,
        case: Case,
        case_txns: list[NormalizedTransaction],
    ) -> str:
        """Build description of the entity's suspicious activity."""
        parts: list[str] = []

        # High-value activity
        high_value = [t for t in case_txns if t.amount >= 10_000]
        if high_value:
            max_amt = max(t.amount for t in high_value)
            parts.append(
                f"The investigation identified {len(high_value)} high-value "
                f"transaction(s) with amounts up to ${max_amt:,.2f}."
            )

        # Risk indicators
        if case.risk_indicators:
            critical = [ri for ri in case.risk_indicators if ri.severity == "critical"]
            if critical:
                parts.append(
                    f"Critical risk indicators detected: "
                    f"{', '.join(ri.indicator_type.replace('_', ' ') for ri in critical)}."
                )

        # Related entities
        if case.related_entities:
            parts.append(
                f"The entity network involves {len(case.related_entities)} "
                f"related entities requiring coordinated review."
            )

        return " ".join(parts)

    def _build_pattern_descriptions(
        self,
        entity_id: str,
        aml_patterns: Optional[list],
    ) -> list[str]:
        """Build investigator-friendly descriptions from detected AML patterns."""
        if not aml_patterns:
            return []

        # Investigator-friendly templates per pattern type
        _TEMPLATES = {
            "structuring": (
                "This investigation identified structuring behavior where "
                "Entity {entity} executed multiple transactions just below "
                "reporting thresholds across accounts within a short timeframe."
            ),
            "layering": (
                "The analysis uncovered layering activity involving Entity "
                "{entity}, with funds routed through multiple intermediary "
                "accounts to obscure the origin and destination of proceeds."
            ),
            "round_tripping": (
                "Circular fund flows were detected involving Entity {entity}, "
                "where funds departed and ultimately returned to the same "
                "entity through a chain of intermediaries, a hallmark of "
                "round-tripping activity."
            ),
            "rapid_transfers": (
                "Entity {entity} executed a series of rapid successive "
                "transfers within a narrow time window, suggesting automated "
                "or coordinated movement of funds."
            ),
            "shell_company_clusters": (
                "Entity {entity} is connected to a cluster of entities "
                "exhibiting shell-company characteristics, including minimal "
                "transaction diversity and concentrated flows."
            ),
        }

        descriptions: list[str] = []
        for pattern in aml_patterns:
            ptype = getattr(pattern, "pattern_type", "unknown")
            confidence = getattr(pattern, "confidence", 0.0)
            severity = getattr(pattern, "severity", "medium")

            template = _TEMPLATES.get(ptype)
            if template:
                text = template.format(entity=entity_id)
                text += f" (severity: {severity}, confidence: {confidence:.0%})"
                descriptions.append(text)
            else:
                desc = getattr(pattern, "description", "")
                if desc:
                    descriptions.append(
                        f"AML pattern detected ({ptype}, severity: {severity}, "
                        f"confidence: {confidence:.0%}): {desc}"
                    )

        return descriptions
