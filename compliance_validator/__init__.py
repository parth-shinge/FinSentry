"""
FinSentry - Compliance Validator Package
=============================================

Rule-based validation engine for SAR reports, ensuring regulatory
compliance before filing.

Modules:
    models    -- Pydantic models (ValidationResult, RuleViolation).
    rules     -- Validation rule classes (RequiredFieldRule, etc.).
    validator -- ComplianceValidator (orchestrates rule execution).
"""

from compliance_validator.models import (
    RuleViolation,
    Severity,
    ValidationResult,
)
from compliance_validator.rules import (
    EntityReferenceRule,
    NarrativeLengthRule,
    ReportStructureRule,
    RequiredFieldRule,
    TransactionReferenceRule,
    ValidationRule,
)
from compliance_validator.validator import ComplianceValidator

__all__ = [
    "ComplianceValidator",
    "ValidationResult",
    "RuleViolation",
    "Severity",
    "ValidationRule",
    "RequiredFieldRule",
    "TransactionReferenceRule",
    "EntityReferenceRule",
    "NarrativeLengthRule",
    "ReportStructureRule",
]
