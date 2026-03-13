/* FinSentry — API Type Definitions */

// ─── Transaction ─────────────────────────────────────────────

export interface TransactionInput {
  transaction_id: string;
  account_id: string;
  sender_entity_id: string;
  receiver_entity_id: string;
  amount: number;
  currency: string;
  timestamp: string;
  origin_country: string;
  destination_country: string;
  merchant_category?: string;
  transaction_type?: string;
  channel?: string;
  is_international?: boolean;
}

// ─── Pipeline ────────────────────────────────────────────────

export interface PipelineRunRequest {
  transactions: TransactionInput[];
  fraud_threshold?: number;
  contamination?: number;
  n_estimators?: number;
  explain_top_n?: number;
}

export interface PipelineCaseOut {
  case_id: string;
  primary_entity: string;
  risk_score: number;
  transaction_count: number;
  evidence_count: number;
}

export interface PipelineSAROut {
  report_id: string;
  case_id: string;
  subject_entity: string;
  risk_score: number;
  is_valid: boolean;
}

export interface PipelineRunResponse {
  transactions_processed: number;
  high_risk_count: number;
  explanations_generated: number;
  entity_risk_scores: number;
  aml_patterns_detected: number;
  risk_explanations_generated: number;
  narratives_generated: number;
  cases_generated: number;
  sar_reports_generated: number;
  all_reports_valid: boolean;
  cases: PipelineCaseOut[];
  sar_reports: PipelineSAROut[];
}

// ─── Fraud Detection ─────────────────────────────────────────

export interface FraudScoreOut {
  transaction_id: string;
  fraud_probability: number;
  anomaly_score: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
}

export interface DetectionResultOut {
  transaction_id: string;
  features_used: string[];
  fraud_score: FraudScoreOut;
}

export interface DetectResponse {
  total_scored: number;
  high_risk_count: number;
  medium_risk_count: number;
  low_risk_count: number;
  results: DetectionResultOut[];
}

// ─── Case ────────────────────────────────────────────────────

export interface RiskIndicatorOut {
  indicator_type: string;
  severity: string;
  description: string;
}

export interface EvidenceOut {
  evidence_type: string;
  description: string;
  related_transactions: string[];
  related_entities: string[];
}

export interface CaseDetailResponse {
  case_id: string;
  primary_entity: string;
  related_entities: string[];
  transactions: string[];
  fraud_scores: Record<string, number>;
  graph_metrics: Record<string, number>;
  risk_indicators: RiskIndicatorOut[];
  evidence: EvidenceOut[];
  risk_score: number;
  created_at: string;
}

// ─── Timeline ────────────────────────────────────────────────

export interface TimelineEventOut {
  timestamp: string;
  event_type: string;
  description: string;
  transaction_id?: string;
  sender?: string;
  receiver?: string;
  amount: number;
  currency: string;
  origin_country: string;
  destination_country: string;
  fraud_score?: number;
  risk_level?: string;
}

export interface TimelineResponse {
  case_id: string;
  total_events: number;
  events: TimelineEventOut[];
}

// ─── SAR ─────────────────────────────────────────────────────

export interface SARReportOut {
  report_id: string;
  case_id: string;
  subject_entity: string;
  report_date: string;
  suspicious_activity_description: string;
  transaction_summary: string;
  evidence_summary: string;
  risk_assessment: string;
  recommended_action: string;
  entities_involved: string[];
  jurisdictions: string[];
  total_amount: number;
  risk_score: number;
}

export interface SARGenerateResponse {
  report: SARReportOut;
}

export interface ViolationOut {
  rule_name: string;
  severity: string;
  field?: string;
  message: string;
}

export interface SARValidateResponse {
  report_id: string;
  is_valid: boolean;
  error_count: number;
  warning_count: number;
  rules_checked: number;
  violations: ViolationOut[];
}

// ─── Graph ───────────────────────────────────────────────────

export interface NeighborOut {
  entity_id: string;
  direction: string;
  transaction_amount: number;
  fraud_score: number;
}

export interface GraphEntityResponse {
  entity_id: string;
  entity_type: string;
  degree_centrality: number;
  betweenness_centrality: number;
  pagerank: number;
  in_degree: number;
  out_degree: number;
  community_id: number;
  neighbors: NeighborOut[];
}

// ─── Health ──────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  service: string;
  modules_loaded: number;
  transactions_loaded: number;
  cases_generated: number;
  sar_reports_generated: number;
}

// ─── Entity Profile ─────────────────────────────────────────

export interface EntityProfileResponse {
  entity_id: string;
  jurisdiction: string;
  risk_score: number;
  connected_entities: string[];
  total_transaction_value: number;
  total_transactions: number;
  fraud_transactions: number;
  detected_patterns: string[];
  suspicious_activity_summary: string;
}

// ─── SAR List ────────────────────────────────────────────────

export interface SARListItem {
  report_id: string;
  case_id: string;
  subject_entity: string;
  report_date: string;
  risk_score: number;
}

export interface SARListResponse {
  total: number;
  reports: SARListItem[];
}

// ─── Investigation Copilot ──────────────────────────────────

export interface InvestigationQueryRequest {
  question: string;
}

export interface InvestigationDriverOut {
  factor: string;
  detail: string;
  weight: number;
}

export interface InvestigationQueryResponse {
  entity_id: string;
  question: string;
  answer: string;
  risk_score: number;
  risk_level: string;
  drivers: InvestigationDriverOut[];
  aml_patterns: string[];
  connected_entities: string[];
  graph_insights: string;
}
