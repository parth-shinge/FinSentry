import axios from "axios";
import type {
  PipelineRunRequest,
  PipelineRunResponse,
  CaseDetailResponse,
  TimelineResponse,
  SARGenerateResponse,
  SARValidateResponse,
  SARListResponse,
  SARReportOut,
  GraphEntityResponse,
  EntityProfileResponse,
  HealthResponse,
  DetectResponse,
  InvestigationQueryRequest,
  InvestigationQueryResponse,
} from "../types/apiTypes";

const api = axios.create({
  baseURL: "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

/* ── Health ─────────────────────────────────────────────── */

export const checkHealth = () =>
  api.get<HealthResponse>("/").then((r) => r.data);

/* ── Pipeline ───────────────────────────────────────────── */

export const runPipeline = (data: PipelineRunRequest) =>
  api.post<PipelineRunResponse>("/pipeline/run", data).then((r) => r.data);

/* ── Cases ──────────────────────────────────────────────── */

export const getCase = (caseId: string) =>
  api.get<CaseDetailResponse>(`/case/${caseId}`).then((r) => r.data);

/* ── Timeline ───────────────────────────────────────────── */

export const getTimeline = (caseId: string) =>
  api.get<TimelineResponse>(`/timeline/${caseId}`).then((r) => r.data);

/* ── SAR ────────────────────────────────────────────────── */

export const generateSAR = (caseId: string) =>
  api
    .post<SARGenerateResponse>("/sar/generate", { case_id: caseId })
    .then((r) => r.data);

export const validateSAR = (reportData: Record<string, unknown>) =>
  api
    .post<SARValidateResponse>("/sar/validate", reportData)
    .then((r) => r.data);

export const listSARReports = () =>
  api.get<SARListResponse>("/sar/list").then((r) => r.data);

export const getSARReport = (reportId: string) =>
  api.get<SARReportOut>(`/sar/${reportId}`).then((r) => r.data);

/* ── Graph ──────────────────────────────────────────────── */

export const getGraphEntity = (entityId: string) =>
  api
    .get<GraphEntityResponse>(`/graph/${entityId}`)
    .then((r) => r.data);

/* ── Detection (standalone) ─────────────────────────────── */

export const detectFraud = () =>
  api.post<DetectResponse>("/detect", {}).then((r) => r.data);

/* ── Entity Profile ─────────────────────────────────────── */

export const getEntityProfile = (entityId: string) =>
  api
    .get<EntityProfileResponse>(`/entity/${entityId}`)
    .then((r) => r.data);

/* ── Investigation Copilot ──────────────────────────────── */

export const queryInvestigation = (data: InvestigationQueryRequest) =>
  api
    .post<InvestigationQueryResponse>("/investigation/query", data)
    .then((r) => r.data);
