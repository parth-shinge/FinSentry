import { useEffect, useState } from "react";
import { getTimeline } from "../services/api";
import type { TimelineEventOut } from "../types/apiTypes";

interface Props {
  caseId: string | null;
}

const eventIcons: Record<string, string> = {
  deposit: "💰",
  transfer: "➡️",
  offshore_movement: "🌍",
  withdrawal: "🏧",
  flagged_transaction: "🚩",
};

const eventColors: Record<string, string> = {
  deposit: "border-emerald-400 bg-emerald-50",
  transfer: "border-blue-400 bg-blue-50",
  offshore_movement: "border-amber-400 bg-amber-50",
  withdrawal: "border-purple-400 bg-purple-50",
  flagged_transaction: "border-red-400 bg-red-50",
};

export default function TimelineView({ caseId }: Props) {
  const [events, setEvents] = useState<TimelineEventOut[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    getTimeline(caseId)
      .then((data) => setEvents(data.events))
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  }, [caseId]);

  if (!caseId) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h3 className="text-base font-semibold text-gray-800 mb-2">
          Investigation Timeline
        </h3>
        <p className="text-sm text-gray-400">
          Select a case to view the investigation timeline.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-6 py-4">
        <h3 className="text-base font-semibold text-gray-800">
          Investigation Timeline
          {events.length > 0 && (
            <span className="ml-2 text-sm font-normal text-gray-400">
              ({events.length} events)
            </span>
          )}
        </h3>
      </div>

      <div className="px-6 py-4 max-h-[500px] overflow-y-auto">
        {loading && (
          <p className="text-sm text-blue-600 animate-pulse">
            Loading timeline…
          </p>
        )}

        {!loading && events.length === 0 && (
          <p className="text-sm text-gray-400">No timeline events found.</p>
        )}

        {!loading && events.length > 0 && (
          <div className="relative ml-4">
            {/* Vertical line */}
            <div className="absolute left-0 top-2 bottom-2 w-px bg-gray-200" />

            <div className="space-y-4">
              {events.map((ev, idx) => (
                <div key={idx} className="relative pl-7">
                  {/* Dot */}
                  <div
                    className={`absolute left-[-5px] top-2 h-2.5 w-2.5 rounded-full border-2 ${
                      ev.event_type === "flagged_transaction"
                        ? "border-red-500 bg-red-100"
                        : ev.event_type === "offshore_movement"
                        ? "border-amber-500 bg-amber-100"
                        : "border-blue-500 bg-blue-100"
                    }`}
                  />

                  <div
                    className={`rounded-lg border-l-2 p-3 ${
                      eventColors[ev.event_type] ?? "border-gray-300 bg-gray-50"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm">
                          {eventIcons[ev.event_type] ?? "📋"}
                        </span>
                        <span className="text-xs font-medium uppercase text-gray-500">
                          {ev.event_type.replace(/_/g, " ")}
                        </span>
                      </div>
                      <span className="text-xs text-gray-400">
                        {new Date(ev.timestamp).toLocaleString()}
                      </span>
                    </div>

                    <p className="mt-1.5 text-sm text-gray-700">
                      {ev.description}
                    </p>

                    <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-gray-500">
                      {ev.amount > 0 && (
                        <span>
                          ${ev.amount.toLocaleString()} {ev.currency}
                        </span>
                      )}
                      {ev.fraud_score != null && ev.fraud_score > 0 && (
                        <span
                          className={`font-medium ${
                            ev.fraud_score >= 0.7
                              ? "text-red-600"
                              : ev.fraud_score >= 0.3
                              ? "text-amber-600"
                              : "text-gray-500"
                          }`}
                        >
                          Fraud: {(ev.fraud_score * 100).toFixed(1)}%
                        </span>
                      )}
                      {ev.risk_level && (
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                            ev.risk_level === "HIGH"
                              ? "bg-red-100 text-red-700"
                              : ev.risk_level === "MEDIUM"
                              ? "bg-amber-100 text-amber-700"
                              : "bg-emerald-100 text-emerald-700"
                          }`}
                        >
                          {ev.risk_level}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
