import { useState } from "react";
import SARViewer from "../components/SARViewer";
import { usePipeline } from "../hooks/usePipeline";

export default function Reports() {
  const { sarReports, hasResults } = usePipeline();
  const [selectedCase, setSelectedCase] = useState<string | null>(
    sarReports.length > 0 ? sarReports[0].case_id : null
  );

  return (
    <div className="space-y-6 p-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold text-gray-800">SAR Reports</h2>
        <p className="text-sm text-gray-500 mt-1">
          Generate and review Suspicious Activity Reports.
        </p>
      </div>

      {/* Empty state */}
      {!hasResults && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center">
          <p className="text-lg font-semibold text-gray-400">
            Run Investigation First
          </p>
          <p className="text-sm text-gray-400 mt-1">
            Go to the Dashboard and upload transactions to run the pipeline.
          </p>
        </div>
      )}

      {/* SAR report list + viewer */}
      {sarReports.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* SAR list */}
          <div className="rounded-xl border border-gray-200 bg-white">
            <div className="border-b border-gray-200 px-6 py-4">
              <h3 className="text-base font-semibold text-gray-800">
                Generated Reports ({sarReports.length})
              </h3>
            </div>
            <div className="max-h-[500px] overflow-y-auto">
              {sarReports.map((sar) => (
                <button
                  key={sar.report_id}
                  onClick={() => setSelectedCase(sar.case_id)}
                  className={`w-full text-left px-5 py-3 border-b border-gray-100 transition-colors ${
                    selectedCase === sar.case_id
                      ? "bg-blue-50"
                      : "hover:bg-gray-50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-700">
                        {sar.subject_entity}
                      </p>
                      <p className="text-xs text-gray-400 font-mono mt-0.5">
                        {sar.report_id}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                          sar.is_valid
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {sar.is_valid ? "Valid" : "Invalid"}
                      </span>
                      <span className="text-xs text-gray-500">
                        Risk: {(sar.risk_score * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* SAR viewer */}
          <div className="lg:col-span-2">
            <SARViewer caseId={selectedCase} />
          </div>
        </div>
      )}

      {hasResults && sarReports.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-center">
          <p className="text-sm text-gray-400">
            No SAR reports were generated. The investigation did not produce
            any cases with sufficient risk to report.
          </p>
        </div>
      )}
    </div>
  );
}
