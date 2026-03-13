import { useEffect, useState } from "react";
import { checkHealth } from "../services/api";

export default function Navbar() {
  const [status, setStatus] = useState<"connected" | "offline" | "checking">(
    "checking"
  );

  useEffect(() => {
    checkHealth()
      .then(() => setStatus("connected"))
      .catch(() => setStatus("offline"));
  }, []);

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
      {/* Logo */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white font-bold text-sm">
          FS
        </div>
        <h1 className="text-xl font-bold text-gray-800 tracking-tight">
          FinSentry
        </h1>
      </div>

      {/* Status */}
      <div className="flex items-center gap-2 text-sm">
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full ${
            status === "connected"
              ? "bg-emerald-500"
              : status === "offline"
              ? "bg-red-400"
              : "bg-amber-400 animate-pulse"
          }`}
        />
        <span className="text-gray-500">
          {status === "connected"
            ? "Backend Connected"
            : status === "offline"
            ? "Backend Offline"
            : "Checking…"}
        </span>
      </div>
    </header>
  );
}
