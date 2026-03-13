"""
FinSentry - Investigation Orchestrator
============================================

High-level orchestrator that runs the entire FinSentry investigation
pipeline end-to-end — from raw transactions through to validated SAR
reports.

Pipeline Stages
---------------
1. **Fraud Detection** — Train and score transactions.
2. **Explainability** — Generate SHAP explanations for high-risk transactions.
3. **Graph Building** — Construct the transaction network.
4. **Graph Analysis** — Centrality, communities, cycles, entity risk scores.
5. **Case Building** — Aggregate suspicious activity into investigation cases.
6. **SAR Generation** — Generate Suspicious Activity Reports for each case.
7. **Compliance Validation** — Validate SARs against regulatory rules.

Usage::

    from agents.orchestrator import InvestigationOrchestrator

    orchestrator = InvestigationOrchestrator()
    result = orchestrator.run_full_investigation(transactions)
"""

from __future__ import annotations

from typing import Optional, Sequence

from agents.models import InvestigationResult
from aml_patterns.detector import AMLPatternDetector
from case_builder.builder import CaseBuilder
from compliance_validator.validator import ComplianceValidator
from explainability.explainer import FraudExplainer
from explainability.risk_explainer import RiskExplainer
from fraud_detection.detector import FraudDetector
from fraud_detection.models import DetectionResult
from graph_engine.analyzer import GraphAnalyzer
from graph_engine.builder import GraphBuilder
from ingestion.schema import NormalizedTransaction
from investigation_narrative.generator import NarrativeGenerator
from sar_generator.generator import SARGenerator
from utils.logging import get_logger

logger = get_logger("agents.orchestrator")


