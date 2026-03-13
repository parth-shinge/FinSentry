"""
FinSentry - API Routes
============================

FastAPI router exposing the full FinSentry pipeline through REST endpoints.

Endpoints
---------
POST /ingest           Upload and normalise transactions.
POST /detect           Run fraud detection on loaded transactions.
POST /investigate      Run the full investigation pipeline.
GET  /case/{case_id}   Retrieve a specific investigation case.
POST /sar/generate     Generate a SAR report for a case.
POST /sar/validate     Validate a SAR report against compliance rules.
GET  /graph/{entity_id} Return graph metrics and neighbors.
POST /pipeline/run     Run full orchestrated investigation pipeline.
GET  /timeline/{case_id} Return timeline reconstruction for a case.
GET  /sar/list         List all generated SAR reports.
GET  /sar/{report_id}  Retrieve a specific SAR report.
POST /investigation/query  Investigation Copilot.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import (
    CaseDetailResponse,
    CaseOut,
    DetectRequest,
    DetectResponse,
    DetectionResultOut,
    EntityProfileResponse,
    EvidenceOut,
    FraudScoreOut,
    GraphEntityResponse,
    IngestRequest,
    IngestResponse,
    InvestigateRequest,
    InvestigateResponse,
    InvestigationDriverOut,
    InvestigationQueryRequest,
    InvestigationQueryResponse,
    NeighborOut,
    PipelineCaseOut,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineSAROut,
    RiskIndicatorOut,
    SARGenerateRequest,
    SARGenerateResponse,
    SARListItem,
    SARListResponse,
    SARReportOut,
    SARValidateRequest,
    SARValidateResponse,
    TimelineEventOut,
    TimelineResponse,
    ViolationOut,
)
from api.services.pipeline import (
    generate_sar_for_case,
    get_state,
    run_detection,
    run_investigation_pipeline,
    validate_sar_report,
)
from fraud_detection.models import RiskLevel
from ingestion.schema import NormalizedTransaction
from sar_generator.models import SARReport

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /ingest
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=IngestResponse)
def ingest_transactions(request: IngestRequest) -> IngestResponse:
    """Load, validate, and normalise transactions into memory."""
    state = get_state()

    normalized: list[NormalizedTransaction] = []
    errors: list[str] = []

    for i, txn_input in enumerate(request.transactions):
        try:
            txn = NormalizedTransaction(
                transaction_id=txn_input.transaction_id,
                account_id=txn_input.account_id,
                sender_entity_id=txn_input.sender_entity_id,
                receiver_entity_id=txn_input.receiver_entity_id,
                amount=txn_input.amount,
                currency=txn_input.currency.upper(),
                timestamp=txn_input.timestamp,
                origin_country=txn_input.origin_country.upper(),
                destination_country=txn_input.destination_country.upper(),
                merchant_category=txn_input.merchant_category,
                transaction_type=txn_input.transaction_type,
                channel=txn_input.channel,
                risk_flag=txn_input.risk_flag,
            )
            normalized.append(txn)
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")

    state.transactions.extend(normalized)

    return IngestResponse(
        total_rows=len(request.transactions),
        valid_count=len(normalized),
        invalid_count=len(errors),
        normalized_count=len(normalized),
        international_count=sum(1 for t in normalized if t.is_international),
        large_transaction_count=sum(
            1 for t in normalized if t.is_large_transaction
        ),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# POST /detect
# ---------------------------------------------------------------------------


@router.post("/detect", response_model=DetectResponse)
def detect_fraud(request: DetectRequest) -> DetectResponse:
    """Run fraud detection on loaded transactions."""
    state = get_state()

    if not state.transactions:
        raise HTTPException(
            status_code=400,
            detail="No transactions loaded. Call POST /ingest first.",
        )

    if len(state.transactions) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 5 transactions to train, got {len(state.transactions)}.",
        )

    try:
        results = run_detection(
            contamination=request.contamination,
            n_estimators=request.n_estimators,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    result_outs = [
        DetectionResultOut(
            transaction_id=r.transaction_id,
            features_used=r.features_used,
            fraud_score=FraudScoreOut(
                transaction_id=r.fraud_score.transaction_id,
                fraud_probability=r.fraud_score.fraud_probability,
                anomaly_score=r.fraud_score.anomaly_score,
                risk_level=r.fraud_score.risk_level.value,
            ),
        )
        for r in results
    ]

    return DetectResponse(
        total_scored=len(results),
        high_risk_count=sum(
            1 for r in results if r.fraud_score.risk_level == RiskLevel.HIGH
        ),
        medium_risk_count=sum(
            1 for r in results if r.fraud_score.risk_level == RiskLevel.MEDIUM
        ),
        low_risk_count=sum(
            1 for r in results if r.fraud_score.risk_level == RiskLevel.LOW
        ),
        results=result_outs,
    )


# ---------------------------------------------------------------------------
# POST /investigate
# ---------------------------------------------------------------------------


@router.post("/investigate", response_model=InvestigateResponse)
def investigate(request: InvestigateRequest) -> InvestigateResponse:
    """Run the full investigation pipeline."""
    state = get_state()

    if not state.transactions:
        raise HTTPException(
            status_code=400,
            detail="No transactions loaded. Call POST /ingest first.",
        )

    try:
        cases = run_investigation_pipeline(
            fraud_threshold=request.fraud_threshold,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    case_outs = [
        CaseOut(
            case_id=c.case_id,
            primary_entity=c.primary_entity,
            related_entities=list(c.related_entities),
            transactions=list(c.transactions),
            fraud_scores=dict(c.fraud_scores),
            graph_metrics=dict(c.graph_metrics),
            risk_score=c.risk_score,
            risk_indicator_count=len(c.risk_indicators),
            evidence_count=len(c.evidence),
        )
        for c in cases
    ]

    return InvestigateResponse(
        cases_generated=len(cases),
        cases=case_outs,
    )


# ---------------------------------------------------------------------------
# GET /case/{case_id}
# ---------------------------------------------------------------------------


@router.get("/case/{case_id}", response_model=CaseDetailResponse)
def get_case(case_id: str) -> CaseDetailResponse:
    """Retrieve details of a specific investigation case."""
    state = get_state()

    if case_id not in state.cases:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    case = state.cases[case_id]

    return CaseDetailResponse(
        case_id=case.case_id,
        primary_entity=case.primary_entity,
        related_entities=list(case.related_entities),
        transactions=list(case.transactions),
        fraud_scores=dict(case.fraud_scores),
        graph_metrics=dict(case.graph_metrics),
        risk_indicators=[
            RiskIndicatorOut(
                indicator_type=ri.indicator_type,
                severity=ri.severity,
                description=ri.description,
            )
            for ri in case.risk_indicators
        ],
        evidence=[
            EvidenceOut(
                evidence_type=ev.evidence_type,
                description=ev.description,
                related_transactions=list(ev.related_transactions),
                related_entities=list(ev.related_entities),
            )
            for ev in case.evidence
        ],
        risk_score=case.risk_score,
        created_at=case.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# POST /sar/generate
# ---------------------------------------------------------------------------


@router.post("/sar/generate", response_model=SARGenerateResponse)
def generate_sar(request: SARGenerateRequest) -> SARGenerateResponse:
    """Generate a SAR report for a specific case."""
    try:
        report = generate_sar_for_case(request.case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return SARGenerateResponse(
        report=SARReportOut(
            report_id=report.report_id,
            case_id=report.case_id,
            subject_entity=report.subject_entity,
            report_date=report.report_date.isoformat(),
            suspicious_activity_description=report.suspicious_activity_description,
            transaction_summary=report.transaction_summary,
            evidence_summary=report.evidence_summary,
            risk_assessment=report.risk_assessment,
            recommended_action=report.recommended_action,
            entities_involved=list(report.entities_involved),
            jurisdictions=list(report.jurisdictions),
            total_amount=report.total_amount,
            risk_score=report.risk_score,
        ),
    )


# ---------------------------------------------------------------------------
# POST /sar/validate
# ---------------------------------------------------------------------------


@router.post("/sar/validate", response_model=SARValidateResponse)
def validate_sar(request: SARValidateRequest) -> SARValidateResponse:
    """Validate a SAR report against compliance rules."""
    report = SARReport(
        report_id=request.report_id,
        case_id=request.case_id,
        subject_entity=request.subject_entity,
        suspicious_activity_description=request.suspicious_activity_description,
        transaction_summary=request.transaction_summary,
        evidence_summary=request.evidence_summary,
        risk_assessment=request.risk_assessment,
        recommended_action=request.recommended_action,
        entities_involved=request.entities_involved,
        jurisdictions=request.jurisdictions,
        total_amount=request.total_amount,
        risk_score=request.risk_score,
    )

    result = validate_sar_report(report)

    return SARValidateResponse(
        report_id=result.report_id,
        is_valid=result.is_valid,
        error_count=result.error_count,
        warning_count=result.warning_count,
        rules_checked=result.rules_checked,
        violations=[
            ViolationOut(
                rule_name=v.rule_name,
                severity=v.severity.value,
                field=v.field,
                message=v.message,
            )
            for v in result.violations
        ],
    )


# ---------------------------------------------------------------------------
# GET /sar/list
# ---------------------------------------------------------------------------


@router.get("/sar/list", response_model=SARListResponse)
def list_sar_reports() -> SARListResponse:
    """Return all generated SAR reports."""
    state = get_state()

    items = [
        SARListItem(
            report_id=r.report_id,
            case_id=r.case_id,
            subject_entity=r.subject_entity,
            report_date=r.report_date.isoformat(),
            risk_score=r.risk_score,
        )
        for r in state.sar_reports.values()
    ]

    return SARListResponse(total=len(items), reports=items)


# ---------------------------------------------------------------------------
# GET /sar/{report_id}
# ---------------------------------------------------------------------------


@router.get("/sar/{report_id}", response_model=SARReportOut)
def get_sar_report(report_id: str) -> SARReportOut:
    """Retrieve a specific SAR report by ID."""
    state = get_state()

    if report_id not in state.sar_reports:
        raise HTTPException(
            status_code=404,
            detail=f"SAR report '{report_id}' not found.",
        )

    report = state.sar_reports[report_id]
    return SARReportOut(
        report_id=report.report_id,
        case_id=report.case_id,
        subject_entity=report.subject_entity,
        report_date=report.report_date.isoformat(),
        suspicious_activity_description=report.suspicious_activity_description,
        transaction_summary=report.transaction_summary,
        evidence_summary=report.evidence_summary,
        risk_assessment=report.risk_assessment,
        recommended_action=report.recommended_action,
        entities_involved=list(report.entities_involved),
        jurisdictions=list(report.jurisdictions),
        total_amount=report.total_amount,
        risk_score=report.risk_score,
    )


# ---------------------------------------------------------------------------
# GET /graph/{entity_id}
# ---------------------------------------------------------------------------


@router.get("/graph/{entity_id}", response_model=GraphEntityResponse)
def get_graph_entity(entity_id: str) -> GraphEntityResponse:
    """Return graph metrics and neighbors for a specific entity."""
    state = get_state()

    if state.graph is None or state.analyzer is None:
        raise HTTPException(
            status_code=400,
            detail="Graph not built. Call POST /investigate first.",
        )

    if entity_id not in state.graph:
        raise HTTPException(
            status_code=404,
            detail=f"Entity '{entity_id}' not found in the graph.",
        )

    graph = state.graph

    # Node data
    node_data = dict(graph.nodes[entity_id])

    # Centrality metrics
    centrality = state.analyzer.compute_centrality()
    metrics = centrality.get(entity_id)

    # Collect neighbors
    neighbors: list[NeighborOut] = []

    for succ in graph.successors(entity_id):
        edge_data = dict(graph.edges[entity_id, succ])
        neighbors.append(
            NeighborOut(
                entity_id=str(succ),
                direction="outgoing",
                transaction_amount=float(edge_data.get("amount", 0.0)),
                fraud_score=float(edge_data.get("fraud_score", 0.0)),
            )
        )

    for pred in graph.predecessors(entity_id):
        edge_data = dict(graph.edges[pred, entity_id])
        neighbors.append(
            NeighborOut(
                entity_id=str(pred),
                direction="incoming",
                transaction_amount=float(edge_data.get("amount", 0.0)),
                fraud_score=float(edge_data.get("fraud_score", 0.0)),
            )
        )

    return GraphEntityResponse(
        entity_id=entity_id,
        entity_type=str(node_data.get("entity_type", "unknown")),
        degree_centrality=metrics.degree_centrality if metrics else 0.0,
        betweenness_centrality=metrics.betweenness_centrality if metrics else 0.0,
        pagerank=metrics.pagerank if metrics else 0.0,
        in_degree=metrics.in_degree if metrics else 0,
        out_degree=metrics.out_degree if metrics else 0,
        community_id=metrics.community_id if metrics else -1,
        neighbors=neighbors,
    )


# ---------------------------------------------------------------------------
# GET /entity/{entity_id}
# ---------------------------------------------------------------------------


def _build_entity_summary(
    entity_id: str,
    risk_score: float,
    total_txns: int,
    fraud_txns: int,
    total_value: float,
    patterns: list[str],
    connected: list[str],
    jurisdiction: str,
) -> str:
    """Build a human-readable suspicious-activity summary for an entity."""
    if total_txns == 0:
        return f"Entity {entity_id} has no recorded transactions."

    parts: list[str] = []
    risk_label = "high" if risk_score >= 0.7 else "medium" if risk_score >= 0.4 else "low"
    parts.append(
        f"Entity {entity_id} has a {risk_label} risk score ({risk_score:.2f}) "
        f"based on {total_txns} transaction(s) totaling ${total_value:,.2f}."
    )
    if fraud_txns:
        parts.append(
            f"{fraud_txns} transaction(s) flagged as high-risk fraud."
        )
    if patterns:
        labels = ", ".join(p.replace("_", " ") for p in patterns)
        parts.append(f"Detected patterns: {labels}.")
    if len(connected) > 1:
        parts.append(
            f"Connected to {len(connected)} entities in the transaction network."
        )
    return " ".join(parts)


@router.get("/entity/{entity_id}", response_model=EntityProfileResponse)
def get_entity_profile(entity_id: str) -> EntityProfileResponse:
    """Return a comprehensive entity profile with investigation metrics."""
    state = get_state()

    if state.graph is None:
        raise HTTPException(
            status_code=400,
            detail="Pipeline has not been run. Call POST /pipeline/run or POST /investigate first.",
        )

    # Jurisdiction from graph node data
    jurisdiction = ""
    if entity_id in state.graph:
        node_data = dict(state.graph.nodes[entity_id])
        jurisdiction = str(node_data.get("country", ""))

    # Connected entities
    connected: set[str] = set()
    if entity_id in state.graph:
        for succ in state.graph.successors(entity_id):
            connected.add(str(succ))
        for pred in state.graph.predecessors(entity_id):
            connected.add(str(pred))

    # Transaction metrics
    total_value = 0.0
    total_txns = 0
    fraud_txns = 0
    fraud_map = {r.transaction_id: r.fraud_score for r in state.fraud_results}

    for txn in state.transactions:
        if txn.sender_entity_id == entity_id or txn.receiver_entity_id == entity_id:
            total_value += txn.amount
            total_txns += 1
            score = fraud_map.get(txn.transaction_id)
            if score and score.risk_level.value == "HIGH":
                fraud_txns += 1

    # Risk score from graph analysis
    risk_score = 0.0
    if state.analyzer is not None:
        entity_risks = state.analyzer.compute_entity_risk_scores()
        for er in entity_risks:
            if er.entity_id == entity_id:
                risk_score = er.overall_risk_score
                break

    # Detected patterns from cases
    detected_patterns: list[str] = []
    for case in state.cases.values():
        if case.primary_entity == entity_id or entity_id in case.related_entities:
            for ri in case.risk_indicators:
                if ri.indicator_type not in detected_patterns:
                    detected_patterns.append(ri.indicator_type)

    # Generate suspicious activity summary
    suspicious_activity_summary = _build_entity_summary(
        entity_id, risk_score, total_txns, fraud_txns, total_value,
        detected_patterns, sorted(connected), jurisdiction,
    )

    return EntityProfileResponse(
        entity_id=entity_id,
        jurisdiction=jurisdiction,
        risk_score=round(risk_score, 4),
        connected_entities=sorted(connected),
        total_transaction_value=round(total_value, 2),
        total_transactions=total_txns,
        fraud_transactions=fraud_txns,
        detected_patterns=detected_patterns,
        suspicious_activity_summary=suspicious_activity_summary,
    )


# ---------------------------------------------------------------------------
# POST /pipeline/run
# ---------------------------------------------------------------------------


@router.post("/pipeline/run", response_model=PipelineRunResponse)
def run_pipeline(request: PipelineRunRequest) -> PipelineRunResponse:
    """Run the full orchestrated investigation pipeline."""
    from agents.orchestrator import InvestigationOrchestrator

    # Build NormalizedTransaction objects from input
    normalized: list[NormalizedTransaction] = []
    for txn_input in request.transactions:
        try:
            txn = NormalizedTransaction(
                transaction_id=txn_input.transaction_id,
                account_id=txn_input.account_id,
                sender_entity_id=txn_input.sender_entity_id,
                receiver_entity_id=txn_input.receiver_entity_id,
                amount=txn_input.amount,
                currency=txn_input.currency.upper(),
                timestamp=txn_input.timestamp,
                origin_country=txn_input.origin_country.upper(),
                destination_country=txn_input.destination_country.upper(),
                merchant_category=txn_input.merchant_category,
                transaction_type=txn_input.transaction_type,
                channel=txn_input.channel,
                risk_flag=txn_input.risk_flag,
            )
            normalized.append(txn)
        except Exception:
            continue

    if len(normalized) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 5 valid transactions, got {len(normalized)}.",
        )

    orchestrator = InvestigationOrchestrator(
        fraud_threshold=request.fraud_threshold,
        contamination=request.contamination,
        n_estimators=request.n_estimators,
        explain_top_n=request.explain_top_n,
    )

    try:
        result = orchestrator.run_full_investigation(normalized)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Store cases and reports in app state for retrieval by other endpoints
    state = get_state()
    state.transactions = normalized
    state.fraud_results = result.fraud_results
    state.cases = {c.case_id: c for c in result.cases}
    state.sar_reports = {r.report_id: r for r in result.sar_reports}

    # Rebuild graph in state so /graph and /entity endpoints work
    from graph_engine.builder import GraphBuilder
    from graph_engine.analyzer import GraphAnalyzer

    fraud_score_map = {
        r.transaction_id: r.fraud_score.fraud_probability
        for r in result.fraud_results
    }
    builder = GraphBuilder(load_metadata=True)
    state.graph = builder.build_transaction_graph(normalized, fraud_score_map)
    state.analyzer = GraphAnalyzer(state.graph)
    state.analyzer.compute_centrality()
    state.analyzer.detect_communities()
    state.analyzer.detect_cycles()

    # Build validation lookup
    validation_map: dict[str, bool] = {}
    for vr in result.validation_results:
        validation_map[vr.report_id] = vr.is_valid

    return PipelineRunResponse(
        transactions_processed=result.transactions_processed,
        high_risk_count=result.high_risk_count,
        explanations_generated=len(result.explanations),
        entity_risk_scores=len(result.graph_metrics),
        aml_patterns_detected=len(result.aml_patterns),
        risk_explanations_generated=len(result.risk_explanations),
        narratives_generated=len(result.narratives),
        cases_generated=result.total_cases,
        sar_reports_generated=len(result.sar_reports),
        all_reports_valid=result.all_reports_valid,
        cases=[
            PipelineCaseOut(
                case_id=c.case_id,
                primary_entity=c.primary_entity,
                risk_score=c.risk_score,
                transaction_count=len(c.transactions),
                evidence_count=len(c.evidence),
            )
            for c in result.cases
        ],
        sar_reports=[
            PipelineSAROut(
                report_id=r.report_id,
                case_id=r.case_id,
                subject_entity=r.subject_entity,
                risk_score=r.risk_score,
                is_valid=validation_map.get(r.report_id, False),
            )
            for r in result.sar_reports
        ],
    )


# ---------------------------------------------------------------------------
# GET /timeline/{case_id}
# ---------------------------------------------------------------------------


@router.get("/timeline/{case_id}", response_model=TimelineResponse)
def get_timeline(case_id: str) -> TimelineResponse:
    """Return chronological timeline reconstruction for a case."""
    from agents.timeline import build_transaction_timeline

    state = get_state()

    if case_id not in state.cases:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found.",
        )

    case = state.cases[case_id]
    events = build_transaction_timeline(
        case=case,
        transactions=state.transactions,
        fraud_results=state.fraud_results,
    )

    return TimelineResponse(
        case_id=case_id,
        total_events=len(events),
        events=[
            TimelineEventOut(
                timestamp=e.timestamp,
                event_type=e.event_type,
                description=e.description,
                transaction_id=e.transaction_id,
                sender=e.sender,
                receiver=e.receiver,
                amount=e.amount,
                currency=e.currency,
                origin_country=e.origin_country,
                destination_country=e.destination_country,
                fraud_score=e.fraud_score,
                risk_level=e.risk_level,
            )
            for e in events
        ],
    )


# ---------------------------------------------------------------------------
# POST /investigation/query  (Investigation Copilot)
# ---------------------------------------------------------------------------


def _extract_entity_from_question(question: str, known_entities: set[str]) -> str | None:
    """Robust extraction of an entity ID from a free-text question.

    Strategy:
    1. Direct substring match (existing entity ID appears in question).
    2. Regex extraction of ID-like tokens, then fuzzy match against known
       entities (handles partial matches like "7001" → "ENT-7001").
    """
    import re

    q_lower = question.lower()

    # Pass 1: exact substring match (longest first to prefer ENT-7001 over ENT-700)
    for eid in sorted(known_entities, key=len, reverse=True):
        if eid.lower() in q_lower:
            return eid

    # Pass 2: extract candidate tokens via regex and match against known entities
    # Matches: E12, E001, ENT-7001, ACC_17, CUST17, ENTITY12, 7001, etc.
    candidates = re.findall(r"\b[A-Za-z]*[-_]?\d+\b", question)
    for candidate in candidates:
        c_lower = candidate.lower()
        # Check if any known entity ends with or contains this candidate
        for eid in known_entities:
            eid_lower = eid.lower()
            # Exact match
            if c_lower == eid_lower:
                return eid
            # Candidate is the numeric suffix (e.g., "7001" matches "ENT-7001")
            if eid_lower.endswith(c_lower):
                return eid
            # Candidate without separator matches (e.g., "ENT7001" matches "ENT-7001")
            if c_lower.replace("-", "").replace("_", "") == eid_lower.replace("-", "").replace("_", ""):
                return eid

    return None


@router.post("/investigation/query", response_model=InvestigationQueryResponse)
def investigation_query(request: InvestigationQueryRequest) -> InvestigationQueryResponse:
    """Answer an investigator's question about an entity using pipeline intelligence.

    Uses risk scores, AML patterns, SHAP explanations, and graph
    relationships to produce a structured explanation.
    """
    state = get_state()
    question = request.question.strip()

    if state.graph is None:
        raise HTTPException(
            status_code=400,
            detail="Pipeline has not been run. Call POST /pipeline/run first.",
        )

    # Try to identify the entity being asked about
    known_entities: set[str] = set(str(n) for n in state.graph.nodes)
    entity_id = _extract_entity_from_question(question, known_entities)

    if not entity_id:
        sample = sorted(known_entities)[:10]
        sample_str = ", ".join(sample)
        hint = f" Available entities include: {sample_str}." if sample else ""
        return InvestigationQueryResponse(
            question=question,
            answer="Could not identify an entity in your question. "
                   "Please include a valid entity ID (e.g., 'Why is ENT-7001 suspicious?')."
                   + hint,
        )

    # ── Gather intelligence ──────────────────────────────────────

    # Risk score
    risk_score = 0.0
    if state.analyzer is not None:
        for er in state.analyzer.compute_entity_risk_scores():
            if er.entity_id == entity_id:
                risk_score = er.overall_risk_score
                break
    risk_level = "high" if risk_score >= 0.7 else "medium" if risk_score >= 0.4 else "low"

    # Connected entities
    connected: list[str] = []
    if entity_id in state.graph:
        nbrs: set[str] = set()
        for s in state.graph.successors(entity_id):
            nbrs.add(str(s))
        for p in state.graph.predecessors(entity_id):
            nbrs.add(str(p))
        connected = sorted(nbrs)

    # AML patterns from cases
    aml_patterns: list[str] = []
    for case in state.cases.values():
        if case.primary_entity == entity_id or entity_id in case.related_entities:
            for ri in case.risk_indicators:
                if ri.indicator_type not in aml_patterns:
                    aml_patterns.append(ri.indicator_type)

    # Transaction stats
    fraud_map = {r.transaction_id: r.fraud_score for r in state.fraud_results}
    total_txns = 0
    fraud_txns = 0
    total_value = 0.0
    for txn in state.transactions:
        if txn.sender_entity_id == entity_id or txn.receiver_entity_id == entity_id:
            total_txns += 1
            total_value += txn.amount
            fs = fraud_map.get(txn.transaction_id)
            if fs and fs.risk_level.value == "HIGH":
                fraud_txns += 1

    # Risk drivers from RiskExplainer
    drivers: list[InvestigationDriverOut] = []
    try:
        from explainability.risk_explainer import RiskExplainer
        from graph_engine.models import EntityRiskScore as _ERS

        explainer = RiskExplainer()
        ers = _ERS(entity_id=entity_id, overall_risk_score=risk_score)
        explanation = explainer.explain_entity_risk(
            entity_id=entity_id,
            entity_risk=ers,
            transactions=state.transactions,
            graph=state.graph,
        )
        for d in explanation.drivers:
            drivers.append(InvestigationDriverOut(
                factor=d.factor, detail=d.detail, weight=round(d.weight, 3),
            ))
    except Exception:
        pass  # graceful degradation if explainer fails

    # Graph insights
    graph_insights_parts: list[str] = []
    if state.analyzer:
        centrality = state.analyzer.compute_centrality()
        m = centrality.get(entity_id)
        if m:
            graph_insights_parts.append(
                f"Degree centrality: {m.degree_centrality:.4f}, "
                f"Betweenness centrality: {m.betweenness_centrality:.4f}, "
                f"PageRank: {m.pagerank:.4f}"
            )
        cycles = state.analyzer.detect_cycles()
        entity_cycles = [c for c in cycles if entity_id in c]
        if entity_cycles:
            graph_insights_parts.append(
                f"Participates in {len(entity_cycles)} transaction cycle(s)"
            )
    graph_insights = ". ".join(graph_insights_parts)

    # ── Build answer ─────────────────────────────────────────────
    answer_parts: list[str] = []
    answer_parts.append(
        f"Entity {entity_id} has a {risk_level} risk score ({risk_score:.2f}) "
        f"based on {total_txns} transaction(s) totaling ${total_value:,.2f}."
    )
    if fraud_txns:
        answer_parts.append(f"{fraud_txns} of those transactions are flagged as high-risk.")
    if aml_patterns:
        labels = ", ".join(p.replace("_", " ") for p in aml_patterns)
        answer_parts.append(f"Detected AML patterns: {labels}.")
    if connected:
        answer_parts.append(f"Connected to {len(connected)} entities in the financial network.")
    if drivers:
        top = drivers[0]
        answer_parts.append(f"Top risk driver: {top.factor} — {top.detail}")
    if graph_insights:
        answer_parts.append(graph_insights + ".")

    return InvestigationQueryResponse(
        entity_id=entity_id,
        question=question,
        answer=" ".join(answer_parts),
        risk_score=round(risk_score, 4),
        risk_level=risk_level,
        drivers=drivers,
        aml_patterns=aml_patterns,
        connected_entities=connected,
        graph_insights=graph_insights,
    )
