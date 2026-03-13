"""
FinSentry AI - Case Builder Unit Tests
========================================

Tests covering:

* Pydantic data models (Case, Evidence, RiskIndicator)
* Case grouping and entity expansion
* Risk scoring computation
* Evidence generation
* Edge cases (no high-risk txns, single transaction, empty input)

All tests use synthetic NormalizedTransaction and DetectionResult
objects — no database or external data required.

Run::

    cd d:\\FinSentry
    python -m pytest tests/test_case_builder.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from case_builder.builder import CaseBuilder
from case_builder.models import Case, Evidence, RiskIndicator
from fraud_detection.models import DetectionResult, FraudScore, RiskLevel
from graph_engine.models import EntityRiskScore
from ingestion.schema import NormalizedTransaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_txn(
    txn_id: str = "TXN-001",
    sender: str = "ENT-S001",
    receiver: str = "ENT-R001",
    amount: float = 500.0,
    origin: str = "US",
    dest: str = "US",
    hour: int = 10,
    day: int = 15,
) -> NormalizedTransaction:
    """Create a NormalizedTransaction with sensible defaults."""
    ts = datetime(2025, 1, day, hour, 0, 0, tzinfo=timezone.utc)
    return NormalizedTransaction(
        transaction_id=txn_id,
        account_id="ACC-001",
        sender_entity_id=sender,
        receiver_entity_id=receiver,
        amount=amount,
        currency="USD",
        timestamp=ts,
        origin_country=origin,
        destination_country=dest,
        merchant_category="retail",
        transaction_type="wire",
        channel="online",
        is_international=origin != dest,
        is_large_transaction=amount >= 10000.0,
    )


def _make_detection(
    txn_id: str, fraud_prob: float
) -> DetectionResult:
    """Create a DetectionResult with a given fraud probability."""
    risk = FraudScore.classify_risk(fraud_prob)
    return DetectionResult(
        transaction_id=txn_id,
        features_used=["amount", "hour"],
        fraud_score=FraudScore(
            transaction_id=txn_id,
            fraud_probability=fraud_prob,
            anomaly_score=-0.1,
            risk_level=risk,
        ),
    )


def _make_entity_risk(
    entity_id: str,
    overall_risk: float = 0.5,
    centrality: float = 0.1,
    community_fraud: float = 0.3,
    cycle_count: int = 0,
) -> EntityRiskScore:
    """Create an EntityRiskScore with given values."""
    return EntityRiskScore(
        entity_id=entity_id,
        centrality_score=centrality,
        community_fraud_density=community_fraud,
        high_risk_neighbor_count=2,
        cycle_participation_count=cycle_count,
        overall_risk_score=overall_risk,
    )


# ===========================================================================
# Data Model Tests
# ===========================================================================


class TestDataModels:
    """Tests for case builder Pydantic models."""

    def test_risk_indicator(self):
        """RiskIndicator should store type, severity, description."""
        ri = RiskIndicator(
            indicator_type="high_value_transfer",
            severity="high",
            description="Transfer exceeds $10,000",
        )
        assert ri.indicator_type == "high_value_transfer"
        assert ri.severity == "high"

    def test_evidence_defaults(self):
        """Evidence should have empty lists by default."""
        ev = Evidence(evidence_type="test")
        assert ev.related_transactions == []
        assert ev.related_entities == []

    def test_evidence_with_data(self):
        """Evidence should store related transactions and entities."""
        ev = Evidence(
            evidence_type="cross_border_flow",
            description="3 cross-border transactions",
            related_transactions=["T1", "T2", "T3"],
            related_entities=["E1", "E2"],
        )
        assert len(ev.related_transactions) == 3
        assert len(ev.related_entities) == 2

    def test_case_defaults(self):
        """Case should have sensible defaults."""
        case = Case(case_id="CASE-001", primary_entity="ENT-001")
        assert case.risk_score == 0.0
        assert case.transactions == []
        assert case.evidence == []
        assert case.created_at is not None

    def test_case_full(self):
        """Case should store all fields."""
        case = Case(
            case_id="CASE-001",
            primary_entity="ENT-001",
            related_entities=["ENT-002", "ENT-003"],
            transactions=["TXN-001", "TXN-002"],
            fraud_scores={"TXN-001": 0.9, "TXN-002": 0.7},
            risk_score=0.85,
        )
        assert case.risk_score == 0.85
        assert len(case.related_entities) == 2


# ===========================================================================
# Case Builder Tests
# ===========================================================================


class TestCaseGrouping:
    """Tests for case grouping logic."""

    def test_single_suspicious_transaction(self):
        """One high-risk transaction should produce one case."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000, "US", "KY")]
        fraud = [_make_detection("T1", 0.9)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        assert len(cases) == 1
        assert cases[0].primary_entity == "ENT-A"
        assert "T1" in cases[0].transactions

    def test_multiple_txns_same_sender(self):
        """Multiple transactions from same sender should group together."""
        txns = [
            _make_txn("T1", "ENT-A", "ENT-B", 50000, "US", "KY", 9),
            _make_txn("T2", "ENT-A", "ENT-C", 40000, "US", "PA", 10),
            _make_txn("T3", "ENT-A", "ENT-D", 30000, "US", "CH", 11),
        ]
        fraud = [
            _make_detection("T1", 0.9),
            _make_detection("T2", 0.8),
            _make_detection("T3", 0.7),
        ]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        assert len(cases) == 1
        assert cases[0].primary_entity == "ENT-A"
        assert len(cases[0].transactions) == 3

    def test_different_senders_produce_separate_cases(self):
        """Transactions from different senders should produce separate cases."""
        txns = [
            _make_txn("T1", "ENT-A", "ENT-B", 50000),
            _make_txn("T2", "ENT-C", "ENT-D", 40000),
        ]
        fraud = [
            _make_detection("T1", 0.9),
            _make_detection("T2", 0.8),
        ]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        assert len(cases) == 2
        entities = {c.primary_entity for c in cases}
        assert entities == {"ENT-A", "ENT-C"}

    def test_no_high_risk_produces_no_cases(self):
        """If no transactions exceed the fraud threshold, no cases."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 100)]
        fraud = [_make_detection("T1", 0.1)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        assert len(cases) == 0

    def test_empty_input(self):
        """Empty input should produce no cases."""
        builder = CaseBuilder()
        cases = builder.build_cases([], [])
        assert len(cases) == 0


class TestEntityExpansion:
    """Tests for entity expansion via graph."""

    def test_related_entities_from_transactions(self):
        """Related entities should include receivers."""
        txns = [
            _make_txn("T1", "ENT-A", "ENT-B", 50000),
            _make_txn("T2", "ENT-A", "ENT-C", 40000),
        ]
        fraud = [
            _make_detection("T1", 0.9),
            _make_detection("T2", 0.8),
        ]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        assert len(cases) == 1
        assert "ENT-B" in cases[0].related_entities
        assert "ENT-C" in cases[0].related_entities

    def test_graph_neighbor_expansion(self):
        """Related entities should expand via graph neighbors."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.9)]

        # Build a graph with extra neighbor
        graph = nx.DiGraph()
        graph.add_edge("ENT-A", "ENT-B")
        graph.add_edge("ENT-A", "ENT-EXTRA")

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud, graph=graph)

        assert len(cases) == 1
        assert "ENT-EXTRA" in cases[0].related_entities


