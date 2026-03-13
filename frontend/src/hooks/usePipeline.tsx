import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { runPipeline } from "../services/api";
import type {
  TransactionInput,
  PipelineRunResponse,
  PipelineCaseOut,
  PipelineSAROut,
} from "../types/apiTypes";

/* ── Context shape ──────────────────────────────────────── */

interface PipelineState {
  loading: boolean;
  error: string | null;
  result: PipelineRunResponse | null;
  selectedCaseId: string | null;
  setSelectedCaseId: (id: string | null) => void;
  execute: (
    txns: TransactionInput[],
    opts?: { fraud_threshold?: number; explain_top_n?: number }
  ) => Promise<PipelineRunResponse | null>;
  reset: () => void;

  /* Convenience getters */
  cases: PipelineCaseOut[];
  sarReports: PipelineSAROut[];
  entityIds: string[];
  hasResults: boolean;
}

const PipelineContext = createContext<PipelineState | null>(null);

/* ── Provider ───────────────────────────────────────────── */

export function PipelineProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PipelineRunResponse | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  const execute = useCallback(
    async (
      transactions: TransactionInput[],
      opts?: {
        fraud_threshold?: number;
        explain_top_n?: number;
      }
    ) => {
      setLoading(true);
      setError(null);
      try {
        const res = await runPipeline({
          transactions,
          fraud_threshold: opts?.fraud_threshold ?? 0.3,
          explain_top_n: opts?.explain_top_n ?? 0,
        });
        setResult(res);
        if (res.cases && res.cases.length > 0) {
          setSelectedCaseId(res.cases[0].case_id);
        }
        return res;
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Pipeline execution failed";
        setError(msg);
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
    setSelectedCaseId(null);
  }, []);

  const cases = result?.cases ?? [];
  const sarReports = result?.sar_reports ?? [];

  // Extract entity IDs from cases; fall back to SAR report subjects
  const entityIds = (() => {
    const fromCases = cases.map((c) => c.primary_entity);
    const fromSARs = sarReports.map((s) => s.subject_entity);
    const merged = [...new Set([...fromCases, ...fromSARs])];
    return merged.filter(Boolean);
  })();

  return (
    <PipelineContext.Provider
      value={{
        loading,
        error,
        result,
        selectedCaseId,
        setSelectedCaseId,
        execute,
        reset,
        cases,
        sarReports,
        entityIds,
        hasResults: result !== null,
      }}
    >
      {children}
    </PipelineContext.Provider>
  );
}

/* ── Hook ───────────────────────────────────────────────── */

export function usePipeline(): PipelineState {
  const ctx = useContext(PipelineContext);
  if (!ctx) {
    throw new Error("usePipeline must be used inside <PipelineProvider>");
  }
  return ctx;
}
