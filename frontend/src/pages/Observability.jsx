import React, { useMemo, useState } from "react";
import { Activity, ExternalLink, RefreshCw, Gauge } from "lucide-react";
import { Card, SectionTitle, Badge } from "../components/ui.jsx";

// The provisioned Grafana stack publishes on :3000 and bundles a dashboard with
// a fixed UID (see observability/grafana/dashboards/ollama-copilot.json).
const GRAFANA_PORT = 3000;
const DASHBOARD_UID = "ollama-copilot";

export default function Observability() {
  const [reloadKey, setReloadKey] = useState(0);

  const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
  const grafanaBase = `http://${host}:${GRAFANA_PORT}`;

  const dashUrl = useMemo(
    () => `${grafanaBase}/d/${DASHBOARD_UID}?orgId=1&kiosk&refresh=5s&theme=dark`,
    [grafanaBase]
  );

  return (
    <div className="space-y-6">
      <SectionTitle
        icon={Gauge}
        title="Observabilité (Grafana)"
        subtitle="Métriques temps réel du backend Ollama hors-ligne : tokens, KV cache, throughput, taux de cache, requêtes HTTP — agrégés par Prometheus + Loki."
        right={
          <div className="flex items-center gap-2">
            <button className="btn-ghost" onClick={() => setReloadKey((k) => k + 1)}>
              <RefreshCw size={16} /> Recharger
            </button>
            <a className="btn-primary" href={dashUrl} target="_blank" rel="noreferrer">
              <ExternalLink size={16} /> Ouvrir Grafana
            </a>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <Badge tone="green">Grafana :3000</Badge>
        <Badge tone="blue">Prometheus :9090</Badge>
        <Badge tone="slate">Loki :3100</Badge>
        <Badge tone="slate">Exporter :9105</Badge>
        <span className="text-slate-500">
          Stack provisionné automatiquement. Login anonyme (admin/admin pour éditer).
        </span>
      </div>

      <Card className="overflow-hidden p-0">
        <iframe
          key={reloadKey}
          title="Grafana — Ollama / Copilot CLI"
          src={dashUrl}
          className="h-[78vh] w-full border-0 bg-ink-900"
          loading="lazy"
        />
      </Card>

      <Card>
        <div className="flex items-start gap-3 text-sm text-slate-400">
          <Activity size={18} className="mt-0.5 shrink-0 text-brand" />
          <div className="space-y-1">
            <p>
              Si le tableau de bord reste vide : démarrez la stack
              (<span className="font-mono text-slate-300">docker compose up -d</span>),
              vérifiez que le conteneur <span className="font-mono text-slate-300">dgx-demo-ollama</span> tourne,
              puis envoyez une requête au modèle (page « Copilot hors-ligne ») pour générer des métriques.
            </p>
            <p className="text-slate-500">
              L'embarquement iframe nécessite <span className="font-mono">GF_SECURITY_ALLOW_EMBEDDING=true</span>{" "}
              (déjà activé dans <span className="font-mono">docker-compose.yml</span>).
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
