import React, { useEffect, useState } from "react";
import { Network, Save, Play, Square } from "lucide-react";
import { Card, SectionTitle, Badge } from "../components/ui.jsx";
import { api } from "../api.js";

export default function McpAdmin() {
  const [metaPrompt, setMetaPrompt] = useState("");
  const [mcp, setMcp] = useState(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState("");

  const refresh = () => {
    api.mcpStatus().then(setMcp).catch(() => {});
  };

  useEffect(() => {
    api.getMcpConfig().then((c) => setMetaPrompt(c.meta_prompt || "")).catch(() => {});
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, []);

  const save = async () => {
    await api.setMcpConfig(metaPrompt);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const startMcp = async () => {
    setBusy("mcp");
    await api.startMcp();
    setBusy("");
    refresh();
  };
  const stopMcp = async () => {
    await api.stopMcp();
    refresh();
  };

  return (
    <div className="space-y-6">
      <SectionTitle
        icon={Network}
        title="Admin · Serveur MCP"
        subtitle="Méta-prompt · démarrage du serveur RAG MCP"
        right={
          mcp?.running ? <Badge tone="green">● MCP actif</Badge> : <Badge tone="slate">MCP arrêté</Badge>
        }
      />

      {/* Meta prompt */}
      <Card>
        <SectionTitle title="Méta-prompt du serveur RAG" subtitle="Injecté en system prompt pour chaque requête" />
        <textarea
          className="input min-h-[140px] font-mono leading-relaxed"
          value={metaPrompt}
          onChange={(e) => setMetaPrompt(e.target.value)}
        />
        <div className="mt-3 flex items-center gap-3">
          <button className="btn-primary" onClick={save}>
            <Save size={16} /> Enregistrer
          </button>
          {saved && <span className="text-sm text-brand">Enregistré ✓</span>}
        </div>
      </Card>

      {/* MCP server control */}
      <Card>
        <SectionTitle title="Serveur MCP" subtitle={`Transport HTTP · port ${mcp?.port ?? "—"}`} />
        <div className="flex items-center gap-3">
          <button className="btn-primary" onClick={startMcp} disabled={mcp?.running || busy === "mcp"}>
            <Play size={16} /> Démarrer
          </button>
          <button className="btn-ghost" onClick={stopMcp} disabled={!mcp?.running}>
            <Square size={16} /> Arrêter
          </button>
          {mcp?.message && <span className="text-sm text-slate-400">{mcp.message}</span>}
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Pour exposer ce serveur sur Internet, créez un tunnel depuis la page{" "}
          <span className="text-brand">Tunnels</span>.
        </p>
      </Card>
    </div>
  );
}
