"""
FinSentry - Compliance Validator Data Models
=================================================

Pydantic models for SAR report validation results.

Models
------
RuleViolation
    A single validation rule failure with severity and details.
ValidationResult
    Complete validation outcome aggregating all violations and an
    overall pass/fail status.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity level for a rule violation.

    Values:
        ERROR:   Critical failure — report must not be filed.
        WARNING: Non-critical issue — report can be filed but should
                 be reviewed.
        INFO:    Advisory note — no action required.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class RuleViolation(BaseModel):
    """A single rule violation detected during SAR report validation.

    Attributes:
        rule_name:   Name of the validation rule that was violated.
        severity:    Severity of the violation (ERROR / WARNING / INFO).
        field:       The report field that triggered the violation, if
                     applicable.
        message:     Human-readable description of the violation.
    """

    rule_name: str
    severity: Severity = Severity.ERROR
    field: Optional[str] = None
    message: str = ""


class ValidationResult(BaseModel):
    """Aggregated result of validating a SAR report.

    Attributes:
        report_id:   The SAR report ID that was validated.
        is_valid:    ``True`` if no ERROR-level violations were found.
        violations:  List of all detected violations.
        validated_at: UTC timestamp when validation was performed.
        rules_checked: Number of validation rules that were evaluated.
    """

    report_id: str
    is_valid: bool = True
    violations: list[RuleViolation] = Field(default_factory=list)
    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    rules_checked: int = 0

    @property
    def error_count(self) -> int:
        """Number of ERROR-level violations."""
        return sum(1 for v in self.violations if v.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        """Number of WARNING-level violations."""
        return sum(1 for v in self.violations if v.severity == Severity.WARNING)
