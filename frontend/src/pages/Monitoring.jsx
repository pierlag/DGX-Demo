import React, { useState } from "react";
import { Activity, ExternalLink, RefreshCw } from "lucide-react";
import { Card, SectionTitle, Badge } from "../components/ui.jsx";
import { grafanaUrl } from "../api.js";

// Embeds the provisioned Grafana dashboard (Prometheus + Loki) in an iframe.
// Grafana is brought up by docker-compose (service "grafana", port 3000) and
// scrapes the backend /metrics endpoint + ships container logs via Promtail.
export default function Monitoring() {
  const [reloadKey, setReloadKey] = useState(0);
  const src = grafanaUrl("/d/dgx-demo/dgx-demo-live-metrics?kiosk&theme=dark&refresh=5s");
  const openUrl = grafanaUrl("/d/dgx-demo/dgx-demo-live-metrics?theme=dark");

  return (
    <div className="space-y-6">
      <SectionTitle
        icon={Activity}
        title="Monitoring · Grafana"
        subtitle="GPU · vLLM · RAG · Copilot CLI · énergie & CO₂ — Prometheus + Loki"
        right={
          <div className="flex items-center gap-2">
            <Badge tone="green">Grafana :3000</Badge>
            <button
              className="btn-ghost"
              onClick={() => setReloadKey((k) => k + 1)}
              title="Recharger"
            >
              <RefreshCw size={16} /> Recharger
            </button>
            <a className="btn-ghost" href={openUrl} target="_blank" rel="noreferrer">
              <ExternalLink size={16} /> Ouvrir
            </a>
          </div>
        }
      />

      <Card className="overflow-hidden p-0">
        <iframe
          key={reloadKey}
          title="Grafana — DGX Demo"
          src={src}
          className="h-[calc(100vh-220px)] min-h-[640px] w-full border-0 bg-ink-900"
        />
      </Card>

      <p className="text-xs text-slate-500">
        Si le tableau de bord ne se charge pas, démarrez la stack&nbsp;:
        <span className="text-brand"> docker compose up -d prometheus loki promtail grafana</span>.
        Grafana est accessible sur <span className="text-brand">http://localhost:3000</span>{" "}
        (anonyme en lecture · admin / admin pour éditer).
      </p>
    </div>
  );
}
