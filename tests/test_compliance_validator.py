"""
FinSentry - Compliance Validator Unit Tests
================================================

Tests covering:

* RuleViolation and ValidationResult Pydantic models
* Each validation rule in isolation
* ComplianceValidator orchestration (single and batch)
* Edge cases (empty fields, boundary values, custom rules)

All tests use synthetic SARReport objects — no database or external
data required.

Run::

    cd /path/to/FinSentry
    python -m pytest tests/test_compliance_validator.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

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
    get_all_rules,
)
from compliance_validator.validator import ComplianceValidator
from sar_generator.models import SARReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_report(
    report_id: str = "SAR-001",
    case_id: str = "CASE-001",
) -> SARReport:
    """Create a fully populated, valid SAR report."""
    return SARReport(
        report_id=report_id,
        case_id=case_id,
        subject_entity="ENT-SUSPECT-001",
        suspicious_activity_description=(
            "The subject entity conducted multiple large wire transfers "
            "to offshore accounts in a pattern consistent with layering "
            "activity typically associated with money laundering schemes."
        ),
        transaction_summary=(
            "Five wire transfers totalling USD 250,000 were sent from "
            "account ACC-001 to accounts in the Cayman Islands."
        ),
        evidence_summary=(
            "Graph analysis revealed circular fund flows between three "
            "entities with high centrality scores and known offshore "
            "connections."
        ),
        risk_assessment=(
            "HIGH — elevated risk due to cross-border flows, circular "
            "patterns, and high-risk jurisdiction involvement."
        ),
        recommended_action=(
            "File SAR with FinCEN and escalate to the BSA Officer for "
            "immediate review."
        ),
        entities_involved=["ENT-SUSPECT-001", "ENT-R002", "ENT-R003"],
        jurisdictions=["US", "KY"],
        total_amount=250000.0,
        risk_score=0.92,
    )


def _make_minimal_report() -> SARReport:
    """Create a report with only required Pydantic defaults (mostly empty)."""
    return SARReport(
        report_id="SAR-EMPTY",
        case_id="CASE-EMPTY",
        subject_entity="",
    )


# ===========================================================================
# Model tests
# ===========================================================================


class TestRuleViolationModel:
    """Tests for the RuleViolation Pydantic model."""

    def test_basic_creation(self):
        v = RuleViolation(rule_name="TestRule", message="something wrong")
        assert v.rule_name == "TestRule"
        assert v.severity == Severity.ERROR
        assert v.message == "something wrong"
        assert v.field is None

    def test_severity_values(self):
        for sev in (Severity.ERROR, Severity.WARNING, Severity.INFO):
            v = RuleViolation(rule_name="R", severity=sev, message="m")
            assert v.severity == sev

    def test_field_assignment(self):
        v = RuleViolation(
            rule_name="R", field="transaction_summary", message="m"
        )
        assert v.field == "transaction_summary"


class TestValidationResultModel:
    """Tests for the ValidationResult Pydantic model."""

    def test_default_values(self):
        r = ValidationResult(report_id="SAR-001")
        assert r.is_valid is True
        assert r.violations == []
        assert r.rules_checked == 0

    def test_error_count_property(self):
        r = ValidationResult(
            report_id="SAR-001",
            violations=[
                RuleViolation(rule_name="A", severity=Severity.ERROR, message="x"),
                RuleViolation(rule_name="B", severity=Severity.WARNING, message="y"),
                RuleViolation(rule_name="C", severity=Severity.ERROR, message="z"),
            ],
        )
        assert r.error_count == 2

    def test_warning_count_property(self):
        r = ValidationResult(
            report_id="SAR-001",
            violations=[
                RuleViolation(rule_name="A", severity=Severity.WARNING, message="x"),
                RuleViolation(rule_name="B", severity=Severity.WARNING, message="y"),
            ],
        )
        assert r.warning_count == 2

    def test_validated_at_auto_set(self):
        r = ValidationResult(report_id="SAR-001")
        assert r.validated_at is not None
        assert r.validated_at.tzinfo is not None


# ===========================================================================
# Individual rule tests
# ===========================================================================


class TestRequiredFieldRule:
    """Tests for RequiredFieldRule."""

    def test_valid_report_no_violations(self):
        rule = RequiredFieldRule()
        violations = rule.check(_make_valid_report())
        assert violations == []

    def test_empty_subject_entity(self):
        report = _make_valid_report()
        report.subject_entity = ""
        rule = RequiredFieldRule()
        violations = rule.check(report)
        fields = [v.field for v in violations]
        assert "subject_entity" in fields

    def test_empty_description(self):
        report = _make_valid_report()
        report.suspicious_activity_description = ""
        rule = RequiredFieldRule()
        violations = rule.check(report)
        fields = [v.field for v in violations]
        assert "suspicious_activity_description" in fields

    def test_multiple_empty_fields(self):
        report = _make_minimal_report()
        rule = RequiredFieldRule()
        violations = rule.check(report)
        # subject_entity, suspicious_activity_description,
        # transaction_summary, risk_assessment should all fail
        assert len(violations) >= 4

    def test_all_violations_are_errors(self):
        report = _make_minimal_report()
        rule = RequiredFieldRule()
        violations = rule.check(report)
        assert all(v.severity == Severity.ERROR for v in violations)


class TestTransactionReferenceRule:
    """Tests for TransactionReferenceRule."""

    def test_valid_report_no_errors(self):
        rule = TransactionReferenceRule()
        violations = rule.check(_make_valid_report())
        # Valid report has summary and amount > 0, so no violations
        assert all(v.severity != Severity.ERROR for v in violations)

    def test_empty_transaction_summary(self):
        report = _make_valid_report()
        report.transaction_summary = ""
        rule = TransactionReferenceRule()
        violations = rule.check(report)
        error_fields = [v.field for v in violations if v.severity == Severity.ERROR]
        assert "transaction_summary" in error_fields

    def test_zero_total_amount_warning(self):
        report = _make_valid_report()
        report.total_amount = 0.0
        rule = TransactionReferenceRule()
        violations = rule.check(report)
        warning_fields = [v.field for v in violations if v.severity == Severity.WARNING]
        assert "total_amount" in warning_fields


class TestEntityReferenceRule:
    """Tests for EntityReferenceRule."""

    def test_valid_report_no_violations(self):
        rule = EntityReferenceRule()
        violations = rule.check(_make_valid_report())
        assert violations == []

    def test_empty_subject_entity(self):
        report = _make_valid_report()
        report.subject_entity = ""
        rule = EntityReferenceRule()
        violations = rule.check(report)
        error_fields = [v.field for v in violations if v.severity == Severity.ERROR]
        assert "subject_entity" in error_fields

    def test_empty_entities_involved_warning(self):
        report = _make_valid_report()
        report.entities_involved = []
        rule = EntityReferenceRule()
        violations = rule.check(report)
        warning_fields = [v.field for v in violations if v.severity == Severity.WARNING]
        assert "entities_involved" in warning_fields


class TestNarrativeLengthRule:
    """Tests for NarrativeLengthRule."""

    def test_valid_report_no_violations(self):
        rule = NarrativeLengthRule()
        violations = rule.check(_make_valid_report())
        assert violations == []

    def test_short_description_warning(self):
        report = _make_valid_report()
        report.suspicious_activity_description = "Too short."
        rule = NarrativeLengthRule(min_description_words=10)
        violations = rule.check(report)
        fields = [v.field for v in violations]
        assert "suspicious_activity_description" in fields

    def test_short_evidence_warning(self):
        report = _make_valid_report()
        report.evidence_summary = "Brief."
        rule = NarrativeLengthRule(min_evidence_words=5)
        violations = rule.check(report)
        fields = [v.field for v in violations]
        assert "evidence_summary" in fields

    def test_custom_thresholds(self):
        report = _make_valid_report()
        # With very low thresholds, even short text should pass
        rule = NarrativeLengthRule(min_description_words=1, min_evidence_words=1)
        violations = rule.check(report)
        assert violations == []

    def test_all_violations_are_warnings(self):
        report = _make_minimal_report()
        rule = NarrativeLengthRule()
        violations = rule.check(report)
        assert all(v.severity == Severity.WARNING for v in violations)


class TestReportStructureRule:
    """Tests for ReportStructureRule."""

    def test_valid_report_no_violations(self):
        rule = ReportStructureRule()
        violations = rule.check(_make_valid_report())
        assert violations == []

    def test_empty_jurisdictions_warning(self):
        report = _make_valid_report()
        report.jurisdictions = []
        rule = ReportStructureRule()
        violations = rule.check(report)
        fields = [v.field for v in violations]
        assert "jurisdictions" in fields

    def test_empty_recommended_action_warning(self):
        report = _make_valid_report()
        report.recommended_action = ""
        rule = ReportStructureRule()
        violations = rule.check(report)
        fields = [v.field for v in violations]
        assert "recommended_action" in fields


# ===========================================================================
# Rule registry tests
# ===========================================================================


class TestRuleRegistry:
    """Tests for the get_all_rules() registry function."""

    def test_returns_five_rules(self):
        rules = get_all_rules()
        assert len(rules) == 5

    def test_rule_names_unique(self):
        rules = get_all_rules()
        names = [r.name for r in rules]
        assert len(names) == len(set(names))

    def test_all_have_check_method(self):
        rules = get_all_rules()
        for rule in rules:
            assert callable(getattr(rule, "check", None))


# ===========================================================================
# ComplianceValidator tests
# ===========================================================================


class TestComplianceValidator:
    """Tests for ComplianceValidator orchestration."""

    def test_valid_report_passes(self):
        validator = ComplianceValidator()
        result = validator.validate(_make_valid_report())
        assert result.is_valid is True
        assert result.error_count == 0

    def test_invalid_report_fails(self):
        validator = ComplianceValidator()
        result = validator.validate(_make_minimal_report())
        assert result.is_valid is False
        assert result.error_count > 0

    def test_report_id_propagated(self):
        validator = ComplianceValidator()
        result = validator.validate(_make_valid_report("SAR-UNIQUE"))
        assert result.report_id == "SAR-UNIQUE"

    def test_rules_checked_count(self):
        validator = ComplianceValidator()
        result = validator.validate(_make_valid_report())
        assert result.rules_checked == 5

    def test_custom_rules(self):
        validator = ComplianceValidator(rules=[RequiredFieldRule()])
        result = validator.validate(_make_valid_report())
        assert result.rules_checked == 1

    def test_batch_validation(self):
        validator = ComplianceValidator()
        reports = [
            _make_valid_report(report_id="SAR-A"),
            _make_minimal_report(),
            _make_valid_report(report_id="SAR-B"),
        ]
        results = validator.validate_batch(reports)
        assert len(results) == 3
        assert results[0].is_valid is True
        assert results[1].is_valid is False
        assert results[2].is_valid is True

    def test_batch_empty(self):
        validator = ComplianceValidator()
        results = validator.validate_batch([])
        assert results == []

    def test_warnings_do_not_make_report_invalid(self):
        """A report with only WARNING-level violations should still be valid."""
        report = _make_valid_report()
        report.entities_involved = []  # WARNING from EntityReferenceRule
        report.jurisdictions = []      # WARNING from ReportStructureRule
        report.recommended_action = "" # WARNING from ReportStructureRule
        validator = ComplianceValidator()
        result = validator.validate(report)
        assert result.is_valid is True
        assert result.warning_count > 0

    def test_mixed_violations(self):
        """Both error and warning violations should be collected."""
        report = _make_valid_report()
        report.subject_entity = ""     # ERROR from RequiredFieldRule + EntityReferenceRule
        report.jurisdictions = []      # WARNING from ReportStructureRule
        validator = ComplianceValidator()
        result = validator.validate(report)
        assert result.is_valid is False
        assert result.error_count >= 1
        assert result.warning_count >= 1


class TestComplianceValidatorEdgeCases:
    """Edge case tests for ComplianceValidator."""

    def test_validator_with_no_rules(self):
        """Empty rule set should result in a valid report."""
        validator = ComplianceValidator(rules=[])
        result = validator.validate(_make_valid_report())
        assert result.is_valid is True
        assert result.rules_checked == 0
        assert result.violations == []

    def test_all_rules_produce_named_violations(self):
        """All violations should have a non-empty rule_name."""
        validator = ComplianceValidator()
        result = validator.validate(_make_minimal_report())
        for v in result.violations:
            assert v.rule_name, "Every violation must have a rule_name"

    def test_multiple_reports_independent(self):
        """Validating one report should not affect another."""
        validator = ComplianceValidator()
        r1 = validator.validate(_make_valid_report())
        r2 = validator.validate(_make_minimal_report())
        assert r1.is_valid is True
        assert r2.is_valid is False
