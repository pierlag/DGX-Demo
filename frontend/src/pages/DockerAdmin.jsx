import React, { useState, useEffect, useRef } from "react";
import {
  Container,
  Play,
  Square,
  Settings,
  AlertCircle,
  RefreshCw,
  Loader2,
} from "lucide-react";
import { Card, SectionTitle, Badge, Spinner } from "../components/ui.jsx";
import { api } from "../api.js";

export default function DockerAdmin() {
  const [containers, setContainers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [configOpen, setConfigOpen] = useState(false);
  const [config, setConfig] = useState(null);
  const [refreshInterval, setRefreshInterval] = useState(3000);
  const [error, setError] = useState(null);
  const [connected, setConnected] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const inFlight = useRef(false);

  const fetchContainers = async () => {
    // Avoid overlapping polls and don't disturb a running action.
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const data = await api.listDockerContainers();
      setContainers(data);
      setConnected(true);
      setError(null);
    } catch (err) {
      setConnected(false);
      setError(err.message || "Erreur de connexion au démon Docker");
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  };

  const handleStart = async (id) => {
    setBusyId(id);
    setError(null);
    try {
      await api.startDockerContainer(id);
      await fetchContainers();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleStop = async (id) => {
    setBusyId(id);
    setError(null);
    try {
      await api.stopDockerContainer(id);
      await fetchContainers();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleViewConfig = async (id) => {
    setSelectedId(id);
    setConfig(null);
    setConfigOpen(true);
    try {
      const data = await api.getDockerContainerConfig(id);
      setConfig(data);
    } catch (err) {
      setError(err.message);
      setConfigOpen(false);
    }
  };

  useEffect(() => {
    fetchContainers();
    const interval = setInterval(fetchContainers, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  const isRunning = (status) => status.toLowerCase().includes("up");

  const runningCount = containers.filter((c) => isRunning(c.status)).length;

  return (
    <div className="space-y-6">
      <SectionTitle
        icon={Container}
        title="Admin · Gestion Docker"
        subtitle="Containers en temps réel · CPU / mémoire · start / stop"
        right={
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-xs text-slate-400">
              <span
                className={`h-2 w-2 rounded-full ${
                  connected ? "bg-brand animate-pulse" : "bg-rose-500"
                }`}
              />
              {connected ? "Connecté au démon" : "Déconnecté"}
            </span>
            <Badge tone="green">{runningCount} actif(s)</Badge>
          </div>
        }
      />

      <Card>
        <div className="mb-4 flex items-center justify-between">
          <span className="label">{containers.length} container(s)</span>
          <div className="flex items-center gap-2">
            <select
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(parseInt(e.target.value))}
              className="input w-auto"
            >
              <option value={2000}>Rafraîchir : 2s</option>
              <option value={3000}>Rafraîchir : 3s</option>
              <option value={5000}>Rafraîchir : 5s</option>
              <option value={10000}>Rafraîchir : 10s</option>
            </select>
            <button className="btn-ghost" onClick={fetchContainers}>
              <RefreshCw size={16} /> Actualiser
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3">
            <AlertCircle className="text-rose-400" size={18} />
            <p className="text-sm text-rose-300">{error}</p>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-10">
            <Spinner size={24} />
          </div>
        ) : containers.length === 0 ? (
          <p className="py-8 text-center text-slate-500">
            Aucun container Docker détecté
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-ink-border text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-3 font-medium">Nom</th>
                  <th className="px-3 py-3 font-medium">Image</th>
                  <th className="px-3 py-3 font-medium">État</th>
                  <th className="px-3 py-3 text-center font-medium">CPU</th>
                  <th className="px-3 py-3 text-center font-medium">Mémoire</th>
                  <th className="px-3 py-3 text-center font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {containers.map((cont) => {
                  const running = isRunning(cont.status);
                  const busy = busyId === cont.id;
                  return (
                    <tr
                      key={cont.id}
                      className="border-b border-ink-border/60 transition-colors hover:bg-ink-700/40"
                    >
                      <td className="px-3 py-3">
                        <div className="font-mono text-brand">{cont.name}</div>
                        <div className="font-mono text-[11px] text-slate-600">
                          {cont.id}
                        </div>
                      </td>
                      <td className="max-w-[220px] truncate px-3 py-3 text-slate-300">
                        {cont.image}
                      </td>
                      <td className="px-3 py-3">
                        <Badge tone={running ? "green" : "slate"}>
                          {running ? "● En cours" : "○ Arrêté"}
                        </Badge>
                        <div className="mt-1 text-[11px] text-slate-500">
                          {cont.status}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-center font-mono">
                        {running && cont.cpu_percent != null ? (
                          <span
                            className={
                              cont.cpu_percent > 50
                                ? "text-amber-400"
                                : "text-slate-200"
                            }
                          >
                            {cont.cpu_percent.toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        {running && cont.memory_usage_mb != null ? (
                          <div className="flex flex-col items-center">
                            <span className="font-mono text-slate-200">
                              {cont.memory_usage_mb >= 1024
                                ? `${(cont.memory_usage_mb / 1024).toFixed(1)} GB`
                                : `${cont.memory_usage_mb.toFixed(0)} MB`}
                            </span>
                            <div className="mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-ink-900">
                              <div
                                className={
                                  cont.memory_percent > 80
                                    ? "h-full bg-rose-500"
                                    : cont.memory_percent > 50
                                      ? "h-full bg-amber-500"
                                      : "h-full bg-brand"
                                }
                                style={{
                                  width: `${Math.min(cont.memory_percent || 0, 100)}%`,
                                }}
                              />
                            </div>
                            <span className="mt-1 text-[11px] text-slate-600">
                              {cont.memory_percent != null
                                ? `${cont.memory_percent.toFixed(1)}%`
                                : ""}
                            </span>
                          </div>
                        ) : (
                          <div className="text-center text-slate-600">—</div>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex justify-center gap-2">
                          {running ? (
                            <button
                              onClick={() => handleStop(cont.id)}
                              disabled={busy}
                              className="grid h-9 w-9 place-items-center rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-300 transition hover:bg-rose-500/20 disabled:opacity-40"
                              title="Arrêter"
                            >
                              {busy ? (
                                <Loader2 size={16} className="animate-spin" />
                              ) : (
                                <Square size={16} />
                              )}
                            </button>
                          ) : (
                            <button
                              onClick={() => handleStart(cont.id)}
                              disabled={busy}
                              className="grid h-9 w-9 place-items-center rounded-lg border border-brand/30 bg-brand/10 text-brand transition hover:bg-brand/20 disabled:opacity-40"
                              title="Démarrer"
                            >
                              {busy ? (
                                <Loader2 size={16} className="animate-spin" />
                              ) : (
                                <Play size={16} />
                              )}
                            </button>
                          )}
                          <button
                            onClick={() => handleViewConfig(cont.id)}
                            className="grid h-9 w-9 place-items-center rounded-lg border border-ink-border bg-ink-900/40 text-slate-300 transition hover:bg-ink-700"
                            title="Configuration"
                          >
                            <Settings size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Config Modal */}
      {configOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => setConfigOpen(false)}
        >
          <div
            className="card max-h-[80vh] w-full max-w-3xl overflow-hidden p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="font-mono text-sm text-white">
                Configuration · {selectedId}
              </h3>
              <button
                onClick={() => setConfigOpen(false)}
                className="text-slate-400 transition hover:text-white"
              >
                ✕
              </button>
            </div>
            {config ? (
              <pre className="max-h-[60vh] overflow-auto rounded-xl bg-ink-900 p-4 text-xs text-slate-300">
                {JSON.stringify(config, null, 2)}
              </pre>
            ) : (
              <div className="flex justify-center py-10">
                <Spinner size={24} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
