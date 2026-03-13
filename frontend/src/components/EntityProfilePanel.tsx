import { useEffect, useState } from "react";
import { getEntityProfile } from "../services/api";
import type { EntityProfileResponse } from "../types/apiTypes";

interface Props {
  entityId: string | null;
  onClose: () => void;
}

function riskColor(score: number) {
  if (score >= 0.7) return "text-red-600";
  if (score >= 0.4) return "text-amber-600";
  return "text-blue-600";
}

function riskBg(score: number) {
  if (score >= 0.7) return "bg-red-500";
  if (score >= 0.4) return "bg-amber-500";
  return "bg-blue-500";
}

function patternLabel(pattern: string) {
  return pattern
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function patternBadgeColor(pattern: string) {
  const p = pattern.toLowerCase();
  if (p.includes("circular") || p.includes("round")) return "bg-red-100 text-red-700";
  if (p.includes("cross_border") || p.includes("layering")) return "bg-purple-100 text-purple-700";
  if (p.includes("rapid") || p.includes("succession")) return "bg-amber-100 text-amber-700";
  if (p.includes("structuring") || p.includes("high_value")) return "bg-orange-100 text-orange-700";
  if (p.includes("fraud") || p.includes("critical")) return "bg-red-100 text-red-700";
  return "bg-blue-100 text-blue-700";
}

export default function EntityProfilePanel({ entityId, onClose }: Props) {
  const [profile, setProfile] = useState<EntityProfileResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!entityId) {
      setProfile(null);
      return;
    }
    setLoading(true);
    setError(null);
    getEntityProfile(entityId)
      .then(setProfile)
      .catch(() => setError("Failed to load entity profile"))
      .finally(() => setLoading(false));
  }, [entityId]);

  if (!entityId) return null;

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-lg">
      {/* Header */}
      <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`h-3 w-3 rounded-full ${profile ? riskBg(profile.risk_score) : "bg-gray-300"}`} />
          <h3 className="text-base font-semibold text-gray-800">
            Entity Profile
          </h3>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 text-sm"
        >
          ✕
        </button>
      </div>

      {loading && (
        <div className="px-6 py-8 text-center">
          <p className="text-sm text-blue-600 animate-pulse">Loading profile…</p>
        </div>
      )}

      {error && (
        <div className="px-6 py-8 text-center">
          <p className="text-sm text-red-500">{error}</p>
        </div>
      )}

      {!loading && profile && (
        <div className="px-6 py-4 space-y-4">
          {/* Entity ID & Jurisdiction */}
          <div>
            <p className="text-lg font-bold text-gray-800">{profile.entity_id}</p>
            {profile.jurisdiction && (
              <p className="text-sm text-gray-500 mt-0.5">
                Jurisdiction: <span className="font-medium">{profile.jurisdiction}</span>
              </p>
            )}
          </div>

          {/* Risk Score */}
          <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                Risk Score
              </p>
              <p className={`text-2xl font-bold ${riskColor(profile.risk_score)}`}>
                {(profile.risk_score * 100).toFixed(0)}%
              </p>
            </div>
            <div className="h-2 w-full rounded-full bg-gray-200 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${riskBg(profile.risk_score)}`}
                style={{ width: `${Math.round(profile.risk_score * 100)}%` }}
              />
            </div>
          </div>

          {/* Transaction Stats */}
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-gray-50 rounded-lg p-3 border border-gray-100 text-center">
              <p className="text-xs text-gray-400">Transactions</p>
              <p className="text-lg font-bold text-gray-800">{profile.total_transactions}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 border border-gray-100 text-center">
              <p className="text-xs text-gray-400">Total Value</p>
              <p className="text-lg font-bold text-gray-800">
                ${profile.total_transaction_value >= 1000
                  ? `${(profile.total_transaction_value / 1000).toFixed(0)}K`
                  : profile.total_transaction_value.toFixed(0)}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 border border-gray-100 text-center">
              <p className="text-xs text-gray-400">Fraud Txns</p>
              <p className="text-lg font-bold text-red-600">{profile.fraud_transactions}</p>
            </div>
          </div>

          {/* Connected Entities */}
          {profile.connected_entities.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                Connected Entities ({profile.connected_entities.length})
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {profile.connected_entities.slice(0, 12).map((eid) => (
                  <span
                    key={eid}
                    className="inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-mono text-gray-600"
                  >
                    {eid}
                  </span>
                ))}
                {profile.connected_entities.length > 12 && (
                  <span className="text-xs text-gray-400 px-2 py-1">
                    +{profile.connected_entities.length - 12} more
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Detected AML Patterns */}
          {profile.detected_patterns.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                Detected Patterns
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {profile.detected_patterns.map((p, i) => (
                  <span
                    key={i}
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${patternBadgeColor(p)}`}
                  >
                    {patternLabel(p)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Suspicious Activity Summary */}
          {profile.suspicious_activity_summary && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                Suspicious Activity Summary
              </h4>
              <div className="rounded-lg bg-amber-50 border border-amber-100 p-3">
                <p className="text-sm text-amber-900 leading-relaxed">
                  {profile.suspicious_activity_summary}
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
