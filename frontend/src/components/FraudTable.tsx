import type { DetectionResultOut } from "../types/apiTypes";

interface Props {
  results: DetectionResultOut[];
}

const riskColor: Record<string, string> = {
  HIGH: "bg-red-100 text-red-700",
  MEDIUM: "bg-amber-100 text-amber-700",
  LOW: "bg-emerald-100 text-emerald-700",
};

export default function FraudTable({ results }: Props) {
  if (results.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h3 className="text-base font-semibold text-gray-800 mb-2">
          Fraud Detection Results
        </h3>
        <p className="text-sm text-gray-400">No results yet. Upload transactions and run the pipeline.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-6 py-4">
        <h3 className="text-base font-semibold text-gray-800">
          Fraud Detection Results
          <span className="ml-2 text-sm font-normal text-gray-400">
            ({results.length} transactions)
          </span>
        </h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              <th className="px-6 py-3">Transaction ID</th>
              <th className="px-6 py-3">Fraud Probability</th>
              <th className="px-6 py-3">Anomaly Score</th>
              <th className="px-6 py-3">Risk Level</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {results.map((r) => (
              <tr key={r.transaction_id} className="hover:bg-gray-50 transition-colors">
                <td className="whitespace-nowrap px-6 py-3 font-mono text-xs text-gray-700">
                  {r.transaction_id}
                </td>
                <td className="px-6 py-3">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-20 rounded-full bg-gray-200 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          r.fraud_score.fraud_probability >= 0.7
                            ? "bg-red-500"
                            : r.fraud_score.fraud_probability >= 0.3
                            ? "bg-amber-500"
                            : "bg-emerald-500"
                        }`}
                        style={{
                          width: `${Math.round(r.fraud_score.fraud_probability * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="text-xs text-gray-600">
                      {(r.fraud_score.fraud_probability * 100).toFixed(1)}%
                    </span>
                  </div>
                </td>
                <td className="px-6 py-3 text-xs text-gray-600">
                  {r.fraud_score.anomaly_score.toFixed(3)}
                </td>
                <td className="px-6 py-3">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                      riskColor[r.fraud_score.risk_level] ?? "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {r.fraud_score.risk_level}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
