"""
FinSentry - Compliance Validation Rules
============================================

Rule-based validation engine for SAR reports.  Each rule is a callable
class that inspects a :class:`~sar_generator.models.SARReport` and
returns a list of :class:`~compliance_validator.models.RuleViolation`
objects (empty list if the report passes the rule).

Rules
-----
RequiredFieldRule
    Ensures mandatory fields are non-empty.
TransactionReferenceRule
    Validates that the report references at least one transaction.
EntityReferenceRule
    Validates that entity references are present and consistent.
NarrativeLengthRule
    Checks that the narrative sections meet minimum length requirements.
ReportStructureRule
    Validates overall report structural integrity.

Usage::

    from compliance_validator.rules import get_all_rules
    rules = get_all_rules()
    for rule in rules:
        violations = rule.check(report)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from compliance_validator.models import RuleViolation, Severity
from sar_generator.models import SARReport


# ---------------------------------------------------------------------------
# Abstract base rule
# ---------------------------------------------------------------------------


class ValidationRule(ABC):
    """Abstract base class for validation rules.

    Subclasses must implement :meth:`check`, which receives a
    :class:`SARReport` and returns zero or more :class:`RuleViolation`
    instances.
    """

    name: str = "BaseRule"

    @abstractmethod
    def check(self, report: SARReport) -> list[RuleViolation]:
        """Validate *report* and return any violations found."""
        ...


# ---------------------------------------------------------------------------
# Concrete rules
# ---------------------------------------------------------------------------


class RequiredFieldRule(ValidationRule):
    """Ensures mandatory SAR fields are non-empty.

    Checks that ``report_id``, ``case_id``, ``subject_entity``,
    ``suspicious_activity_description``, ``transaction_summary``,
    and ``risk_assessment`` are populated.
    """

    name = "RequiredFieldRule"

    #: Fields that must have a non-empty string value.
    REQUIRED_FIELDS: list[str] = [
        "report_id",
        "case_id",
        "subject_entity",
        "suspicious_activity_description",
        "transaction_summary",
        "risk_assessment",
    ]

    def check(self, report: SARReport) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        for field_name in self.REQUIRED_FIELDS:
            value = getattr(report, field_name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                violations.append(
                    RuleViolation(
                        rule_name=self.name,
                        severity=Severity.ERROR,
                        field=field_name,
                        message=f"Required field '{field_name}' is missing or empty.",
                    )
                )
        return violations


class TransactionReferenceRule(ValidationRule):
    """Validates that the SAR report references transactions.

    Checks that ``transaction_summary`` is non-empty and that
    ``total_amount`` is greater than zero.
    """

    name = "TransactionReferenceRule"

    def check(self, report: SARReport) -> list[RuleViolation]:
        violations: list[RuleViolation] = []

        if not report.transaction_summary.strip():
            violations.append(
                RuleViolation(
                    rule_name=self.name,
                    severity=Severity.ERROR,
                    field="transaction_summary",
                    message="Transaction summary is empty — no transaction references.",
                )
            )

        if report.total_amount <= 0:
            violations.append(
                RuleViolation(
                    rule_name=self.name,
                    severity=Severity.WARNING,
                    field="total_amount",
                    message=(
                        f"Total suspicious amount is {report.total_amount}. "
                        "Expected a positive value."
                    ),
                )
            )
        return violations


class EntityReferenceRule(ValidationRule):
    """Validates entity references in the SAR report.

    Checks that ``subject_entity`` is populated and that
    ``entities_involved`` includes at least one entity.
    """

    name = "EntityReferenceRule"

    def check(self, report: SARReport) -> list[RuleViolation]:
        violations: list[RuleViolation] = []

        if not report.subject_entity.strip():
            violations.append(
                RuleViolation(
                    rule_name=self.name,
                    severity=Severity.ERROR,
                    field="subject_entity",
                    message="Subject entity is missing.",
                )
            )

        if not report.entities_involved:
            violations.append(
                RuleViolation(
                    rule_name=self.name,
                    severity=Severity.WARNING,
                    field="entities_involved",
                    message="No additional entities listed in entities_involved.",
                )
            )
        return violations


class NarrativeLengthRule(ValidationRule):
    """Checks that narrative sections meet minimum length requirements.

    FinCEN guidance recommends that SAR narratives be sufficiently
    detailed.  This rule applies a configurable minimum word count to
    ``suspicious_activity_description`` and ``evidence_summary``.

    Args:
        min_description_words: Minimum words for the activity description.
        min_evidence_words:    Minimum words for the evidence summary.
    """

    name = "NarrativeLengthRule"

    def __init__(
        self,
        min_description_words: int = 10,
        min_evidence_words: int = 5,
    ) -> None:
        self.min_description_words = min_description_words
        self.min_evidence_words = min_evidence_words

    def check(self, report: SARReport) -> list[RuleViolation]:
        violations: list[RuleViolation] = []

        desc_words = len(report.suspicious_activity_description.split())
        if desc_words < self.min_description_words:
            violations.append(
                RuleViolation(
                    rule_name=self.name,
                    severity=Severity.WARNING,
                    field="suspicious_activity_description",
                    message=(
                        f"Suspicious activity description has {desc_words} words "
                        f"(minimum {self.min_description_words})."
                    ),
                )
            )

        evidence_words = len(report.evidence_summary.split())
        if evidence_words < self.min_evidence_words:
            violations.append(
                RuleViolation(
                    rule_name=self.name,
                    severity=Severity.WARNING,
                    field="evidence_summary",
                    message=(
                        f"Evidence summary has {evidence_words} words "
                        f"(minimum {self.min_evidence_words})."
                    ),
                )
            )
        return violations


class ReportStructureRule(ValidationRule):
    """Validates overall SAR report structural integrity.

    Checks that:
    - ``risk_score`` is within the valid [0, 1] range.
    - ``jurisdictions`` contains at least one entry.
    - ``recommended_action`` is populated.
    """

    name = "ReportStructureRule"

    def check(self, report: SARReport) -> list[RuleViolation]:
        violations: list[RuleViolation] = []

        if not (0.0 <= report.risk_score <= 1.0):
            violations.append(
                RuleViolation(
                    rule_name=self.name,
                    severity=Severity.ERROR,
                    field="risk_score",
                    message=(
                        f"Risk score {report.risk_score} is outside "
                        "the valid range [0, 1]."
                    ),
                )
            )

        if not report.jurisdictions:
            violations.append(
                RuleViolation(
                    rule_name=self.name,
                    severity=Severity.WARNING,
                    field="jurisdictions",
                    message="No jurisdictions listed in the report.",
                )
            )

        if not report.recommended_action.strip():
            violations.append(
                RuleViolation(
                    rule_name=self.name,
                    severity=Severity.WARNING,
                    field="recommended_action",
                    message="Recommended action is empty.",
                )
            )
        return violations


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------


def get_all_rules() -> list[ValidationRule]:
    """Return a list of all default validation rule instances."""
    return [
        RequiredFieldRule(),
        TransactionReferenceRule(),
        EntityReferenceRule(),
        NarrativeLengthRule(),
        ReportStructureRule(),
    ]
