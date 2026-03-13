import { Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Investigations from "./pages/Investigations";
import Reports from "./pages/Reports";
import { PipelineProvider } from "./hooks/usePipeline";

export default function App() {
  return (
    <PipelineProvider>
      <div className="flex h-screen flex-col bg-white">
        <Navbar />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-y-auto bg-gray-50">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/investigations" element={<Investigations />} />
              <Route path="/reports" element={<Reports />} />
            </Routes>
          </main>
        </div>
      </div>
    </PipelineProvider>
  );
}