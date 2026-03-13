"""
FinSentry - API Request/Response Schemas
=============================================

Pydantic models for all FastAPI endpoint request and response bodies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# /ingest
# ---------------------------------------------------------------------------


class TransactionInput(BaseModel):
    """A single raw transaction for ingestion."""

    transaction_id: str
    account_id: str
    sender_entity_id: str
    receiver_entity_id: str
    amount: float
    currency: str
    timestamp: str  # ISO-format string
    origin_country: str
    destination_country: str
    merchant_category: str = "general"
    transaction_type: str = "wire"
    channel: str = "online"
    is_international: bool = False
    risk_flag: Optional[str] = None


class IngestRequest(BaseModel):
    """Request body for POST /ingest."""

    transactions: list[TransactionInput]


class IngestResponse(BaseModel):
    """Response body for POST /ingest."""

    total_rows: int
    valid_count: int
    invalid_count: int
    normalized_count: int
    international_count: int
    large_transaction_count: int
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# /detect
# ---------------------------------------------------------------------------


class FraudScoreOut(BaseModel):
    """Fraud score for a single transaction."""

    transaction_id: str
    fraud_probability: float
    anomaly_score: float
    risk_level: str


class DetectionResultOut(BaseModel):
    """Detection result for a single transaction."""

    transaction_id: str
    features_used: list[str]
    fraud_score: FraudScoreOut


class DetectRequest(BaseModel):
    """Request body for POST /detect."""

    contamination: float = 0.15
    n_estimators: int = 100


class DetectResponse(BaseModel):
    """Response body for POST /detect."""

    total_scored: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    results: list[DetectionResultOut]


# ---------------------------------------------------------------------------
# /investigate
# ---------------------------------------------------------------------------


class InvestigateRequest(BaseModel):
    """Request body for POST /investigate."""

    fraud_threshold: float = 0.5


class CaseOut(BaseModel):
    """Serializable investigation case."""

    case_id: str
    primary_entity: str
    related_entities: list[str]
    transactions: list[str]
    fraud_scores: dict[str, float]
    graph_metrics: dict[str, float]
    risk_score: float
    risk_indicator_count: int
    evidence_count: int


class InvestigateResponse(BaseModel):
    """Response body for POST /investigate."""

    cases_generated: int
    cases: list[CaseOut]


# ---------------------------------------------------------------------------
# /case/{case_id}
# ---------------------------------------------------------------------------


class RiskIndicatorOut(BaseModel):
    """A risk indicator in a case."""

    indicator_type: str
    severity: str
    description: str


class EvidenceOut(BaseModel):
    """A piece of supporting evidence."""

    evidence_type: str
    description: str
    related_transactions: list[str]
    related_entities: list[str]


class CaseDetailResponse(BaseModel):
    """Response body for GET /case/{case_id}."""

    case_id: str
    primary_entity: str
    related_entities: list[str]
    transactions: list[str]
    fraud_scores: dict[str, float]
    graph_metrics: dict[str, float]
    risk_indicators: list[RiskIndicatorOut]
    evidence: list[EvidenceOut]
    risk_score: float
    created_at: str


# ---------------------------------------------------------------------------
# /sar/generate
# ---------------------------------------------------------------------------


class SARGenerateRequest(BaseModel):
    """Request body for POST /sar/generate."""

    case_id: str


class SARReportOut(BaseModel):
    """Serializable SAR report."""

    report_id: str
    case_id: str
    subject_entity: str
    report_date: str
    suspicious_activity_description: str
    transaction_summary: str
    evidence_summary: str
    risk_assessment: str
    recommended_action: str
    entities_involved: list[str]
    jurisdictions: list[str]
    total_amount: float
    risk_score: float


class SARGenerateResponse(BaseModel):
    """Response body for POST /sar/generate."""

    report: SARReportOut


# ---------------------------------------------------------------------------
# /sar/validate
# ---------------------------------------------------------------------------


class SARValidateRequest(BaseModel):
    """Request body for POST /sar/validate."""

    report_id: str
    case_id: str
    subject_entity: str
    suspicious_activity_description: str = ""
    transaction_summary: str = ""
    evidence_summary: str = ""
    risk_assessment: str = ""
    recommended_action: str = ""
    entities_involved: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    total_amount: float = 0.0
    risk_score: float = 0.0


class ViolationOut(BaseModel):
    """A single validation rule violation."""

    rule_name: str
    severity: str
    field: Optional[str] = None
    message: str


class SARValidateResponse(BaseModel):
    """Response body for POST /sar/validate."""

    report_id: str
    is_valid: bool
    error_count: int
    warning_count: int
    rules_checked: int
    violations: list[ViolationOut]


# ---------------------------------------------------------------------------
# /sar/list  &  /sar/{report_id}
# ---------------------------------------------------------------------------


class SARListItem(BaseModel):
    """Summary of a stored SAR report."""

    report_id: str
    case_id: str
    subject_entity: str
    report_date: str
    risk_score: float


class SARListResponse(BaseModel):
    """Response body for GET /sar/list."""

    total: int
    reports: list[SARListItem]


# ---------------------------------------------------------------------------
# /graph/{entity_id}
# ---------------------------------------------------------------------------


class NeighborOut(BaseModel):
    """A graph neighbor of an entity."""

    entity_id: str
    direction: str  # "incoming" or "outgoing"
    transaction_amount: float
    fraud_score: float


class GraphEntityResponse(BaseModel):
    """Response body for GET /graph/{entity_id}."""

    entity_id: str
    entity_type: str
    degree_centrality: float
    betweenness_centrality: float = 0.0
    pagerank: float
    in_degree: int
    out_degree: int
    community_id: int
    neighbors: list[NeighborOut]


# ---------------------------------------------------------------------------
# /pipeline/run
# ---------------------------------------------------------------------------


class PipelineRunRequest(BaseModel):
    """Request body for POST /pipeline/run."""

    transactions: list[TransactionInput]
    fraud_threshold: float = 0.5
    contamination: float = 0.15
    n_estimators: int = 100
    explain_top_n: int = 20


class PipelineCaseOut(BaseModel):
    """Case summary within pipeline results."""

    case_id: str
    primary_entity: str
    risk_score: float
    transaction_count: int
    evidence_count: int


class PipelineSAROut(BaseModel):
    """SAR summary within pipeline results."""

    report_id: str
    case_id: str
    subject_entity: str
    risk_score: float
    is_valid: bool


class PipelineRunResponse(BaseModel):
    """Response body for POST /pipeline/run."""

    transactions_processed: int
    high_risk_count: int
    explanations_generated: int
    entity_risk_scores: int
    aml_patterns_detected: int = 0
    risk_explanations_generated: int = 0
    narratives_generated: int = 0
    cases_generated: int
    sar_reports_generated: int
    all_reports_valid: bool
    cases: list[PipelineCaseOut]
    sar_reports: list[PipelineSAROut]


# ---------------------------------------------------------------------------
# /timeline/{case_id}
# ---------------------------------------------------------------------------


class TimelineEventOut(BaseModel):
    """A single event in a case timeline."""

    timestamp: str
    event_type: str
    description: str
    transaction_id: Optional[str] = None
    sender: Optional[str] = None
    receiver: Optional[str] = None
    amount: float = 0.0
    currency: str = "USD"
    origin_country: str = ""
    destination_country: str = ""
    fraud_score: Optional[float] = None
    risk_level: Optional[str] = None


class TimelineResponse(BaseModel):
    """Response body for GET /timeline/{case_id}."""

    case_id: str
    total_events: int
    events: list[TimelineEventOut]


# ---------------------------------------------------------------------------
# /entity/{entity_id}
# ---------------------------------------------------------------------------


class EntityProfileResponse(BaseModel):
    """Response body for GET /entity/{entity_id}."""

    entity_id: str
    jurisdiction: str = ""
    risk_score: float = 0.0
    connected_entities: list[str] = Field(default_factory=list)
    total_transaction_value: float = 0.0
    total_transactions: int = 0
    fraud_transactions: int = 0
    detected_patterns: list[str] = Field(default_factory=list)
    suspicious_activity_summary: str = ""


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Response body for GET /."""

    status: str = "ok"
    service: str = "FinSentry"
    modules_loaded: int = 0
    transactions_loaded: int = 0
    cases_generated: int = 0
    sar_reports_generated: int = 0


# ---------------------------------------------------------------------------
# /investigation/query  (Investigation Copilot)
# ---------------------------------------------------------------------------


class InvestigationQueryRequest(BaseModel):
    """Request body for POST /investigation/query."""

    question: str


class InvestigationDriverOut(BaseModel):
    """A single factor contributing to the explanation."""

    factor: str
    detail: str
    weight: float = 0.0


class InvestigationQueryResponse(BaseModel):
    """Response body for POST /investigation/query."""

    entity_id: str = ""
    question: str
    answer: str
    risk_score: float = 0.0
    risk_level: str = "unknown"
    drivers: list[InvestigationDriverOut] = Field(default_factory=list)
    aml_patterns: list[str] = Field(default_factory=list)
    connected_entities: list[str] = Field(default_factory=list)
    graph_insights: str = ""
