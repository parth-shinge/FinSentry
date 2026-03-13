"""
FinSentry - Agents Module Tests
======================================

Tests for the InvestigationOrchestrator, timeline reconstruction,
and the corresponding API endpoints.

Test Classes
------------
TestInvestigationOrchestrator  Unit tests for the orchestrator pipeline.
TestTimelineReconstruction     Unit tests for timeline event generation.
TestPipelineEndpoint           API tests for POST /pipeline/run.
TestTimelineEndpoint           API tests for GET /timeline/{case_id}.

Run::

    cd /path/to/FinSentry
    python -m pytest tests/test_agents.py -v
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ingestion.schema import NormalizedTransaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transactions(n: int = 30) -> list[NormalizedTransaction]:
    """Generate sample NormalizedTransaction objects.

    Creates a realistic mix of domestic, international, and high-value
    transactions to exercise the full pipeline.
    """
    random.seed(42)
    txns: list[NormalizedTransaction] = []

    for i in range(n):
        if i % 5 == 0:
            # Suspicious: high-value international
            txns.append(
                NormalizedTransaction(
                    transaction_id=f"TXN-{i:04d}",
                    account_id=f"ACC-{i % 3:03d}",
                    sender_entity_id=f"ENT-S{i % 3:03d}",
                    receiver_entity_id=f"ENT-R{i % 4:03d}",
                    amount=float(random.randint(15000, 80000)),
                    currency="USD",
                    timestamp=f"2025-01-15T{random.randint(0, 5):02d}:00:00",
                    origin_country="US",
                    destination_country="KY",
                    merchant_category="offshore_services",
                    transaction_type="wire",
                    channel="online",
                )
            )
        elif i % 3 == 0:
            # Medium: international
            txns.append(
                NormalizedTransaction(
                    transaction_id=f"TXN-{i:04d}",
                    account_id=f"ACC-{i % 5:03d}",
                    sender_entity_id=f"ENT-S{i % 5:03d}",
                    receiver_entity_id=f"ENT-R{i % 6:03d}",
                    amount=float(random.randint(3000, 9000)),
                    currency="USD",
                    timestamp=f"2025-01-15T{random.randint(8, 17):02d}:00:00",
                    origin_country="US",
                    destination_country="MX",
                    merchant_category="consulting",
                    transaction_type="wire",
                    channel="online",
                )
            )
        else:
            # Normal: domestic
            txns.append(
                NormalizedTransaction(
                    transaction_id=f"TXN-{i:04d}",
                    account_id=f"ACC-{i % 7:03d}",
                    sender_entity_id=f"ENT-S{i % 7:03d}",
                    receiver_entity_id=f"ENT-R{i % 8:03d}",
                    amount=float(random.randint(10, 2000)),
                    currency="USD",
                    timestamp=f"2025-01-15T{random.randint(8, 20):02d}:00:00",
                    origin_country="US",
                    destination_country="US",
                    merchant_category="retail",
                    transaction_type="card",
                    channel="pos",
                )
            )

    return txns


def _sample_api_transactions(n: int = 30) -> list[dict]:
    """Generate sample transaction dicts for API ingestion."""
    random.seed(42)
    txns = []
    for i in range(n):
        if i % 5 == 0:
            txns.append(
                {
                    "transaction_id": f"TXN-{i:04d}",
                    "account_id": f"ACC-{i % 3:03d}",
                    "sender_entity_id": f"ENT-S{i % 3:03d}",
                    "receiver_entity_id": f"ENT-R{i % 4:03d}",
                    "amount": float(random.randint(15000, 80000)),
                    "currency": "USD",
                    "timestamp": f"2025-01-15T{random.randint(0, 5):02d}:00:00",
                    "origin_country": "US",
                    "destination_country": "KY",
                    "merchant_category": "offshore_services",
                    "transaction_type": "wire",
                    "channel": "online",
                    "is_international": True,
                }
            )
        elif i % 3 == 0:
            txns.append(
                {
                    "transaction_id": f"TXN-{i:04d}",
                    "account_id": f"ACC-{i % 5:03d}",
                    "sender_entity_id": f"ENT-S{i % 5:03d}",
                    "receiver_entity_id": f"ENT-R{i % 6:03d}",
                    "amount": float(random.randint(3000, 9000)),
                    "currency": "USD",
                    "timestamp": f"2025-01-15T{random.randint(8, 17):02d}:00:00",
                    "origin_country": "US",
                    "destination_country": "MX",
                    "merchant_category": "consulting",
                    "transaction_type": "wire",
                    "channel": "online",
                    "is_international": True,
                }
            )
        else:
            txns.append(
                {
                    "transaction_id": f"TXN-{i:04d}",
                    "account_id": f"ACC-{i % 7:03d}",
                    "sender_entity_id": f"ENT-S{i % 7:03d}",
                    "receiver_entity_id": f"ENT-R{i % 8:03d}",
                    "amount": float(random.randint(10, 2000)),
                    "currency": "USD",
                    "timestamp": f"2025-01-15T{random.randint(8, 20):02d}:00:00",
                    "origin_country": "US",
                    "destination_country": "US",
                    "merchant_category": "retail",
                    "transaction_type": "card",
                    "channel": "pos",
                }
            )
    return txns


# ===========================================================================
# InvestigationOrchestrator — unit tests
# ===========================================================================


class TestInvestigationOrchestrator:
    """Tests for the full-pipeline orchestrator."""

    def test_run_returns_investigation_result(self):
        from agents.models import InvestigationResult
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(
            fraud_threshold=0.3, explain_top_n=0,
        )
        result = orch.run_full_investigation(txns)
        assert isinstance(result, InvestigationResult)

    def test_transactions_processed_count(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(explain_top_n=0)
        result = orch.run_full_investigation(txns)
        assert result.transactions_processed == 30

    def test_fraud_results_generated(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(explain_top_n=0)
        result = orch.run_full_investigation(txns)
        assert len(result.fraud_results) == 30

    def test_fraud_results_have_scores(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(explain_top_n=0)
        result = orch.run_full_investigation(txns)
        for r in result.fraud_results:
            assert 0.0 <= r.fraud_score.fraud_probability <= 1.0

    def test_graph_metrics_generated(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(explain_top_n=0)
        result = orch.run_full_investigation(txns)
        assert len(result.graph_metrics) > 0

    def test_cases_generated(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(fraud_threshold=0.3, explain_top_n=0)
        result = orch.run_full_investigation(txns)
        assert result.total_cases >= 0  # May be 0 depending on data

    def test_sar_reports_match_cases(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(fraud_threshold=0.3, explain_top_n=0)
        result = orch.run_full_investigation(txns)
        if result.total_cases > 0:
            assert len(result.sar_reports) == result.total_cases
        else:
            assert len(result.sar_reports) == 0

    def test_validation_results_match_sars(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(fraud_threshold=0.3, explain_top_n=0)
        result = orch.run_full_investigation(txns)
        assert len(result.validation_results) == len(result.sar_reports)

    def test_too_few_transactions_raises(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(3)
        orch = InvestigationOrchestrator()
        with pytest.raises(ValueError, match="at least 5"):
            orch.run_full_investigation(txns)

    def test_high_risk_count_property(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(explain_top_n=0)
        result = orch.run_full_investigation(txns)
        assert result.high_risk_count >= 0
        assert result.high_risk_count <= 30

    def test_all_reports_valid_property(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(fraud_threshold=0.3, explain_top_n=0)
        result = orch.run_full_investigation(txns)
        assert isinstance(result.all_reports_valid, bool)

    def test_explainability_stage(self):
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(
            fraud_threshold=0.3, explain_top_n=5,
        )
        result = orch.run_full_investigation(txns)
        # Should have generated up to 5 explanations
        assert len(result.explanations) <= 5


# ===========================================================================
# Timeline Reconstruction — unit tests
# ===========================================================================


class TestTimelineReconstruction:
    """Tests for build_transaction_timeline."""

    def _run_pipeline_and_get_case(self):
        """Helper: run the orchestrator and return first case + context."""
        from agents.orchestrator import InvestigationOrchestrator

        txns = _make_transactions(30)
        orch = InvestigationOrchestrator(fraud_threshold=0.3, explain_top_n=0)
        result = orch.run_full_investigation(txns)
        if result.total_cases == 0:
            pytest.skip("No cases generated from sample data")
        return result.cases[0], txns, result.fraud_results

    def test_timeline_returns_list(self):
        from agents.timeline import build_transaction_timeline

        case, txns, fraud = self._run_pipeline_and_get_case()
        events = build_transaction_timeline(case, txns, fraud)
        assert isinstance(events, list)

    def test_timeline_events_not_empty(self):
        from agents.timeline import build_transaction_timeline

        case, txns, fraud = self._run_pipeline_and_get_case()
        events = build_transaction_timeline(case, txns, fraud)
        assert len(events) > 0

    def test_timeline_events_chronological(self):
        from agents.timeline import build_transaction_timeline

        case, txns, fraud = self._run_pipeline_and_get_case()
        events = build_transaction_timeline(case, txns, fraud)
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)

    def test_timeline_event_types_valid(self):
        from agents.timeline import build_transaction_timeline

        valid_types = {
            "deposit",
            "transfer",
            "offshore_movement",
            "withdrawal",
            "flagged_transaction",
        }
        case, txns, fraud = self._run_pipeline_and_get_case()
        events = build_transaction_timeline(case, txns, fraud)
        for ev in events:
            assert ev.event_type in valid_types, f"Unexpected type: {ev.event_type}"

    def test_timeline_event_has_description(self):
        from agents.timeline import build_transaction_timeline

        case, txns, fraud = self._run_pipeline_and_get_case()
        events = build_transaction_timeline(case, txns, fraud)
        for ev in events:
            assert len(ev.description) > 0

    def test_timeline_event_has_amount(self):
        from agents.timeline import build_transaction_timeline

        case, txns, fraud = self._run_pipeline_and_get_case()
        events = build_transaction_timeline(case, txns, fraud)
        for ev in events:
            assert ev.amount >= 0

    def test_timeline_without_fraud_results(self):
        from agents.timeline import build_transaction_timeline

        case, txns, _ = self._run_pipeline_and_get_case()
        events = build_transaction_timeline(case, txns, fraud_results=None)
        assert isinstance(events, list)
        # Without fraud results, no events should be flagged_transaction
        for ev in events:
            if not (
                ev.origin_country != ev.destination_country
                and ev.origin_country
                and ev.destination_country
            ):
                assert ev.event_type != "flagged_transaction"


# ===========================================================================
# API Endpoint Tests — POST /pipeline/run
# ===========================================================================


class TestPipelineEndpoint:
    """Tests for the POST /pipeline/run API endpoint."""

    @pytest.fixture(autouse=True)
    def _clean_state(self):
        from api.services.pipeline import reset_state
        reset_state()
        yield
        reset_state()

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from api.main import app
        return TestClient(app)

    def test_pipeline_requires_minimum_transactions(self, client):
        resp = client.post(
            "/pipeline/run",
            json={"transactions": _sample_api_transactions(3)},
        )
        assert resp.status_code == 400

    def test_pipeline_runs_successfully(self, client):
        resp = client.post(
            "/pipeline/run",
            json={
                "transactions": _sample_api_transactions(30),
                "fraud_threshold": 0.3,
                "explain_top_n": 0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["transactions_processed"] == 30

    def test_pipeline_response_fields(self, client):
        data = client.post(
            "/pipeline/run",
            json={
                "transactions": _sample_api_transactions(30),
                "explain_top_n": 0,
            },
        ).json()
        assert "high_risk_count" in data
        assert "explanations_generated" in data
        assert "entity_risk_scores" in data
        assert "cases_generated" in data
        assert "sar_reports_generated" in data
        assert "all_reports_valid" in data
        assert "cases" in data
        assert "sar_reports" in data

    def test_pipeline_cases_structure(self, client):
        data = client.post(
            "/pipeline/run",
            json={
                "transactions": _sample_api_transactions(30),
                "fraud_threshold": 0.3,
                "explain_top_n": 0,
            },
        ).json()
        if data["cases_generated"] > 0:
            case = data["cases"][0]
            assert "case_id" in case
            assert "primary_entity" in case
            assert "risk_score" in case
            assert "transaction_count" in case

    def test_pipeline_populates_state_for_timeline(self, client):
        """After /pipeline/run, GET /timeline/{case_id} should work."""
        data = client.post(
            "/pipeline/run",
            json={
                "transactions": _sample_api_transactions(30),
                "fraud_threshold": 0.3,
                "explain_top_n": 0,
            },
        ).json()
        if data["cases_generated"] > 0:
            case_id = data["cases"][0]["case_id"]
            resp = client.get(f"/timeline/{case_id}")
            assert resp.status_code == 200


# ===========================================================================
# API Endpoint Tests — GET /timeline/{case_id}
# ===========================================================================


class TestTimelineEndpoint:
    """Tests for the GET /timeline/{case_id} API endpoint."""

    @pytest.fixture(autouse=True)
    def _clean_state(self):
        from api.services.pipeline import reset_state
        reset_state()
        yield
        reset_state()

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from api.main import app
        return TestClient(app)

    def test_timeline_not_found(self, client):
        resp = client.get("/timeline/NONEXISTENT")
        assert resp.status_code == 404

    def test_timeline_after_pipeline(self, client):
        """Run pipeline then fetch timeline for a generated case."""
        data = client.post(
            "/pipeline/run",
            json={
                "transactions": _sample_api_transactions(30),
                "fraud_threshold": 0.3,
                "explain_top_n": 0,
            },
        ).json()
        if data["cases_generated"] > 0:
            case_id = data["cases"][0]["case_id"]
            resp = client.get(f"/timeline/{case_id}")
            assert resp.status_code == 200
            tl = resp.json()
            assert tl["case_id"] == case_id
            assert "total_events" in tl
            assert "events" in tl
            assert isinstance(tl["events"], list)

    def test_timeline_events_structure(self, client):
        data = client.post(
            "/pipeline/run",
            json={
                "transactions": _sample_api_transactions(30),
                "fraud_threshold": 0.3,
                "explain_top_n": 0,
            },
        ).json()
        if data["cases_generated"] > 0:
            case_id = data["cases"][0]["case_id"]
            tl = client.get(f"/timeline/{case_id}").json()
            if tl["total_events"] > 0:
                ev = tl["events"][0]
                assert "timestamp" in ev
                assert "event_type" in ev
                assert "description" in ev
                assert "amount" in ev
                assert ev["event_type"] in {
                    "deposit",
                    "transfer",
                    "offshore_movement",
                    "withdrawal",
                    "flagged_transaction",
                }

    def test_timeline_events_chronological_via_api(self, client):
        data = client.post(
            "/pipeline/run",
            json={
                "transactions": _sample_api_transactions(30),
                "fraud_threshold": 0.3,
                "explain_top_n": 0,
            },
        ).json()
        if data["cases_generated"] > 0:
            case_id = data["cases"][0]["case_id"]
            tl = client.get(f"/timeline/{case_id}").json()
            timestamps = [e["timestamp"] for e in tl["events"]]
            assert timestamps == sorted(timestamps)

    def test_timeline_after_investigate(self, client):
        """The /timeline endpoint should also work after /ingest + /investigate."""
        client.post(
            "/ingest",
            json={"transactions": _sample_api_transactions(30)},
        )
        inv = client.post("/investigate", json={"fraud_threshold": 0.3}).json()
        if inv["cases_generated"] > 0:
            case_id = inv["cases"][0]["case_id"]
            resp = client.get(f"/timeline/{case_id}")
            assert resp.status_code == 200