class InvestigationOrchestrator:
    """Orchestrates the complete FinSentry investigation pipeline.

    Coordinates all pipeline stages and returns a unified
    :class:`InvestigationResult` containing outputs from every stage.

    Pipeline Stages
    ---------------
    1. Fraud Detection
    2. Explainability
    3. Graph Building
    4. Graph Analysis
    5. AML Pattern Detection
    6. Risk Explanation
    7. Case Building
    8. Investigation Narratives
    9. SAR Generation
    10. Compliance Validation

    Args:
        fraud_threshold:  Minimum fraud probability for case inclusion.
        contamination:    IsolationForest contamination parameter.
        n_estimators:     Number of trees for the detector.
        explain_top_n:    Max number of high-risk transactions to explain
                          (0 = skip explainability).
    """

    def __init__(
        self,
        fraud_threshold: float = 0.5,
        contamination: float = 0.15,
        n_estimators: int = 100,
        explain_top_n: int = 20,
    ) -> None:
        self.fraud_threshold = fraud_threshold
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.explain_top_n = explain_top_n

    def run_full_investigation(
        self,
        transactions: Sequence[NormalizedTransaction],
    ) -> InvestigationResult:
        """Run the complete investigation pipeline.

        Args:
            transactions: Normalised transactions to investigate.

        Returns:
            An :class:`InvestigationResult` with all pipeline outputs.

        Raises:
            ValueError: If fewer than 5 transactions are provided.
        """
        txn_list = list(transactions)
        if len(txn_list) < 5:
            raise ValueError(
                f"Need at least 5 transactions, got {len(txn_list)}."
            )

        result = InvestigationResult(transactions_processed=len(txn_list))

        # ── Stage 1: Fraud Detection ──────────────────────────────────
        logger.info("Stage 1/10: Fraud Detection (%d transactions)", len(txn_list))
        detector = FraudDetector(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=42,
        )
        detector.train(txn_list)
        fraud_results = detector.predict(txn_list)
        result.fraud_results = fraud_results

        fraud_score_map = {
            r.transaction_id: r.fraud_score.fraud_probability
            for r in fraud_results
        }
        logger.info(
            "Detection complete: %d HIGH, %d MEDIUM, %d LOW",
            result.high_risk_count,
            sum(1 for r in fraud_results if r.fraud_score.risk_level.value == "MEDIUM"),
            sum(1 for r in fraud_results if r.fraud_score.risk_level.value == "LOW"),
        )

        # ── Stage 2: Explainability ───────────────────────────────────
        if self.explain_top_n > 0:
            logger.info("Stage 2/10: Explainability (top %d)", self.explain_top_n)
            try:
                explainer = FraudExplainer(detector)
                # Explain top N highest fraud-probability transactions
                sorted_results = sorted(
                    fraud_results,
                    key=lambda r: r.fraud_score.fraud_probability,
                    reverse=True,
                )
                txn_map = {t.transaction_id: t for t in txn_list}
                for det_result in sorted_results[: self.explain_top_n]:
                    txn = txn_map.get(det_result.transaction_id)
                    if txn is not None:
                        explanation = explainer.explain_transaction(txn, txn_list)
                        result.explanations.append(explanation)
                logger.info("Generated %d explanations", len(result.explanations))
            except Exception as exc:
                logger.warning("Explainability skipped: %s", exc)
        else:
            logger.info("Stage 2/10: Explainability (skipped)")

        # ── Stage 3: Graph Building ───────────────────────────────────
        logger.info("Stage 3/10: Graph Building")
        builder = GraphBuilder(load_metadata=True)
        graph = builder.build_transaction_graph(txn_list, fraud_score_map)

        # ── Stage 4: Graph Analysis ───────────────────────────────────
        logger.info("Stage 4/10: Graph Analysis")
        analyzer = GraphAnalyzer(graph)
        analyzer.compute_centrality()
        analyzer.detect_communities()
        analyzer.detect_cycles()
        entity_risk_scores = analyzer.compute_entity_risk_scores()
        result.graph_metrics = entity_risk_scores

        # ── Stage 5: AML Pattern Detection ────────────────────────────
        logger.info("Stage 5/10: AML Pattern Detection")
        aml_detector = AMLPatternDetector()
        aml_patterns = aml_detector.detect_all(
            txn_list, fraud_results, graph, entity_risk_scores
        )
        result.aml_patterns = aml_patterns
        logger.info("Detected %d AML patterns", len(aml_patterns))

        # ── Stage 6: Risk Explanation ─────────────────────────────────
        logger.info("Stage 6/10: Risk Explanation")
        risk_explainer = RiskExplainer()
        risk_explanations = risk_explainer.explain_multiple(
            entity_risk_scores, txn_list, graph
        )
        result.risk_explanations = risk_explanations
        logger.info("Generated %d risk explanations", len(risk_explanations))

        # ── Stage 7: Case Building ────────────────────────────────────
        logger.info("Stage 7/10: Case Building (threshold=%.2f)", self.fraud_threshold)
        case_builder = CaseBuilder(fraud_threshold=self.fraud_threshold)
        cases = case_builder.build_cases(
            transactions=txn_list,
            fraud_results=fraud_results,
            entity_risk_scores=entity_risk_scores,
            graph=graph,
        )
        result.cases = cases
        logger.info("Generated %d investigation cases", len(cases))

        # ── Stage 8: Investigation Narratives ─────────────────────────
        logger.info("Stage 8/10: Investigation Narratives")
        if cases:
            narrator = NarrativeGenerator()
            narratives = narrator.generate_multiple(
                cases, txn_list, aml_patterns
            )
            result.narratives = narratives
            logger.info("Generated %d investigation narratives", len(narratives))
        else:
            logger.info("No cases — skipping narrative generation")

        # ── Stage 9: SAR Generation ───────────────────────────────────
        logger.info("Stage 9/10: SAR Generation")
        if cases:
            sar_gen = SARGenerator(graph, analyzer)
            reports = sar_gen.generate_multiple(cases, txn_list, fraud_results)
            result.sar_reports = reports
            logger.info("Generated %d SAR reports", len(reports))
        else:
            logger.info("No cases — skipping SAR generation")

        # ── Stage 10: Compliance Validation ───────────────────────────
        logger.info("Stage 10/10: Compliance Validation")
        if result.sar_reports:
            validator = ComplianceValidator()
            validations = validator.validate_batch(result.sar_reports)
            result.validation_results = validations
            valid_count = sum(1 for v in validations if v.is_valid)
            logger.info(
                "Validation complete: %d/%d reports valid",
                valid_count,
                len(validations),
            )
        else:
            logger.info("No SAR reports — skipping validation")

        logger.info(
            "Investigation complete: %d txns → %d patterns → %d cases → %d SARs",
            result.transactions_processed,
            len(result.aml_patterns),
            result.total_cases,
            len(result.sar_reports),
        )
        return result
