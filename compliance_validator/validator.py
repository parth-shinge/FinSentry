"""
FinSentry - Compliance Validator
=====================================

Orchestrates validation of SAR reports against a configurable set of
compliance rules.

Classes
-------
ComplianceValidator
    Validates :class:`~sar_generator.models.SARReport` objects against
    all registered rules and returns structured
    :class:`~compliance_validator.models.ValidationResult` objects.

Usage::

    from compliance_validator.validator import ComplianceValidator
    from sar_generator.models import SARReport

    validator = ComplianceValidator()
    result = validator.validate(report)
    print(result.is_valid, result.error_count)
"""

from __future__ import annotations

from typing import Optional, Sequence

from compliance_validator.models import (
    RuleViolation,
    Severity,
    ValidationResult,
)
from compliance_validator.rules import ValidationRule, get_all_rules
from sar_generator.models import SARReport
from utils.logging import get_logger

logger = get_logger("compliance_validator.validator")


class ComplianceValidator:
    """Validates SAR reports against compliance rules.

    By default, all built-in rules are loaded.  Custom rule sets can be
    injected via the *rules* argument.

    Args:
        rules: Optional sequence of :class:`ValidationRule` instances
               to use.  If ``None``, the default rule set from
               :func:`get_all_rules` is used.

    Attributes:
        rules: The active list of validation rules.

    Usage::

        validator = ComplianceValidator()
        result = validator.validate(sar_report)
    """

    def __init__(
        self,
        rules: Optional[Sequence[ValidationRule]] = None,
    ) -> None:
        self.rules: list[ValidationRule] = (
            list(rules) if rules is not None else get_all_rules()
        )
        logger.info(
            "ComplianceValidator initialised with %d rules: %s",
            len(self.rules),
            [r.name for r in self.rules],
        )

    def validate(self, report: SARReport) -> ValidationResult:
        """Validate a single SAR report.

        Runs every registered rule and collects any violations.  The
        report is considered **invalid** if any ERROR-level violations
        are found.

        Args:
            report: The SAR report to validate.

        Returns:
            A :class:`ValidationResult` with all violations and an
            overall pass/fail status.
        """
        all_violations: list[RuleViolation] = []

        for rule in self.rules:
            try:
                violations = rule.check(report)
                all_violations.extend(violations)
            except Exception:
                logger.exception("Rule %s raised an exception", rule.name)
                all_violations.append(
                    RuleViolation(
                        rule_name=rule.name,
                        severity=Severity.ERROR,
                        message=f"Rule '{rule.name}' raised an unexpected error.",
                    )
                )

        has_errors = any(v.severity == Severity.ERROR for v in all_violations)

        result = ValidationResult(
            report_id=report.report_id,
            is_valid=not has_errors,
            violations=all_violations,
            rules_checked=len(self.rules),
        )

        logger.info(
            "Validated report %s: valid=%s (%d errors, %d warnings)",
            report.report_id,
            result.is_valid,
            result.error_count,
            result.warning_count,
        )
        return result

    def validate_batch(
        self,
        reports: Sequence[SARReport],
    ) -> list[ValidationResult]:
        """Validate a batch of SAR reports.

        Args:
            reports: Sequence of SAR reports to validate.

        Returns:
            A list of :class:`ValidationResult`, one per report.
        """
        results = [self.validate(r) for r in reports]
        valid_count = sum(1 for r in results if r.is_valid)
        logger.info(
            "Batch validation complete: %d/%d reports valid",
            valid_count,
            len(results),
        )
        return results
