import { useState } from "react";
import { queryInvestigation } from "../services/api";
import type { InvestigationQueryResponse } from "../types/apiTypes";

function riskColor(level: string) {
  if (level === "high") return "text-red-600";
  if (level === "medium") return "text-amber-600";
  return "text-blue-600";
}

function riskBg(level: string) {
  if (level === "high") return "bg-red-500";
  if (level === "medium") return "bg-amber-500";
  return "bg-blue-500";
}

const EXAMPLE_QUESTIONS = [
  "Why is Entity E17 suspicious?",
  "What AML patterns involve E001?",
  "Tell me about Entity E12",
];

export default function InvestigationCopilot() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<InvestigationQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (q?: string) => {
    const text = (q ?? question).trim();
    if (!text) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await queryInvestigation({ question: text });
      setResult(res);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? String(
              (err as { response?: { data?: { detail?: string } } }).response
                ?.data?.detail ?? "Request failed"
            )
          : "Request failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      {/* Header */}
      <div className="border-b border-gray-200 px-6 py-4">
        <h3 className="text-base font-semibold text-gray-800 flex items-center gap-2">
          <span className="text-lg">🔎</span>
          Investigation Copilot
        </h3>
        <p className="text-xs text-gray-400 mt-1">
          Ask questions about entities, risk scores, AML patterns, and graph relationships.
        </p>
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-b border-gray-100">
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder="Why is Entity E17 suspicious?"
            className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
          />
          <button
            onClick={() => handleSubmit()}
            disabled={loading || !question.trim()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Analyzing…" : "Ask"}
          </button>
        </div>

        {/* Example questions */}
        <div className="flex flex-wrap gap-1.5 mt-3">
          {EXAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => {
                setQuestion(q);
                handleSubmit(q);
              }}
              className="text-[11px] rounded-full border border-gray-200 px-2.5 py-1 text-gray-500 hover:bg-gray-50 hover:text-gray-700 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="px-6 py-4">
          <p className="text-sm text-red-500">{error}</p>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="px-6 py-4 space-y-4 animate-[fade-in-up_0.3s_ease-out]">
          {/* Answer */}
          <div className="rounded-lg bg-blue-50 border border-blue-100 p-4">
            <p className="text-sm text-blue-900 leading-relaxed">{result.answer}</p>
          </div>

          {/* Entity header */}
          {result.entity_id && (
            <div className="flex items-center gap-3">
              <div className={`h-3 w-3 rounded-full ${riskBg(result.risk_level)}`} />
              <span className="text-sm font-semibold text-gray-800">
                {result.entity_id}
              </span>
              <span className={`text-sm font-bold ${riskColor(result.risk_level)}`}>
                Risk: {(result.risk_score * 100).toFixed(0)}%
              </span>
              <span className={`text-[10px] uppercase font-bold tracking-wide rounded-full px-2 py-0.5 ${
                result.risk_level === "high"
                  ? "bg-red-100 text-red-700"
                  : result.risk_level === "medium"
                  ? "bg-amber-100 text-amber-700"
                  : "bg-blue-100 text-blue-700"
              }`}>
                {result.risk_level}
              </span>
            </div>
          )}

          {/* Risk drivers */}
          {result.drivers.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">Risk Drivers</h4>
              <div className="space-y-1.5">
                {result.drivers.map((d, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span className="mt-0.5 inline-block h-2 w-2 rounded-full bg-amber-500 flex-shrink-0" />
                    <span className="text-gray-600">
                      <span className="font-medium text-gray-700">{d.factor}</span>
                      {d.detail && ` — ${d.detail}`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AML Patterns */}
          {result.aml_patterns.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">AML Patterns</h4>
              <div className="flex flex-wrap gap-1.5">
                {result.aml_patterns.map((p) => (
                  <span
                    key={p}
                    className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold bg-red-100 text-red-700"
                  >
                    {p.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Connected entities */}
          {result.connected_entities.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                Connected Entities ({result.connected_entities.length})
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {result.connected_entities.slice(0, 10).map((e) => (
                  <span
                    key={e}
                    className="inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-mono text-gray-600"
                  >
                    {e}
                  </span>
                ))}
                {result.connected_entities.length > 10 && (
                  <span className="text-xs text-gray-400 py-1">
                    +{result.connected_entities.length - 10} more
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Graph insights */}
          {result.graph_insights && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">Graph Intelligence</h4>
              <p className="text-xs text-gray-600 bg-gray-50 rounded-lg p-3 border border-gray-100">
                {result.graph_insights}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!result && !error && !loading && (
        <div className="px-6 py-8 text-center">
          <p className="text-sm text-gray-400">
            Ask a question about any entity to get AI-powered investigation insights.
          </p>
        </div>
      )}
    </div>
  );
}
