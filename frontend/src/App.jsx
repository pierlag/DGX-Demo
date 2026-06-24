import React, { useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Menu, Activity } from "lucide-react";
import Sidebar from "./components/Sidebar.jsx";
import { useMetrics } from "./hooks/useMetrics.js";
import Dashboard from "./pages/Dashboard.jsx";
import ModelsAdmin from "./pages/ModelsAdmin.jsx";
import McpAdmin from "./pages/McpAdmin.jsx";
import TunnelsAdmin from "./pages/TunnelsAdmin.jsx";
import DockerAdmin from "./pages/DockerAdmin.jsx";
import RagAdmin from "./pages/RagAdmin.jsx";
import Chat from "./pages/Chat.jsx";
import Studio3D from "./pages/Studio3D.jsx";

export default function App() {
  const { data, connected } = useMetrics();
  const [kioskMode, setKioskMode] = useState(true);
  const [navOpen, setNavOpen] = useState(false);

  const toggleKioskMode = () => setKioskMode((v) => !v);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        connected={connected}
        kioskMode={kioskMode}
        onKioskToggle={toggleKioskMode}
        open={navOpen}
        onClose={() => setNavOpen(false)}
      />

      {/* Mobile backdrop */}
      {navOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={() => setNavOpen(false)}
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="flex items-center gap-3 border-b border-ink-border bg-ink-900/80 px-4 py-3 backdrop-blur lg:hidden">
          <button
            type="button"
            aria-label="Ouvrir le menu"
            onClick={() => setNavOpen(true)}
            className="grid h-9 w-9 place-items-center rounded-lg border border-ink-border text-slate-300"
          >
            <Menu size={18} />
          </button>
          <div className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-black font-extrabold">
              v
            </div>
            <span className="text-base font-extrabold text-white">vibeMCP</span>
          </div>
          <Activity
            size={16}
            className={`ml-auto ${connected ? "text-brand" : "text-rose-400"}`}
          />
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl p-4 sm:p-6">
            <Routes>
              <Route path="/" element={<Dashboard metrics={data} connected={connected} />} />
              <Route path="/chat" element={<Chat />} />
              <Route path="/studio3d" element={<Studio3D />} />
              {!kioskMode && <Route path="/models" element={<ModelsAdmin />} />}
              {!kioskMode && <Route path="/mcp" element={<McpAdmin />} />}
              {!kioskMode && <Route path="/tunnels" element={<TunnelsAdmin />} />}
              {!kioskMode && <Route path="/docker" element={<DockerAdmin />} />}
              {!kioskMode && <Route path="/rag" element={<RagAdmin />} />}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}
