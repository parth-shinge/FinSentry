import { useState } from "react";
import GraphView from "../components/GraphView";
import CaseViewer from "../components/CaseViewer";
import TimelineView from "../components/TimelineView";
import EntityProfilePanel from "../components/EntityProfilePanel";
import InvestigationCopilot from "../components/InvestigationCopilot";
import { usePipeline } from "../hooks/usePipeline";

export default function Investigations() {
  const {
    cases,
    entityIds,
    selectedCaseId,
    setSelectedCaseId,
    hasResults,
    result,
  } = usePipeline();

  const [profileEntityId, setProfileEntityId] = useState<string | null>(null);

  return (
    <div className="space-y-6 p-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Investigations</h2>
        <p className="text-sm text-gray-500 mt-1">
          Explore the transaction network graph and investigate cases.
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

      {/* Graph + Entity Profile Panel */}
      {hasResults && (
        <div className={`grid gap-6 ${profileEntityId ? "grid-cols-1 lg:grid-cols-3" : "grid-cols-1"}`}>
          <div className={profileEntityId ? "lg:col-span-2" : ""}>
            <GraphView
              entityIds={entityIds}
              onEntitySelect={setProfileEntityId}
            />
          </div>
          {profileEntityId && (
            <div>
              <EntityProfilePanel
                entityId={profileEntityId}
                onClose={() => setProfileEntityId(null)}
              />
            </div>
          )}
        </div>
      )}

      {/* Pipeline intelligence summary */}
      {hasResults && result && (
        <div className="grid grid-cols-3 gap-4">
          {(result.aml_patterns_detected ?? 0) > 0 && (
            <div className="rounded-lg bg-red-50 border border-red-100 px-4 py-3">
              <p className="text-xs text-red-500 font-medium uppercase tracking-wider">AML Patterns</p>
              <p className="text-2xl font-bold text-red-700">{result.aml_patterns_detected}</p>
            </div>
          )}
          {(result.risk_explanations_generated ?? 0) > 0 && (
            <div className="rounded-lg bg-amber-50 border border-amber-100 px-4 py-3">
              <p className="text-xs text-amber-500 font-medium uppercase tracking-wider">Risk Explanations</p>
              <p className="text-2xl font-bold text-amber-700">{result.risk_explanations_generated}</p>
            </div>
          )}
          {(result.narratives_generated ?? 0) > 0 && (
            <div className="rounded-lg bg-blue-50 border border-blue-100 px-4 py-3">
              <p className="text-xs text-blue-500 font-medium uppercase tracking-wider">Narratives</p>
              <p className="text-2xl font-bold text-blue-700">{result.narratives_generated}</p>
            </div>
          )}
        </div>
      )}

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

      {/* Investigation Copilot */}
      {hasResults && <InvestigationCopilot />}
    </div>
  );
}
