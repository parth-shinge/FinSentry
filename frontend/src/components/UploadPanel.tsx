import { useRef, useState } from "react";
import type { TransactionInput } from "../types/apiTypes";

interface Props {
  onUpload: (transactions: TransactionInput[]) => void;
  loading: boolean;
}

/** Parses a CSV string into TransactionInput rows. */
function parseCSV(text: string): TransactionInput[] {
  const lines = text.trim().split("\n");
  if (lines.length < 2) return [];

  const headers = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const rows: TransactionInput[] = [];

  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(",").map((c) => c.trim());
    if (cols.length !== headers.length) continue;

    const obj: Record<string, string> = {};
    headers.forEach((h, idx) => (obj[h] = cols[idx]));

    rows.push({
      transaction_id: obj["transaction_id"] ?? `TXN-${i}`,
      account_id: obj["account_id"] ?? "",
      sender_entity_id: obj["sender_entity_id"] ?? "",
      receiver_entity_id: obj["receiver_entity_id"] ?? "",
      amount: parseFloat(obj["amount"] ?? "0"),
      currency: obj["currency"] ?? "USD",
      timestamp: obj["timestamp"] ?? new Date().toISOString(),
      origin_country: obj["origin_country"] ?? "US",
      destination_country: obj["destination_country"] ?? "US",
      merchant_category: obj["merchant_category"],
      transaction_type: obj["transaction_type"],
      channel: obj["channel"],
      is_international:
        (obj["origin_country"] ?? "US") !== (obj["destination_country"] ?? "US"),
    });
  }

  return rows;
}

export default function UploadPanel({ onUpload, loading }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [rowCount, setRowCount] = useState(0);
  const [parsed, setParsed] = useState<TransactionInput[]>([]);

  const handleFile = (file: File) => {
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const txns = parseCSV(text);
      setParsed(txns);
      setRowCount(txns.length);
    };
    reader.readAsText(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <h3 className="text-base font-semibold text-gray-800 mb-3">
        Upload Transactions
      </h3>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => inputRef.current?.click()}
        className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 px-6 py-10 transition hover:border-blue-400 hover:bg-blue-50/30"
      >
        <svg className="mb-3 h-10 w-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        <p className="text-sm text-gray-600">
          {fileName ? (
            <>
              <span className="font-medium text-blue-600">{fileName}</span> —{" "}
              {rowCount} transactions
            </>
          ) : (
            <>
              <span className="font-medium text-blue-600">Click to upload</span>{" "}
              or drag & drop a CSV file
            </>
          )}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleChange}
        />
      </div>

      {/* Actions */}
      {parsed.length > 0 && (
        <button
          onClick={() => onUpload(parsed)}
          disabled={loading}
          className="mt-4 w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Running Pipeline…
            </>
          ) : (
            `Run Investigation (${parsed.length} transactions)`
          )}
        </button>
      )}
    </div>
  );
}