class TestRiskScoring:
    """Tests for case risk scoring."""

    def test_risk_score_range(self):
        """Case risk scores should be in [0, 1]."""
        txns = [
            _make_txn("T1", "ENT-A", "ENT-B", 50000, "US", "KY"),
            _make_txn("T2", "ENT-A", "ENT-C", 40000, "US", "PA"),
        ]
        fraud = [
            _make_detection("T1", 0.9),
            _make_detection("T2", 0.8),
        ]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        for case in cases:
            assert 0.0 <= case.risk_score <= 1.0

    def test_higher_fraud_means_higher_risk(self):
        """Cases with higher fraud scores should have higher risk."""
        txns_high = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud_high = [_make_detection("T1", 0.95)]

        txns_low = [_make_txn("T2", "ENT-C", "ENT-D", 50000)]
        fraud_low = [_make_detection("T2", 0.51)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases_high = builder.build_cases(txns_high, fraud_high)
        cases_low = builder.build_cases(txns_low, fraud_low)

        assert cases_high[0].risk_score > cases_low[0].risk_score

    def test_graph_metrics_influence_risk(self):
        """Entity risk scores should influence case risk."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.7)]

        # With high graph risk
        risk_scores = [_make_entity_risk("ENT-A", overall_risk=0.9)]
        builder = CaseBuilder(fraud_threshold=0.5)
        cases_with = builder.build_cases(txns, fraud, entity_risk_scores=risk_scores)

        # Without graph risk
        cases_without = builder.build_cases(txns, fraud)

        assert cases_with[0].risk_score > cases_without[0].risk_score

    def test_cases_sorted_by_risk(self):
        """Cases should be sorted by risk score descending."""
        txns = [
            _make_txn("T1", "ENT-A", "ENT-B", 50000),
            _make_txn("T2", "ENT-C", "ENT-D", 5000),
        ]
        fraud = [
            _make_detection("T1", 0.95),
            _make_detection("T2", 0.55),
        ]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        scores = [c.risk_score for c in cases]
        assert scores == sorted(scores, reverse=True)


class TestEvidenceGeneration:
    """Tests for evidence generation."""

    def test_high_value_evidence(self):
        """High-value transfers should generate evidence."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.9)]

        builder = CaseBuilder(fraud_threshold=0.5, high_value_threshold=10000)
        cases = builder.build_cases(txns, fraud)

        evidence_types = [e.evidence_type for e in cases[0].evidence]
        assert "high_value_transfer" in evidence_types

    def test_cross_border_evidence(self):
        """Cross-border transactions should generate evidence."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000, "US", "KY")]
        fraud = [_make_detection("T1", 0.9)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        evidence_types = [e.evidence_type for e in cases[0].evidence]
        assert "cross_border_flow" in evidence_types

    def test_critical_fraud_evidence(self):
        """Critical fraud scores should generate evidence."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.9)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        evidence_types = [e.evidence_type for e in cases[0].evidence]
        assert "critical_fraud_score" in evidence_types

    def test_entity_cluster_evidence(self):
        """Dense entity clusters should generate evidence."""
        txns = [
            _make_txn("T1", "ENT-A", "ENT-B", 50000, hour=9),
            _make_txn("T2", "ENT-A", "ENT-C", 40000, hour=10),
            _make_txn("T3", "ENT-A", "ENT-D", 30000, hour=11),
        ]
        fraud = [
            _make_detection("T1", 0.9),
            _make_detection("T2", 0.8),
            _make_detection("T3", 0.7),
        ]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        evidence_types = [e.evidence_type for e in cases[0].evidence]
        assert "entity_cluster" in evidence_types

    def test_no_evidence_for_low_risk(self):
        """Low-value domestic transactions shouldn't generate high-value evidence."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 500)]
        fraud = [_make_detection("T1", 0.6)]

        builder = CaseBuilder(fraud_threshold=0.5, high_value_threshold=10000)
        cases = builder.build_cases(txns, fraud)

        evidence_types = [e.evidence_type for e in cases[0].evidence]
        assert "high_value_transfer" not in evidence_types
        assert "cross_border_flow" not in evidence_types


class TestRiskIndicators:
    """Tests for risk indicator generation."""

    def test_high_value_indicator(self):
        """High-value transactions should trigger indicator."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.9)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        indicator_types = [ri.indicator_type for ri in cases[0].risk_indicators]
        assert "high_value_transfer" in indicator_types

    def test_cross_border_indicator(self):
        """Cross-border transactions should trigger indicator."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000, "US", "KY")]
        fraud = [_make_detection("T1", 0.9)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        indicator_types = [ri.indicator_type for ri in cases[0].risk_indicators]
        assert "cross_border" in indicator_types

    def test_rapid_succession_indicator(self):
        """Rapid transactions should trigger indicator."""
        txns = [
            _make_txn("T1", "ENT-A", "ENT-B", 50000, hour=9),
            _make_txn("T2", "ENT-A", "ENT-C", 40000, hour=9),
            _make_txn("T3", "ENT-A", "ENT-D", 30000, hour=9),
        ]
        fraud = [
            _make_detection("T1", 0.9),
            _make_detection("T2", 0.8),
            _make_detection("T3", 0.7),
        ]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        indicator_types = [ri.indicator_type for ri in cases[0].risk_indicators]
        assert "rapid_succession" in indicator_types

    def test_high_fraud_concentration_indicator(self):
        """High average fraud should trigger concentration indicator."""
        txns = [
            _make_txn("T1", "ENT-A", "ENT-B", 50000),
            _make_txn("T2", "ENT-A", "ENT-C", 40000),
        ]
        fraud = [
            _make_detection("T1", 0.95),
            _make_detection("T2", 0.90),
        ]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        indicator_types = [ri.indicator_type for ri in cases[0].risk_indicators]
        assert "high_fraud_concentration" in indicator_types


class TestCaseIdGeneration:
    """Tests for case ID generation."""

    def test_case_id_format(self):
        """Case IDs should start with 'CASE-'."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.9)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        assert cases[0].case_id.startswith("CASE-")

    def test_unique_case_ids(self):
        """Each case should have a unique ID."""
        txns = [
            _make_txn("T1", "ENT-A", "ENT-B", 50000),
            _make_txn("T2", "ENT-C", "ENT-D", 40000),
        ]
        fraud = [
            _make_detection("T1", 0.9),
            _make_detection("T2", 0.8),
        ]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        ids = [c.case_id for c in cases]
        assert len(ids) == len(set(ids))


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_threshold_at_boundary(self):
        """Transaction exactly at threshold should be included."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.5)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        assert len(cases) == 1

    def test_threshold_just_below(self):
        """Transaction just below threshold should be excluded."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.49)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        assert len(cases) == 0

    def test_custom_thresholds(self):
        """Custom thresholds should work correctly."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.3)]

        builder = CaseBuilder(fraud_threshold=0.2)
        cases = builder.build_cases(txns, fraud)

        assert len(cases) == 1

    def test_case_created_at_set(self):
        """Each case should have a created_at timestamp."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.9)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud)

        assert cases[0].created_at is not None
        assert cases[0].created_at.tzinfo is not None

    def test_graph_metrics_populated(self):
        """Graph metrics should appear when entity risk scores provided."""
        txns = [_make_txn("T1", "ENT-A", "ENT-B", 50000)]
        fraud = [_make_detection("T1", 0.9)]
        risk = [_make_entity_risk("ENT-A", overall_risk=0.8)]

        builder = CaseBuilder(fraud_threshold=0.5)
        cases = builder.build_cases(txns, fraud, entity_risk_scores=risk)

        assert "overall_graph_risk" in cases[0].graph_metrics
        assert cases[0].graph_metrics["overall_graph_risk"] == 0.8
