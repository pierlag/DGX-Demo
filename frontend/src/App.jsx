import React from "react";
import { Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar.jsx";
import { useMetrics } from "./hooks/useMetrics.js";
import Dashboard from "./pages/Dashboard.jsx";
import ModelsAdmin from "./pages/ModelsAdmin.jsx";
import McpAdmin from "./pages/McpAdmin.jsx";
import TunnelsAdmin from "./pages/TunnelsAdmin.jsx";
import DockerAdmin from "./pages/DockerAdmin.jsx";
import RagAdmin from "./pages/RagAdmin.jsx";
import Chat from "./pages/Chat.jsx";

export default function App() {
  const { data, connected } = useMetrics();
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar connected={connected} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl p-6">
          <Routes>
            <Route path="/" element={<Dashboard metrics={data} connected={connected} />} />
            <Route path="/models" element={<ModelsAdmin />} />
            <Route path="/mcp" element={<McpAdmin />} />
            <Route path="/tunnels" element={<TunnelsAdmin />} />
            <Route path="/docker" element={<DockerAdmin />} />
            <Route path="/rag" element={<RagAdmin />} />
            <Route path="/chat" element={<Chat />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
