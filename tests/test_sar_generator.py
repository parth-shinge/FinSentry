"""
FinSentry AI - SAR Generator Unit Tests
==========================================

Tests covering:

* SARReport model structure and validation
* SAR template rendering
* ContextBuilder output
* SARGenerator end-to-end pipeline

All tests use synthetic data -- no database or external services required.

Run::

    cd d:\\FinSentry
    python -m pytest tests/test_sar_generator.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from case_builder.models import Case, Evidence, RiskIndicator
from fraud_detection.models import DetectionResult, FraudScore, RiskLevel
from graph_engine.analyzer import GraphAnalyzer
from graph_engine.models import EntityRiskScore, NodeMetrics, CommunityResult, PathResult
from graph_rag.context_builder import ContextBuilder, InvestigationContext
from graph_rag.retriever import GraphRetriever, RetrievedContext
from ingestion.schema import NormalizedTransaction
from sar_generator.models import SARReport
from sar_generator import templates
from sar_generator.generator import SARGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_txn(
    txn_id: str = "TXN-001",
    sender: str = "ENT-A",
    receiver: str = "ENT-B",
    amount: float = 5000.0,
    origin: str = "US",
    dest: str = "KY",
    is_intl: bool = True,
) -> NormalizedTransaction:
    """Create a NormalizedTransaction fixture."""
    return NormalizedTransaction(
        transaction_id=txn_id,
        account_id="ACC-001",
        sender_entity_id=sender,
        receiver_entity_id=receiver,
        amount=amount,
        currency="USD",
        timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=timezone.utc),
        origin_country=origin,
        destination_country=dest,
        merchant_category="financial_services",
        transaction_type="wire",
        channel="online",
        is_international=is_intl,
        is_large_transaction=amount >= 10000.0,
    )


def _make_case(
    n_txns: int = 5,
    risk_score: float = 0.75,
) -> Case:
    """Create a Case fixture with transactions and evidence."""
    txn_ids = [f"TXN-{i:03d}" for i in range(n_txns)]
    fraud_scores = {tid: 0.6 + (i * 0.05) for i, tid in enumerate(txn_ids)}

    return Case(
        case_id="CASE-TEST001",
        primary_entity="ENT-A",
        related_entities=["ENT-B", "ENT-C"],
        transactions=txn_ids,
        fraud_scores=fraud_scores,
        graph_metrics={
            "centrality_score": 0.45,
            "community_fraud_density": 0.35,
            "cycle_participation": 2.0,
            "overall_graph_risk": 0.55,
        },
        risk_indicators=[
            RiskIndicator(
                indicator_type="cross_border",
                severity="high",
                description="3 cross-border transactions detected",
            ),
            RiskIndicator(
                indicator_type="high_value_transfer",
                severity="high",
                description="Transactions include amounts up to $50,000",
            ),
        ],
        evidence=[
            Evidence(
                evidence_type="cross_border_flow",
                description="3 cross-border transactions spanning 4 jurisdictions",
                related_transactions=txn_ids[:3],
                related_entities=["ENT-A", "ENT-B"],
            ),
        ],
        risk_score=risk_score,
    )


def _make_transactions(n: int = 10) -> list[NormalizedTransaction]:
    """Create a batch of diverse transactions."""
    txns = []
    for i in range(n):
        sender = f"ENT-{'ABCDE'[i % 5]}"
        receiver = f"ENT-{'BCDEF'[i % 5]}"
        txns.append(
            _make_txn(
                txn_id=f"TXN-{i:03d}",
                sender=sender,
                receiver=receiver,
                amount=float(np.random.randint(1000, 50000)),
                origin="US" if i % 3 != 0 else "GB",
                dest="KY" if i % 4 == 0 else "US",
                is_intl=(i % 4 == 0),
            )
        )
    return txns


def _make_graph(transactions: list[NormalizedTransaction]) -> nx.DiGraph:
    """Build a simple graph from transactions."""
    g = nx.DiGraph()
    for txn in transactions:
        sender = txn.sender_entity_id
        receiver = txn.receiver_entity_id
        if g.has_edge(sender, receiver):
            g[sender][receiver]["total_amount"] += txn.amount
        else:
            g.add_edge(
                sender, receiver,
                total_amount=txn.amount,
                fraud_score=0.5,
            )
    return g


# ===========================================================================
# SARReport model tests
# ===========================================================================


class TestSARReportModel:
    """Tests for the SARReport Pydantic model."""

    def test_basic_creation(self):
        """Should create a valid SARReport with required fields."""
        report = SARReport(
            report_id="SAR-001",
            case_id="CASE-001",
            subject_entity="ENT-A",
        )
        assert report.report_id == "SAR-001"
        assert report.case_id == "CASE-001"
        assert report.subject_entity == "ENT-A"

    def test_default_values(self):
        """Should have sensible defaults for optional fields."""
        report = SARReport(
            report_id="SAR-002",
            case_id="CASE-002",
            subject_entity="ENT-B",
        )
        assert report.total_amount == 0.0
        assert report.risk_score == 0.0
        assert report.entities_involved == []
        assert report.jurisdictions == []

    def test_full_creation(self):
        """Should create a fully populated SARReport."""
        report = SARReport(
            report_id="SAR-003",
            case_id="CASE-003",
            subject_entity="ENT-C",
            suspicious_activity_description="Test activity",
            transaction_summary="5 suspicious transactions",
            evidence_summary="Supporting evidence here",
            risk_assessment="HIGH risk",
            recommended_action="File SAR immediately",
            entities_involved=["ENT-C", "ENT-D"],
            jurisdictions=["US", "KY"],
            total_amount=75000.0,
            risk_score=0.85,
        )
        assert report.total_amount == 75000.0
        assert len(report.entities_involved) == 2
        assert report.risk_score == 0.85

    def test_report_date_auto(self):
        """Report date should be auto-populated."""
        report = SARReport(
            report_id="SAR-004",
            case_id="CASE-004",
            subject_entity="ENT-D",
        )
        assert report.report_date is not None
        assert report.report_date.tzinfo is not None


# ===========================================================================
# Template tests
# ===========================================================================


class TestSARTemplates:
    """Tests for SAR template rendering functions."""

    @pytest.fixture()
    def case(self) -> Case:
        return _make_case()

    @pytest.fixture()
    def context(self) -> InvestigationContext:
        return InvestigationContext(
            case_summary="Test case summary",
            entities_involved="ENT-A (primary), ENT-B, ENT-C",
            suspicious_transactions="5 transactions totaling $50,000",
            graph_patterns="Community of 3 entities",
            risk_indicators="[HIGH] cross_border: 3 transactions",
            supporting_evidence="Cross-border flow evidence",
        )

    def test_subject_information(self, context, case):
        """Subject info should include primary entity and case ID."""
        text = templates.subject_information(context, case)
        assert "ENT-A" in text
        assert "CASE-TEST001" in text

    def test_suspicious_activity(self, context, case):
        """Suspicious activity should include transaction patterns."""
        text = templates.suspicious_activity_description(context, case)
        assert "SUSPICIOUS ACTIVITY" in text
        assert "Test case summary" in text

    def test_transaction_evidence(self, context, case):
        """Transaction evidence should list flagged transactions."""
        text = templates.transaction_evidence(context, case)
        assert "TRANSACTION EVIDENCE" in text
        assert "TXN-" in text

    def test_risk_summary_high(self, context, case):
        """High-risk cases should get HIGH classification."""
        text = templates.risk_summary(context, case)
        assert "RISK ASSESSMENT" in text
        assert "HIGH" in text

    def test_risk_summary_low(self, context):
        """Low-risk cases should get LOW classification."""
        low_case = _make_case(risk_score=0.2)
        text = templates.risk_summary(context, low_case)
        assert "LOW" in text

    def test_recommended_action_high_risk(self, context, case):
        """High-risk cases should recommend filing SAR."""
        text = templates.recommended_action(context, case)
        assert "File SAR" in text or "FinCEN" in text

    def test_recommended_action_low_risk(self, context):
        """Low-risk cases should recommend standard monitoring."""
        low_case = _make_case(risk_score=0.2)
        text = templates.recommended_action(context, low_case)
        assert "standard monitoring" in text

    def test_recommended_action_medium_risk(self, context):
        """Medium-risk cases should recommend enhanced due diligence."""
        med_case = _make_case(risk_score=0.5)
        text = templates.recommended_action(context, med_case)
        assert "due diligence" in text or "monitoring" in text


# ===========================================================================
# Context Builder tests
# ===========================================================================


class TestContextBuilder:
    """Tests for the ContextBuilder."""

    def test_build_context_returns_all_sections(self):
        """Should populate all sections."""
        retrieved = RetrievedContext(
            case_id="CASE-001",
            primary_entity="ENT-A",
        )
        case = _make_case()
        builder = ContextBuilder()
        ctx = builder.build_context(retrieved, case)

        assert isinstance(ctx, InvestigationContext)
        assert ctx.case_summary != ""
        assert ctx.entities_involved != ""
        assert ctx.suspicious_transactions != ""
        assert ctx.risk_indicators != ""
        assert ctx.supporting_evidence != ""

    def test_case_summary_contains_case_id(self):
        """Case summary should include the case ID."""
        retrieved = RetrievedContext(case_id="CASE-X", primary_entity="ENT-X")
        case = _make_case()
        builder = ContextBuilder()
        ctx = builder.build_context(retrieved, case)
        assert case.case_id in ctx.case_summary


# ===========================================================================
# GraphRetriever tests
# ===========================================================================


class TestGraphRetriever:
    """Tests for the GraphRetriever."""

    @pytest.fixture()
    def setup(self):
        txns = _make_transactions(10)
        graph = _make_graph(txns)
        analyzer = GraphAnalyzer(graph)
        retriever = GraphRetriever(graph, analyzer)
        case = _make_case()
        return retriever, case, txns, graph

    def test_retrieve_case_entities(self, setup):
        """Should return primary + related entities."""
        retriever, case, _, _ = setup
        entities = retriever.retrieve_case_entities(case)
        assert "ENT-A" in entities
        assert "ENT-B" in entities
        assert "ENT-C" in entities

    def test_retrieve_returns_context(self, setup):
        """retrieve() should return a RetrievedContext."""
        retriever, case, txns, _ = setup
        ctx = retriever.retrieve(case, txns)
        assert isinstance(ctx, RetrievedContext)
        assert ctx.case_id == case.case_id
        assert ctx.primary_entity == case.primary_entity

    def test_retrieve_graph_metrics(self, setup):
        """Should return graph metrics for primary entity."""
        retriever, case, _, _ = setup
        metrics = retriever.retrieve_graph_metrics(case)
        # If ENT-A exists in graph, should have metrics
        assert isinstance(metrics, dict)

    def test_retrieve_related_transactions(self, setup):
        """Should filter transactions to case entities."""
        retriever, case, txns, _ = setup
        related = retriever.retrieve_related_transactions(case, txns)
        assert isinstance(related, list)


# ===========================================================================
# SARGenerator tests
# ===========================================================================


class TestSARGenerator:
    """Tests for the SARGenerator end-to-end."""

    @pytest.fixture()
    def pipeline(self):
        """Set up the full pipeline with synthetic data."""
        txns = _make_transactions(20)
        graph = _make_graph(txns)
        analyzer = GraphAnalyzer(graph)
        case = _make_case(n_txns=5, risk_score=0.75)
        gen = SARGenerator(graph, analyzer)
        return gen, case, txns

    def test_generate_sar(self, pipeline):
        """Should produce a valid SARReport."""
        gen, case, txns = pipeline
        report = gen.generate_sar(case, txns)

        assert isinstance(report, SARReport)
        assert report.case_id == case.case_id
        assert report.subject_entity == case.primary_entity
        assert report.risk_score == case.risk_score

    def test_report_has_content(self, pipeline):
        """Generated report sections should not be empty."""
        gen, case, txns = pipeline
        report = gen.generate_sar(case, txns)

        assert report.suspicious_activity_description != ""
        assert report.transaction_summary != ""
        assert report.evidence_summary != ""
        assert report.risk_assessment != ""
        assert report.recommended_action != ""

    def test_report_entities(self, pipeline):
        """Report should include all case entities."""
        gen, case, txns = pipeline
        report = gen.generate_sar(case, txns)

        assert case.primary_entity in report.entities_involved

    def test_generate_multiple(self, pipeline):
        """Should generate multiple reports."""
        gen, case, txns = pipeline
        case2 = _make_case(risk_score=0.5)
        case2.case_id = "CASE-TEST002"
        reports = gen.generate_multiple([case, case2], txns)

        assert len(reports) == 2
        assert reports[0].case_id != reports[1].case_id

    def test_report_id_format(self, pipeline):
        """Report ID should start with SAR-."""
        gen, case, txns = pipeline
        report = gen.generate_sar(case, txns)
        assert report.report_id.startswith("SAR-")
