import UploadPanel from "../components/UploadPanel";
import CaseViewer from "../components/CaseViewer";
import TimelineView from "../components/TimelineView";
import { usePipeline } from "../hooks/usePipeline";
import type { TransactionInput } from "../types/apiTypes";

export default function Dashboard() {
  const {
    loading,
    error,
    result,
    execute,
    cases,
    selectedCaseId,
    setSelectedCaseId,
    hasResults,
  } = usePipeline();

  const handleUpload = (txns: TransactionInput[]) => {
    execute(txns);
  };

  return (
    <div className="space-y-6 p-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Dashboard</h2>
        <p className="text-sm text-gray-500 mt-1">
          Upload transactions and run the FinSentry investigation pipeline.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <span className="font-medium">Error:</span> {error}
        </div>
      )}

      {/* Loading overlay */}
      {loading && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700 flex items-center gap-3">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Running investigation pipeline… This may take a few seconds.
        </div>
      )}

      {/* Stats summary */}
      {result && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            {
              label: "Transactions",
              value: result.transactions_processed,
              color: "text-blue-600",
            },
            {
              label: "High Risk",
              value: result.high_risk_count,
              color: "text-red-600",
            },
            {
              label: "Cases",
              value: result.cases_generated,
              color: "text-amber-600",
            },
            {
              label: "SAR Reports",
              value: result.sar_reports_generated,
              color: "text-emerald-600",
            },
          ].map((s) => (
            <div
              key={s.label}
              className="rounded-xl border border-gray-200 bg-white p-5"
            >
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                {s.label}
              </p>
              <p className={`mt-2 text-3xl font-bold ${s.color}`}>
                {s.value}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Upload panel */}
      <UploadPanel onUpload={handleUpload} loading={loading} />

      {/* Case viewer + Timeline */}
      {hasResults && cases.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <CaseViewer
            caseId={selectedCaseId}
            caseList={cases.map((c) => ({
              case_id: c.case_id,
              primary_entity: c.primary_entity,
              risk_score: c.risk_score,
            }))}
            onSelect={setSelectedCaseId}
          />
          <TimelineView caseId={selectedCaseId} />
        </div>
      )}

      {/* Empty state */}
      {!hasResults && !loading && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center">
          <p className="text-lg font-semibold text-gray-400">
            No investigation data
          </p>
          <p className="text-sm text-gray-400 mt-1">
            Upload a CSV file above to run the FinSentry pipeline.
          </p>
        </div>
      )}
    </div>
  );
}
