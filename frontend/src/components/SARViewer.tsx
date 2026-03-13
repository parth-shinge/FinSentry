import { useEffect, useState } from "react";
import { generateSAR, validateSAR, listSARReports, getSARReport } from "../services/api";
import type {
  SARReportOut,
  SARValidateResponse,
  SARListItem,
} from "../types/apiTypes";

interface Props {
  caseId: string | null;
}

export default function SARViewer({ caseId }: Props) {
  const [report, setReport] = useState<SARReportOut | null>(null);
  const [validation, setValidation] = useState<SARValidateResponse | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedReports, setSavedReports] = useState<SARListItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  // Fetch saved reports on mount
  useEffect(() => {
    listSARReports()
      .then((res) => setSavedReports(res?.reports ?? []))
      .catch(() => {});
  }, [report]);

  const generate = async () => {
    if (!caseId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await generateSAR(caseId);
      setReport(resp.report);

      // Auto-validate
      const valResp = await validateSAR({
        report_id: resp.report.report_id,
        case_id: resp.report.case_id,
        subject_entity: resp.report.subject_entity,
        suspicious_activity_description:
          resp.report.suspicious_activity_description,
        transaction_summary: resp.report.transaction_summary,
        evidence_summary: resp.report.evidence_summary,
        risk_assessment: resp.report.risk_assessment,
        recommended_action: resp.report.recommended_action,
        entities_involved: resp.report.entities_involved,
        jurisdictions: resp.report.jurisdictions,
        total_amount: resp.report.total_amount,
        risk_score: resp.report.risk_score,
      });
      setValidation(valResp);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to generate SAR");
    } finally {
      setLoading(false);
    }
  };

  const loadSaved = async (reportId: string) => {
    setLoading(true);
    setError(null);
    try {
      const r = await getSARReport(reportId);
      setReport(r);
      setValidation(null);
      setShowHistory(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load report");
    } finally {
      setLoading(false);
    }
  };

  // Reset when case changes
  useEffect(() => {
    setReport(null);
    setValidation(null);
    setError(null);
  }, [caseId]);

  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <h3 className="text-base font-semibold text-gray-800">
          SAR Report
        </h3>
        <div className="flex items-center gap-2">
          {savedReports.length > 0 && (
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-100"
            >
              {showHistory ? "Hide History" : `History (${savedReports.length})`}
            </button>
          )}
          {caseId && !report && (
            <button
              onClick={generate}
              disabled={loading}
              className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? "Generating…" : "Generate SAR"}
            </button>
          )}
        </div>
      </div>

      {/* Previous reports panel */}
      {showHistory && savedReports.length > 0 && (
        <div className="border-b border-gray-200 px-6 py-3 bg-gray-50 max-h-40 overflow-y-auto">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Previous Reports</p>
          <div className="space-y-1">
            {savedReports.map((sr) => (
              <button
                key={sr.report_id}
                onClick={() => loadSaved(sr.report_id)}
                className="w-full text-left rounded-lg px-3 py-2 text-xs hover:bg-white border border-transparent hover:border-gray-200 transition flex items-center justify-between"
              >
                <div>
                  <span className="font-medium text-gray-700">{sr.subject_entity}</span>
                  <span className="text-gray-400 ml-2 font-mono">{sr.report_id}</span>
                </div>
                <span className="text-gray-500">Risk: {(sr.risk_score * 100).toFixed(0)}%</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="px-6 py-4 max-h-[600px] overflow-y-auto">
        {!caseId && (
          <p className="text-sm text-gray-400">
            Select a case to generate a SAR report.
          </p>
        )}

        {error && (
          <p className="text-sm text-red-600">{error}</p>
        )}

        {report && (
          <div className="space-y-5">
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-mono text-gray-400">
                  {report.report_id}
                </p>
                <p className="text-base font-semibold text-gray-800 mt-1">
                  Subject: {report.subject_entity}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">
                  Report Date:{" "}
                  {new Date(report.report_date).toLocaleDateString()}
                </p>
              </div>

              {/* Validation badge */}
              {validation && (
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${
                    validation.is_valid
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-red-100 text-red-700"
                  }`}
                >
                  {validation.is_valid ? "✓ Valid" : "✗ Invalid"}
                </span>
              )}
            </div>

            {/* Metrics row */}
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-gray-50 border border-gray-100 p-3">
                <p className="text-xs text-gray-400">Total Amount</p>
                <p className="text-lg font-bold text-gray-800">
                  ${report.total_amount.toLocaleString()}
                </p>
              </div>
              <div className="rounded-lg bg-gray-50 border border-gray-100 p-3">
                <p className="text-xs text-gray-400">Risk Score</p>
                <p className="text-lg font-bold text-gray-800">
                  {(report.risk_score * 100).toFixed(0)}%
                </p>
              </div>
              <div className="rounded-lg bg-gray-50 border border-gray-100 p-3">
                <p className="text-xs text-gray-400">Jurisdictions</p>
                <p className="text-sm font-semibold text-gray-800">
                  {report.jurisdictions.join(", ") || "—"}
                </p>
              </div>
            </div>

            {/* Narrative sections */}
            {[
              {
                title: "Suspicious Activity",
                text: report.suspicious_activity_description,
              },
              { title: "Transaction Summary", text: report.transaction_summary },
              { title: "Evidence Summary", text: report.evidence_summary },
              { title: "Risk Assessment", text: report.risk_assessment },
              { title: "Recommended Action", text: report.recommended_action },
            ].map(
              (section) =>
                section.text && (
                  <div key={section.title}>
                    <h4 className="text-sm font-semibold text-gray-700 mb-1">
                      {section.title}
                    </h4>
                    <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap bg-gray-50 rounded-lg p-3 border border-gray-100">
                      {section.text}
                    </p>
                  </div>
                )
            )}

            {/* Validation details */}
            {validation && validation.violations.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2">
                  Validation Issues ({validation.violations.length})
                </h4>
                <div className="space-y-1.5">
                  {validation.violations.map((v, idx) => (
                    <div
                      key={idx}
                      className={`rounded-lg p-2.5 text-xs flex items-start gap-2 ${
                        v.severity === "ERROR"
                          ? "bg-red-50 text-red-700 border border-red-200"
                          : "bg-amber-50 text-amber-700 border border-amber-200"
                      }`}
                    >
                      <span className="font-semibold flex-shrink-0">
                        {v.severity}
                      </span>
                      <span>{v.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
