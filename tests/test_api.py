"""
FinSentry - API Endpoint Tests
====================================

Tests covering all FastAPI endpoints using the TestClient.

Follows a sequential test flow:
1. Health check
2. Ingest transactions
3. Detect fraud
4. Investigate (full pipeline)
5. Get case details
6. Generate SAR
7. Validate SAR
8. Query graph entity

Run::

    cd /path/to/FinSentry
    python -m pytest tests/test_api.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from api.main import app
from api.services.pipeline import reset_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset application state before each test."""
    reset_state()
    yield
    reset_state()


@pytest.fixture()
def client() -> TestClient:
    """Return a FastAPI TestClient."""
    return TestClient(app)


def _sample_transactions(n: int = 30) -> list[dict]:
    """Generate sample transaction dicts for ingestion.

    Generates a mix of normal, international high-value, and medium
    transactions to produce a realistic fraud detection distribution.
    """
    import random

    random.seed(42)
    txns = []
    for i in range(n):
        if i % 5 == 0:
            # Suspicious: high-value, international, odd hour
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
            # Medium: moderate value, international
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
            # Normal: domestic, low-value
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
# Health check
# ===========================================================================


class TestHealthCheck:
    """Tests for the root health-check endpoint."""

    def test_health_returns_200(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_health_response_fields(self, client: TestClient):
        data = client.get("/").json()
        assert data["status"] == "ok"
        assert data["service"] == "FinSentry"
        assert "modules_loaded" in data
        assert "transactions_loaded" in data


# ===========================================================================
# POST /ingest
# ===========================================================================


class TestIngestEndpoint:
    """Tests for the /ingest endpoint."""

    def test_ingest_transactions(self, client: TestClient):
        txns = _sample_transactions(10)
        resp = client.post("/ingest", json={"transactions": txns})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 10
        assert data["valid_count"] == 10
        assert data["invalid_count"] == 0

    def test_ingest_empty_list(self, client: TestClient):
        resp = client.post("/ingest", json={"transactions": []})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 0

    def test_ingest_counts_international(self, client: TestClient):
        txns = _sample_transactions(30)
        resp = client.post("/ingest", json={"transactions": txns})
        data = resp.json()
        assert data["international_count"] > 0


# ===========================================================================
# POST /detect
# ===========================================================================


class TestDetectEndpoint:
    """Tests for the /detect endpoint."""

    def test_detect_requires_transactions(self, client: TestClient):
        resp = client.post("/detect", json={})
        assert resp.status_code == 400

    def test_detect_requires_minimum_transactions(self, client: TestClient):
        txns = _sample_transactions(3)
        client.post("/ingest", json={"transactions": txns})
        resp = client.post("/detect", json={})
        assert resp.status_code == 400

    def test_detect_returns_results(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        resp = client.post("/detect", json={"contamination": 0.15})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_scored"] == 30
        assert len(data["results"]) == 30

    def test_detect_risk_levels(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        data = client.post("/detect", json={}).json()
        assert data["high_risk_count"] >= 0
        assert data["medium_risk_count"] >= 0
        assert data["low_risk_count"] >= 0
        assert (
            data["high_risk_count"]
            + data["medium_risk_count"]
            + data["low_risk_count"]
        ) == data["total_scored"]

    def test_detect_result_structure(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        data = client.post("/detect", json={}).json()
        result = data["results"][0]
        assert "transaction_id" in result
        assert "features_used" in result
        assert "fraud_score" in result
        fs = result["fraud_score"]
        assert 0.0 <= fs["fraud_probability"] <= 1.0
        assert fs["risk_level"] in ("HIGH", "MEDIUM", "LOW")


# ===========================================================================
# POST /investigate
# ===========================================================================


class TestInvestigateEndpoint:
    """Tests for the /investigate endpoint."""

    def test_investigate_requires_transactions(self, client: TestClient):
        resp = client.post("/investigate", json={})
        assert resp.status_code == 400

    def test_investigate_returns_cases(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        resp = client.post("/investigate", json={"fraud_threshold": 0.5})
        assert resp.status_code == 200
        data = resp.json()
        assert "cases_generated" in data
        assert "cases" in data
        assert isinstance(data["cases"], list)

    def test_investigate_case_structure(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        data = client.post("/investigate", json={"fraud_threshold": 0.3}).json()
        if data["cases_generated"] > 0:
            case = data["cases"][0]
            assert "case_id" in case
            assert "primary_entity" in case
            assert "risk_score" in case
            assert 0.0 <= case["risk_score"] <= 1.0


# ===========================================================================
# GET /case/{case_id}
# ===========================================================================


class TestGetCaseEndpoint:
    """Tests for the /case/{case_id} endpoint."""

    def test_case_not_found(self, client: TestClient):
        resp = client.get("/case/NONEXISTENT")
        assert resp.status_code == 404

    def test_case_retrieval(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        inv = client.post("/investigate", json={"fraud_threshold": 0.3}).json()
        if inv["cases_generated"] > 0:
            case_id = inv["cases"][0]["case_id"]
            resp = client.get(f"/case/{case_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["case_id"] == case_id
            assert "risk_indicators" in data
            assert "evidence" in data
            assert "created_at" in data


# ===========================================================================
# POST /sar/generate
# ===========================================================================


class TestSARGenerateEndpoint:
    """Tests for the /sar/generate endpoint."""

    def test_generate_case_not_found(self, client: TestClient):
        resp = client.post("/sar/generate", json={"case_id": "FAKE"})
        assert resp.status_code == 404

    def test_generate_sar_report(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        inv = client.post("/investigate", json={"fraud_threshold": 0.3}).json()
        if inv["cases_generated"] > 0:
            case_id = inv["cases"][0]["case_id"]
            resp = client.post("/sar/generate", json={"case_id": case_id})
            assert resp.status_code == 200
            data = resp.json()
            report = data["report"]
            assert report["case_id"] == case_id
            assert report["report_id"].startswith("SAR-")
            assert len(report["suspicious_activity_description"]) > 0


# ===========================================================================
# POST /sar/validate
# ===========================================================================


class TestSARValidateEndpoint:
    """Tests for the /sar/validate endpoint."""

    def test_validate_valid_report(self, client: TestClient):
        report = {
            "report_id": "SAR-TEST-001",
            "case_id": "CASE-001",
            "subject_entity": "ENT-SUSPECT",
            "suspicious_activity_description": (
                "The subject entity conducted multiple large wire transfers "
                "to offshore accounts in a pattern consistent with layering."
            ),
            "transaction_summary": (
                "Five wire transfers totalling USD 250,000 were sent to the "
                "Cayman Islands from account ACC-001."
            ),
            "evidence_summary": (
                "Graph analysis revealed circular fund flows between three "
                "entities with high centrality scores."
            ),
            "risk_assessment": "HIGH risk due to cross-border flows and layering.",
            "recommended_action": "File SAR with FinCEN immediately.",
            "entities_involved": ["ENT-SUSPECT", "ENT-R001"],
            "jurisdictions": ["US", "KY"],
            "total_amount": 250000.0,
            "risk_score": 0.92,
        }
        resp = client.post("/sar/validate", json=report)
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is True
        assert data["error_count"] == 0

    def test_validate_invalid_report(self, client: TestClient):
        report = {
            "report_id": "SAR-EMPTY",
            "case_id": "CASE-EMPTY",
            "subject_entity": "",
        }
        resp = client.post("/sar/validate", json=report)
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is False
        assert data["error_count"] > 0
        assert len(data["violations"]) > 0

    def test_validate_response_structure(self, client: TestClient):
        report = {
            "report_id": "SAR-STRUCT",
            "case_id": "CASE-S",
            "subject_entity": "ENT-S001",
            "suspicious_activity_description": "Short.",
            "transaction_summary": "Summary.",
            "risk_assessment": "Low.",
        }
        resp = client.post("/sar/validate", json=report)
        data = resp.json()
        assert "rules_checked" in data
        assert data["rules_checked"] == 5
        for v in data["violations"]:
            assert "rule_name" in v
            assert "severity" in v
            assert "message" in v


# ===========================================================================
# GET /graph/{entity_id}
# ===========================================================================


class TestGraphEntityEndpoint:
    """Tests for the /graph/{entity_id} endpoint."""

    def test_graph_requires_investigation(self, client: TestClient):
        resp = client.get("/graph/ENT-S001")
        assert resp.status_code == 400

    def test_graph_entity_not_found(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        client.post("/investigate", json={"fraud_threshold": 0.3})
        resp = client.get("/graph/NONEXISTENT-ENTITY")
        assert resp.status_code == 404

    def test_graph_entity_metrics(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        client.post("/investigate", json={"fraud_threshold": 0.3})
        # Use an entity we know exists from the sample data
        resp = client.get("/graph/ENT-S000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "ENT-S000"
        assert "degree_centrality" in data
        assert "pagerank" in data
        assert "neighbors" in data
        assert isinstance(data["neighbors"], list)

    def test_graph_neighbor_structure(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        client.post("/investigate", json={"fraud_threshold": 0.3})
        data = client.get("/graph/ENT-S000").json()
        if data["neighbors"]:
            neighbor = data["neighbors"][0]
            assert "entity_id" in neighbor
            assert "direction" in neighbor
            assert neighbor["direction"] in ("incoming", "outgoing")
            assert "transaction_amount" in neighbor
            assert "fraud_score" in neighbor


# ===========================================================================
# GET /sar/{report_id}/download
# ===========================================================================


class TestSARDownloadEndpoint:
    """Tests for the /sar/{report_id}/download endpoint."""

    def test_download_report_not_found(self, client: TestClient):
        resp = client.get("/sar/NONEXISTENT/download")
        assert resp.status_code == 404

    def test_download_returns_pdf(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        inv = client.post("/investigate", json={"fraud_threshold": 0.3}).json()
        if inv["cases_generated"] > 0:
            case_id = inv["cases"][0]["case_id"]
            sar = client.post("/sar/generate", json={"case_id": case_id}).json()
            report_id = sar["report"]["report_id"]

            resp = client.get(f"/sar/{report_id}/download")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/pdf"
            assert "attachment" in resp.headers.get("content-disposition", "")
            # Validate PDF magic bytes
            assert resp.content[:5] == b"%PDF-"

    def test_download_pdf_contains_report_id(self, client: TestClient):
        txns = _sample_transactions(30)
        client.post("/ingest", json={"transactions": txns})
        inv = client.post("/investigate", json={"fraud_threshold": 0.3}).json()
        if inv["cases_generated"] > 0:
            case_id = inv["cases"][0]["case_id"]
            sar = client.post("/sar/generate", json={"case_id": case_id}).json()
            report_id = sar["report"]["report_id"]

            resp = client.get(f"/sar/{report_id}/download")
            assert resp.status_code == 200
            # Filename in Content-Disposition must contain the report ID
            disposition = resp.headers.get("content-disposition", "")
            assert report_id in disposition
            # PDF must be non-trivial (more than just a header)
            assert len(resp.content) > 500
