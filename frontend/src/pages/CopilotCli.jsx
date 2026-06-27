import React, { useEffect, useState } from "react";
import {
  Bot, Play, FileCode, Copy, Check, RefreshCw, CheckCircle2, XCircle,
  Terminal, Power,
} from "lucide-react";
import { Card, SectionTitle, Badge, Spinner } from "../components/ui.jsx";
import { api } from "../api.js";

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 1200);
    } catch {
      /* clipboard blocked (insecure context) — ignore */
    }
  };
  return (
    <button className="btn-ghost" onClick={copy} title="Copier">
      {done ? <Check size={14} /> : <Copy size={14} />}
      {done ? "Copié" : "Copier"}
    </button>
  );
}

const TEST_LABELS = {
  models: "Endpoint /models (OpenAI-compatible)",
  chat: "Complétion chat (non-stream)",
  stream: "Streaming",
  tools: "Tool calling (tool_calls structurés)",
};

export default function CopilotCli() {
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(null);
  const [tests, setTests] = useState(null);
  const [busy, setBusy] = useState("");
  const [scriptPath, setScriptPath] = useState("");

  const refresh = () => {
    api.copilotStatus().then(setStatus).catch(() => {});
    api.copilotConfig().then(setConfig).catch(() => {});
  };

  useEffect(() => {
    refresh();
    const id = setInterval(() => api.copilotStatus().then(setStatus).catch(() => {}), 5000);
    return () => clearInterval(id);
  }, []);

  const runTests = async () => {
    setBusy("test");
    try {
      const r = await api.copilotTest();
      setTests(r);
      refresh();
    } finally {
      setBusy("");
    }
  };

  const writeScript = async () => {
    setBusy("script");
    try {
      const r = await api.copilotWriteScript();
      setScriptPath(r.path || "");
    } finally {
      setBusy("");
    }
  };

  const toggleSession = async () => {
    const next = !status?.session_active;
    await api.copilotSetSession(next);
    refresh();
  };

  const cliEnvText = config
    ? Object.entries(config.cli_env)
        .map(([k, v]) => `export ${k}="${v}"`)
        .join("\n")
    : "";

  return (
    <div className="space-y-6">
      <SectionTitle
        icon={Bot}
        title="Copilot CLI · VS Code (offline)"
        subtitle="Branche GitHub Copilot sur le serveur vLLM local en mode airgap (BYOK)"
        right={
          status?.session_active ? (
            <Badge tone="green">● Session offline active</Badge>
          ) : (
            <Badge tone="slate">Session inactive</Badge>
          )
        }
      />

      {/* Readiness */}
      <Card>
        <SectionTitle
          title="État"
          subtitle="Prérequis pour le mode offline"
          right={
            <button className="btn-ghost" onClick={refresh}>
              <RefreshCw size={16} /> Rafraîchir
            </button>
          }
        />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatusTile ok={status?.vllm_up} label="Serveur vLLM" value={status?.vllm_up ? "en ligne" : "hors ligne"} />
          <StatusTile ok={!!status?.model} label="Modèle servi" value={status?.model || "—"} />
          <StatusTile ok={status?.copilot_installed} label="Copilot CLI" value={status?.copilot_installed ? (status?.copilot_version || "présent") : "absent"} />
          <StatusTile ok={status?.vscode_installed} label="VS Code" value={status?.vscode_installed ? (status?.vscode_version || "présent") : "absent"} />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button className="btn-primary" onClick={runTests} disabled={busy === "test"}>
            {busy === "test" ? <Spinner /> : <Play size={16} />} Lancer les tests de validation
          </button>
          <button className="btn-ghost" onClick={toggleSession}>
            <Power size={16} /> {status?.session_active ? "Marquer inactive" : "Marquer active"}
          </button>
          {!status?.copilot_installed && (
            <span className="text-xs text-amber-300">
              Installez la CLI : <span className="font-mono">npm install -g @github/copilot</span>
            </span>
          )}
        </div>
      </Card>

      {/* Validation results */}
      {tests && (
        <Card>
          <SectionTitle
            title="Résultats des tests BYOK"
            subtitle={`Modèle : ${tests.model || "—"}`}
            right={
              tests.ok ? (
                <Badge tone="green">{tests.passed}/{tests.total} OK</Badge>
              ) : (
                <Badge tone="amber">{tests.passed}/{tests.total} OK</Badge>
              )
            }
          />
          <div className="overflow-hidden rounded-xl border border-ink-border">
            <table className="w-full text-sm">
              <thead className="bg-ink-700/40 text-left text-slate-400">
                <tr>
                  <th className="px-4 py-2 font-medium">Test</th>
                  <th className="px-4 py-2 font-medium">Résultat</th>
                  <th className="px-4 py-2 font-medium">Latence</th>
                  <th className="px-4 py-2 font-medium">Détail</th>
                </tr>
              </thead>
              <tbody>
                {tests.results.map((r) => (
                  <tr key={r.test} className="border-t border-ink-border">
                    <td className="px-4 py-2 text-slate-200">{TEST_LABELS[r.test] || r.test}</td>
                    <td className="px-4 py-2">
                      {r.ok ? (
                        <span className="inline-flex items-center gap-1 text-brand">
                          <CheckCircle2 size={15} /> OK
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-rose-300">
                          <XCircle size={15} /> Échec
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 font-mono tabular-nums text-slate-300">{r.latency_ms} ms</td>
                    <td className="px-4 py-2 text-slate-400">{r.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Copilot CLI config */}
      <Card>
        <SectionTitle
          icon={Terminal}
          title="Configuration Copilot CLI"
          subtitle="Variables d'environnement BYOK (offline)"
          right={cliEnvText && <CopyButton text={cliEnvText} />}
        />
        <pre className="input overflow-x-auto whitespace-pre p-4 font-mono text-xs leading-relaxed text-slate-200">
{cliEnvText || "—"}
        </pre>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button className="btn-primary" onClick={writeScript} disabled={busy === "script"}>
            {busy === "script" ? <Spinner /> : <FileCode size={16} />} Générer le script de lancement
          </button>
          {scriptPath && (
            <span className="text-sm text-brand">
              Écrit : <span className="font-mono">{scriptPath}</span> — lancez-le puis utilisez{" "}
              <span className="font-mono">copilot</span>.
            </span>
          )}
        </div>
      </Card>

      {/* VS Code config */}
      {config?.vscode && (
        <Card>
          <SectionTitle
            title="Configuration VS Code Chat"
            subtitle="Chat → Manage Models → Add → OpenAI Compatible"
            right={<CopyButton text={config.vscode.settings_json} />}
          />
          <div className="grid gap-2 text-sm sm:grid-cols-3">
            <KV label="Base URL" value={config.vscode.base_url} />
            <KV label="API Key" value={config.vscode.api_key} />
            <KV label="Model" value={config.vscode.model} />
          </div>
          <pre className="input mt-4 overflow-x-auto whitespace-pre p-4 font-mono text-xs leading-relaxed text-slate-200">
{config.vscode.settings_json}
          </pre>
        </Card>
      )}
    </div>
  );
}

function StatusTile({ ok, label, value }) {
  return (
    <div className="rounded-xl border border-ink-border bg-ink-900/40 p-3">
      <p className="label">{label}</p>
      <div className="mt-1 flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${ok ? "bg-brand" : "bg-rose-500"}`} />
        <span className="truncate text-sm font-medium text-slate-200" title={value}>{value}</span>
      </div>
    </div>
  );
}

function KV({ label, value }) {
  return (
    <div className="rounded-lg border border-ink-border px-3 py-2">
      <p className="label">{label}</p>
      <p className="mt-0.5 truncate font-mono text-xs text-slate-200" title={value}>{value}</p>
    </div>
  );
}
