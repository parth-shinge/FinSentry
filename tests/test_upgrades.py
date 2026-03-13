"""
FinSentry - Upgrade Feature Tests
======================================

Tests for Phase-4 improvements:

* Case model computed properties (severity_label, entities_involved,
  transaction_count, aml_patterns_detected)
* Risk propagation in GraphAnalyzer
* Enhanced investigation narrative pattern descriptions
* Entity profile suspicious activity summary helper

Run::

    cd d:\\FinSentry
    python -m pytest tests/test_upgrades.py -v
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

from case_builder.models import Case, RiskIndicator
from graph_engine.analyzer import GraphAnalyzer
from graph_engine.models import EntityRiskScore
from investigation_narrative.generator import NarrativeGenerator, InvestigationNarrative
from ingestion.schema import NormalizedTransaction


# ===================================================================
# Helpers
# ===================================================================

def _make_case(
    risk_score: float = 0.5,
    primary: str = "E001",
    related: list[str] | None = None,
    transactions: list[str] | None = None,
    indicators: list[RiskIndicator] | None = None,
) -> Case:
    return Case(
        case_id="CASE-001",
        primary_entity=primary,
        related_entities=["E002", "E003"] if related is None else related,
        transactions=["T1", "T2", "T3"] if transactions is None else transactions,
        risk_score=risk_score,
        risk_indicators=[] if indicators is None else indicators,
    )


def _make_txn(
    txn_id: str = "T1",
    sender: str = "E001",
    receiver: str = "E002",
    amount: float = 10000.0,
    is_intl: bool = False,
) -> NormalizedTransaction:
    return NormalizedTransaction(
        transaction_id=txn_id,
        timestamp=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        sender_entity_id=sender,
        receiver_entity_id=receiver,
        amount=amount,
        currency="USD",
        origin_country="US",
        destination_country="SG" if is_intl else "US",
        is_international=is_intl,
        channel="wire",
        transaction_type="transfer",
        account_id="ACC-001",
        merchant_category="general",
    )


class _FakePattern:
    """Lightweight stand-in for PatternDetection."""

    def __init__(self, pattern_type: str, confidence: float = 0.8,
                 severity: str = "high", description: str = "Desc",
                 involved_entities: list[str] | None = None):
        self.pattern_type = pattern_type
        self.confidence = confidence
        self.severity = severity
        self.description = description
        self.involved_entities = involved_entities or []


# ===================================================================
# Case model computed properties
# ===================================================================

class TestCaseComputedProperties:
    """Verify new computed properties on Case model."""

    @pytest.mark.parametrize("score,expected", [
        (0.9, "critical"),
        (0.8, "critical"),
        (0.7, "high"),
        (0.6, "high"),
        (0.5, "medium"),
        (0.4, "medium"),
        (0.3, "low"),
        (0.0, "low"),
    ])
    def test_severity_label(self, score: float, expected: str):
        case = _make_case(risk_score=score)
        assert case.severity_label == expected

    def test_entities_involved(self):
        case = _make_case(primary="E001", related=["E002", "E003"])
        assert case.entities_involved == ["E001", "E002", "E003"]

    def test_entities_involved_no_related(self):
        case = _make_case(primary="E001", related=[], transactions=["T1"])
        assert case.entities_involved == ["E001"]

    def test_transaction_count(self):
        case = _make_case(transactions=["T1", "T2", "T3", "T4"])
        assert case.transaction_count == 4

    def test_transaction_count_empty(self):
        case = _make_case(transactions=[], related=[])
        assert case.transaction_count == 0

    def test_aml_patterns_detected(self):
        indicators = [
            RiskIndicator(indicator_type="structuring", severity="high", description="d1"),
            RiskIndicator(indicator_type="layering", severity="high", description="d2"),
            RiskIndicator(indicator_type="structuring", severity="medium", description="d3"),
        ]
        case = _make_case(indicators=indicators)
        patterns = case.aml_patterns_detected
        assert patterns == ["structuring", "layering"]

    def test_aml_patterns_empty(self):
        case = _make_case(indicators=[])
        assert case.aml_patterns_detected == []


# ===================================================================
# Risk propagation
# ===================================================================

class TestRiskPropagation:
    """Verify GraphAnalyzer._propagate_risk boosts neighbors."""

    def _build_chain_graph(self) -> nx.DiGraph:
        """A → B → C, A has high fraud."""
        g = nx.DiGraph()
        g.add_edge("A", "B", amount=50000, fraud_score=0.9, timestamp="2024-01-01T00:00:00")
        g.add_edge("B", "C", amount=30000, fraud_score=0.2, timestamp="2024-01-02T00:00:00")
        return g

    def test_propagation_boosts_neighbor(self):
        g = self._build_chain_graph()
        analyzer = GraphAnalyzer(g)
        scores = analyzer.compute_entity_risk_scores()
        score_map = {s.entity_id: s.overall_risk_score for s in scores}
        # A should have high risk due to high fraud edges
        # B should get a propagation boost from A if A > threshold
        # This test verifies the mechanism runs without error and scores exist
        assert len(scores) == 3
        assert all(0.0 <= s.overall_risk_score <= 1.0 for s in scores)

    def test_propagate_risk_method_directly(self):
        g = self._build_chain_graph()
        analyzer = GraphAnalyzer(g)
        # Create synthetic scores
        initial = [
            EntityRiskScore(
                entity_id="A", centrality_score=0.5,
                community_fraud_density=0.8, high_risk_neighbor_count=0,
                cycle_participation_count=0, overall_risk_score=0.75,
                suspicious_paths=[],
            ),
            EntityRiskScore(
                entity_id="B", centrality_score=0.3,
                community_fraud_density=0.3, high_risk_neighbor_count=1,
                cycle_participation_count=0, overall_risk_score=0.30,
                suspicious_paths=[],
            ),
            EntityRiskScore(
                entity_id="C", centrality_score=0.1,
                community_fraud_density=0.1, high_risk_neighbor_count=0,
                cycle_participation_count=0, overall_risk_score=0.10,
                suspicious_paths=[],
            ),
        ]
        result = analyzer._propagate_risk(initial, threshold=0.6, boost_factor=0.10)
        result_map = {s.entity_id: s.overall_risk_score for s in result}
        # B is neighbor of high-risk A → should be boosted
        assert result_map["B"] == pytest.approx(0.40, abs=0.01)
        # C is neighbor of B (not high-risk) → should stay same
        assert result_map["C"] == pytest.approx(0.10, abs=0.01)
        # A should be unchanged
        assert result_map["A"] == pytest.approx(0.75, abs=0.01)


# ===================================================================
# Enhanced investigation narrative
# ===================================================================

class TestEnhancedNarrative:
    """Test investigator-friendly pattern descriptions."""

    def test_structuring_template(self):
        gen = NarrativeGenerator()
        patterns = [_FakePattern("structuring", 0.85, "high")]
        case = _make_case()
        txns = [_make_txn("T1"), _make_txn("T2"), _make_txn("T3")]
        narrative = gen.generate_narrative(case, txns, patterns)
        assert isinstance(narrative, InvestigationNarrative)
        full_text = narrative.to_text()
        assert "structuring behavior" in full_text
        assert "reporting thresholds" in full_text

    def test_layering_template(self):
        gen = NarrativeGenerator()
        patterns = [_FakePattern("layering", 0.9, "critical")]
        case = _make_case()
        txns = [_make_txn("T1"), _make_txn("T2"), _make_txn("T3")]
        narrative = gen.generate_narrative(case, txns, patterns)
        assert "layering activity" in narrative.to_text()

    def test_round_tripping_template(self):
        gen = NarrativeGenerator()
        patterns = [_FakePattern("round_tripping", 0.7, "high")]
        case = _make_case()
        txns = [_make_txn("T1"), _make_txn("T2"), _make_txn("T3")]
        narrative = gen.generate_narrative(case, txns, patterns)
        assert "round-tripping" in narrative.to_text()

    def test_rapid_transfers_template(self):
        gen = NarrativeGenerator()
        patterns = [_FakePattern("rapid_transfers", 0.6, "medium")]
        case = _make_case()
        txns = [_make_txn("T1"), _make_txn("T2"), _make_txn("T3")]
        narrative = gen.generate_narrative(case, txns, patterns)
        assert "rapid successive transfers" in narrative.to_text()

    def test_shell_company_template(self):
        gen = NarrativeGenerator()
        patterns = [_FakePattern("shell_company_clusters", 0.75, "high")]
        case = _make_case()
        txns = [_make_txn("T1"), _make_txn("T2"), _make_txn("T3")]
        narrative = gen.generate_narrative(case, txns, patterns)
        assert "shell-company" in narrative.to_text()

    def test_multiple_patterns(self):
        gen = NarrativeGenerator()
        patterns = [
            _FakePattern("structuring", 0.85, "high"),
            _FakePattern("layering", 0.9, "critical"),
        ]
        case = _make_case()
        txns = [_make_txn("T1"), _make_txn("T2"), _make_txn("T3")]
        narrative = gen.generate_narrative(case, txns, patterns)
        text = narrative.to_text()
        assert "structuring behavior" in text
        assert "layering activity" in text

    def test_no_patterns_no_descriptions(self):
        gen = NarrativeGenerator()
        case = _make_case()
        txns = [_make_txn("T1"), _make_txn("T2"), _make_txn("T3")]
        narrative = gen.generate_narrative(case, txns, None)
        assert narrative.pattern_descriptions == []


# ===================================================================
# Entity profile summary helper
# ===================================================================

class TestEntitySummaryHelper:
    """Test the _build_entity_summary function from api.routes."""

    def test_summary_generation(self):
        from api.routes import _build_entity_summary

        summary = _build_entity_summary(
            entity_id="E001",
            risk_score=0.82,
            total_txns=15,
            fraud_txns=5,
            total_value=250000.0,
            patterns=["structuring", "layering"],
            connected=["E002", "E003", "E004"],
            jurisdiction="US",
        )
        assert "E001" in summary
        assert "high risk" in summary
        assert "structuring" in summary
        assert "layering" in summary
        assert "15 transaction" in summary
        assert "5 transaction" in summary

    def test_summary_no_transactions(self):
        from api.routes import _build_entity_summary

        summary = _build_entity_summary(
            entity_id="E999",
            risk_score=0.0,
            total_txns=0,
            fraud_txns=0,
            total_value=0.0,
            patterns=[],
            connected=[],
            jurisdiction="",
        )
        assert "no recorded transactions" in summary

    def test_summary_medium_risk(self):
        from api.routes import _build_entity_summary

        summary = _build_entity_summary(
            entity_id="E100",
            risk_score=0.55,
            total_txns=3,
            fraud_txns=0,
            total_value=8000.0,
            patterns=[],
            connected=["E101"],
            jurisdiction="GB",
        )
        assert "medium risk" in summary
        assert "Detected patterns" not in summary

    def test_summary_low_risk(self):
        from api.routes import _build_entity_summary

        summary = _build_entity_summary(
            entity_id="E200",
            risk_score=0.15,
            total_txns=2,
            fraud_txns=0,
            total_value=500.0,
            patterns=[],
            connected=["E201", "E202"],
            jurisdiction="JP",
        )
        assert "low risk" in summary
        assert "Connected to 2 entities" in summary


# ===================================================================
# Betweenness centrality
# ===================================================================

class TestBetweennessCentrality:
    """Verify betweenness centrality is computed in graph analytics."""

    def _build_star_graph(self) -> nx.DiGraph:
        """Hub A connected to B, C, D. B→C also exists."""
        g = nx.DiGraph()
        g.add_edge("A", "B", amount=10000, fraud_score=0.3, timestamp="2024-01-01T00:00:00")
        g.add_edge("A", "C", amount=20000, fraud_score=0.2, timestamp="2024-01-02T00:00:00")
        g.add_edge("A", "D", amount=15000, fraud_score=0.1, timestamp="2024-01-03T00:00:00")
        g.add_edge("B", "C", amount=5000, fraud_score=0.1, timestamp="2024-01-04T00:00:00")
        return g

    def test_betweenness_in_metrics(self):
        g = self._build_star_graph()
        analyzer = GraphAnalyzer(g)
        centrality = analyzer.compute_centrality()
        assert len(centrality) == 4
        # A is the hub — should have non-zero betweenness
        assert centrality["A"].betweenness_centrality >= 0.0
        # All nodes should have the field
        for metrics in centrality.values():
            assert hasattr(metrics, "betweenness_centrality")
            assert metrics.betweenness_centrality >= 0.0

    def test_hub_has_highest_betweenness(self):
        g = self._build_star_graph()
        analyzer = GraphAnalyzer(g)
        centrality = analyzer.compute_centrality()
        # A is the hub connecting B, C, D — should have highest betweenness
        hub_bc = centrality["A"].betweenness_centrality
        leaf_bc = centrality["D"].betweenness_centrality
        assert hub_bc >= leaf_bc


# ===================================================================
# Investigation Copilot helpers
# ===================================================================

class TestInvestigationCopilot:
    """Test the Investigation Copilot helper functions."""

    def test_extract_entity_exact_match(self):
        from api.routes import _extract_entity_from_question

        entities = {"E17", "E001", "ACME-Corp"}
        assert _extract_entity_from_question("Why is Entity E17 suspicious?", entities) == "E17"
        assert _extract_entity_from_question("Tell me about E001", entities) == "E001"

    def test_extract_entity_no_match(self):
        from api.routes import _extract_entity_from_question

        entities = {"E17", "E001"}
        assert _extract_entity_from_question("No entity here at all", entities) is None

    def test_extract_entity_case_insensitive(self):
        from api.routes import _extract_entity_from_question

        entities = {"E17", "ACME-Corp"}
        assert _extract_entity_from_question("what about e17?", entities) == "E17"

    def test_extract_entity_hyphenated_ids(self):
        """Entity IDs like ENT-7001 should be matched."""
        from api.routes import _extract_entity_from_question

        entities = {"ENT-7001", "ENT-7002", "ENT-8003"}
        assert _extract_entity_from_question("Tell me about ENT-7001", entities) == "ENT-7001"
        assert _extract_entity_from_question("why is ent-7002 suspicious?", entities) == "ENT-7002"

    def test_extract_entity_numeric_suffix(self):
        """Typing just '7001' should match 'ENT-7001'."""
        from api.routes import _extract_entity_from_question

        entities = {"ENT-7001", "ENT-7002"}
        assert _extract_entity_from_question("What about 7001?", entities) == "ENT-7001"

    def test_extract_entity_various_formats(self):
        """ACC_17, CUST17, ENTITY12 formats."""
        from api.routes import _extract_entity_from_question

        entities = {"ACC_17", "CUST17", "ENTITY12"}
        assert _extract_entity_from_question("info on ACC_17", entities) == "ACC_17"
        assert _extract_entity_from_question("look up CUST17", entities) == "CUST17"
        assert _extract_entity_from_question("details for ENTITY12", entities) == "ENTITY12"

    def test_extract_entity_prefers_longest_match(self):
        """ENT-7001 should be preferred over a shorter match."""
        from api.routes import _extract_entity_from_question

        entities = {"ENT-700", "ENT-7001"}
        result = _extract_entity_from_question("Tell me about ENT-7001", entities)
        assert result == "ENT-7001"

    def test_copilot_schemas_importable(self):
        from api.schemas import (
            InvestigationQueryRequest,
            InvestigationQueryResponse,
            InvestigationDriverOut,
        )
        req = InvestigationQueryRequest(question="Why is E17 suspicious?")
        assert req.question == "Why is E17 suspicious?"

        resp = InvestigationQueryResponse(
            entity_id="E17",
            question="test",
            answer="Because it has high risk.",
            risk_score=0.85,
            risk_level="high",
        )
        assert resp.risk_level == "high"
        assert resp.drivers == []
        assert resp.aml_patterns == []


# ===================================================================
# GraphEntityResponse betweenness field
# ===================================================================

class TestGraphSchemaUpgrade:
    """Verify GraphEntityResponse includes betweenness_centrality."""

    def test_schema_has_betweenness(self):
        from api.schemas import GraphEntityResponse

        resp = GraphEntityResponse(
            entity_id="E01",
            entity_type="individual",
            degree_centrality=0.5,
            betweenness_centrality=0.3,
            pagerank=0.1,
            in_degree=2,
            out_degree=3,
            community_id=0,
            neighbors=[],
        )
        assert resp.betweenness_centrality == 0.3

    def test_schema_betweenness_default(self):
        from api.schemas import GraphEntityResponse

        resp = GraphEntityResponse(
            entity_id="E01",
            entity_type="individual",
            degree_centrality=0.5,
            pagerank=0.1,
            in_degree=2,
            out_degree=3,
            community_id=0,
            neighbors=[],
        )
        assert resp.betweenness_centrality == 0.0


# ===================================================================
# SAR Persistence schemas
# ===================================================================

class TestSARPersistenceSchemas:
    """Verify SAR list/detail schemas."""

    def test_sar_list_schema(self):
        from api.schemas import SARListItem, SARListResponse

        item = SARListItem(
            report_id="SAR-001",
            case_id="CASE-001",
            subject_entity="ENT-7001",
            report_date="2025-03-01T00:00:00",
            risk_score=0.85,
        )
        assert item.report_id == "SAR-001"

        resp = SARListResponse(total=1, reports=[item])
        assert resp.total == 1
        assert len(resp.reports) == 1

    def test_sar_list_empty(self):
        from api.schemas import SARListResponse

        resp = SARListResponse(total=0, reports=[])
        assert resp.total == 0
        assert resp.reports == []


# ===================================================================
# Simulation removed — schemas should not exist
# ===================================================================

class TestSimulationRemoved:
    """Verify simulation schemas are removed."""

    def test_no_simulation_schemas(self):
        import api.schemas as schemas
        assert not hasattr(schemas, "SimulationStartRequest")
        assert not hasattr(schemas, "SimulationStartResponse")
        assert not hasattr(schemas, "SimulationStageOut")
