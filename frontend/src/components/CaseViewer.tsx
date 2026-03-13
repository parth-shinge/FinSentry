import { useEffect, useState } from "react";
import { getCase } from "../services/api";
import type { CaseDetailResponse } from "../types/apiTypes";

interface Props {
  caseId: string | null;
  caseList: { case_id: string; primary_entity: string; risk_score: number }[];
  onSelect: (caseId: string) => void;
  narratives?: string[];
  amlPatterns?: string[];
  riskExplanations?: string[];
}

function patternBadge(pattern: string) {
  const label = pattern
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  const p = pattern.toLowerCase();
  let cls = "bg-blue-100 text-blue-700";
  if (p.includes("circular") || p.includes("round")) cls = "bg-red-100 text-red-700";
  else if (p.includes("layering") || p.includes("cross")) cls = "bg-purple-100 text-purple-700";
  else if (p.includes("rapid")) cls = "bg-amber-100 text-amber-700";
  else if (p.includes("structuring")) cls = "bg-orange-100 text-orange-700";
  else if (p.includes("shell")) cls = "bg-rose-100 text-rose-700";
  return (
    <span
      key={pattern}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`}
    >
      {label}
    </span>
  );
}

export default function CaseViewer({
  caseId,
  caseList,
  onSelect,
  narratives = [],
  amlPatterns = [],
  riskExplanations = [],
}: Props) {
  const [caseDetail, setCaseDetail] = useState<CaseDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    getCase(caseId)
      .then(setCaseDetail)
      .catch(() => setCaseDetail(null))
      .finally(() => setLoading(false));
  }, [caseId]);

  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-6 py-4">
        <h3 className="text-base font-semibold text-gray-800">
          Investigation Cases
        </h3>
      </div>

      {caseList.length === 0 ? (
        <div className="px-6 py-8">
          <p className="text-sm text-gray-400 text-center">
            No cases generated yet.
          </p>
        </div>
      ) : (
        <div className="flex divide-x divide-gray-200">
          {/* Case list (left) */}
          <div className="w-64 flex-shrink-0 max-h-[520px] overflow-y-auto">
            {caseList.map((c) => (
              <button
                key={c.case_id}
                onClick={() => onSelect(c.case_id)}
                className={`w-full text-left px-4 py-3 border-b border-gray-100 transition-colors ${
                  caseId === c.case_id
                    ? "bg-blue-50"
                    : "hover:bg-gray-50"
                }`}
              >
                <p className="text-xs font-mono text-gray-500 truncate">
                  {c.case_id}
                </p>
                <p className="text-sm text-gray-700 mt-0.5">
                  {c.primary_entity}
                </p>
                <div className="flex items-center gap-1 mt-1">
                  <div className="h-1.5 w-12 rounded-full bg-gray-200 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        c.risk_score >= 0.7
                          ? "bg-red-500"
                          : c.risk_score >= 0.4
                          ? "bg-amber-500"
                          : "bg-emerald-500"
                      }`}
                      style={{ width: `${Math.round(c.risk_score * 100)}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-gray-400">
                    {(c.risk_score * 100).toFixed(0)}%
                  </span>
                </div>
              </button>
            ))}
          </div>

          {/* Case detail (right) */}
          <div className="flex-1 px-6 py-4 max-h-[520px] overflow-y-auto">
            {loading && (
              <p className="text-sm text-blue-600 animate-pulse">Loading case…</p>
            )}

            {!loading && !caseDetail && (
              <p className="text-sm text-gray-400">
                Select a case to view details.
              </p>
            )}

            {!loading && caseDetail && (
              <div className="space-y-4">
                {/* Header */}
                <div>
                  <p className="text-xs text-gray-400 font-mono">
                    {caseDetail.case_id}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <p className="text-lg font-semibold text-gray-800">
                      {caseDetail.primary_entity}
                    </p>
                    {/* Severity badge */}
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                      caseDetail.risk_score >= 0.8
                        ? "bg-red-600 text-white"
                        : caseDetail.risk_score >= 0.6
                        ? "bg-red-100 text-red-700"
                        : caseDetail.risk_score >= 0.4
                        ? "bg-amber-100 text-amber-700"
                        : "bg-green-100 text-green-700"
                    }`}>
                      {caseDetail.risk_score >= 0.8
                        ? "Critical"
                        : caseDetail.risk_score >= 0.6
                        ? "High"
                        : caseDetail.risk_score >= 0.4
                        ? "Medium"
                        : "Low"}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Created {new Date(caseDetail.created_at).toLocaleString()}
                  </p>
                </div>

                {/* Metrics */}
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                    <p className="text-xs text-gray-400">Risk Score</p>
                    <p className={`text-lg font-bold ${
                      caseDetail.risk_score >= 0.7
                        ? "text-red-600"
                        : caseDetail.risk_score >= 0.4
                        ? "text-amber-600"
                        : "text-gray-800"
                    }`}>
                      {(caseDetail.risk_score * 100).toFixed(0)}%
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                    <p className="text-xs text-gray-400">Transactions</p>
                    <p className="text-lg font-bold text-gray-800">
                      {caseDetail.transactions.length}
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                    <p className="text-xs text-gray-400">Entities</p>
                    <p className="text-lg font-bold text-gray-800">
                      {caseDetail.related_entities.length + 1}
                    </p>
                  </div>
                </div>

                {/* Pattern Detection Badges */}
                {amlPatterns.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">
                      Detected AML Patterns
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {amlPatterns.map((p) => patternBadge(p))}
                    </div>
                  </div>
                )}

                {/* Risk Explanation */}
                {riskExplanations.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">
                      Risk Explanation
                    </h4>
                    <div className="space-y-1.5">
                      {riskExplanations.map((driver, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs">
                          <span className="mt-0.5 inline-block h-2 w-2 rounded-full bg-amber-500 flex-shrink-0" />
                          <span className="text-gray-600">{driver}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Investigation Narrative */}
                {narratives.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">
                      Investigation Narrative
                    </h4>
                    <div className="rounded-lg bg-blue-50 border border-blue-100 p-4">
                      {narratives.map((text, i) => (
                        <p key={i} className="text-sm text-blue-900 leading-relaxed">
                          {text}
                        </p>
                      ))}
                    </div>
                  </div>
                )}

                {/* Risk indicators */}
                {caseDetail.risk_indicators.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">
                      Risk Indicators
                    </h4>
                    <div className="space-y-1.5">
                      {caseDetail.risk_indicators.map((ri, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-2 text-xs"
                        >
                          <span
                            className={`mt-0.5 inline-block h-2 w-2 rounded-full flex-shrink-0 ${
                              ri.severity === "high"
                                ? "bg-red-500"
                                : ri.severity === "medium"
                                ? "bg-amber-500"
                                : "bg-blue-500"
                            }`}
                          />
                          <span className="text-gray-600">
                            {ri.description}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Evidence */}
                {caseDetail.evidence.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">
                      Evidence
                    </h4>
                    <div className="space-y-2">
                      {caseDetail.evidence.map((ev, idx) => (
                        <div
                          key={idx}
                          className="rounded-lg bg-gray-50 border border-gray-100 p-3"
                        >
                          <p className="text-xs font-medium text-blue-600 uppercase">
                            {ev.evidence_type}
                          </p>
                          <p className="text-xs text-gray-600 mt-1">
                            {ev.description}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
