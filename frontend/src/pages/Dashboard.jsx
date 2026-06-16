import React, { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import {
  Cpu,
  HardDrive,
  Gauge,
  Users,
  FileText,
  Timer,
  Zap,
  Thermometer,
} from "lucide-react";
import { Card, StatCard, Badge, SectionTitle } from "../components/ui.jsx";
import { api } from "../api.js";

function fmt(n) {
  if (n == null) return "0";
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(Math.round(n));
}

function toSeries(history = []) {
  return history.map((s) => ({
    t: new Date(s.ts * 1000).toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
    gpu: s.gpu_util,
    mem: Math.round((s.mem_used_mb / Math.max(s.mem_total_mb, 1)) * 100),
    power: s.power_w,
  }));
}

function ChartTip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-ink-border bg-ink-900 px-3 py-2 text-xs">
      <div className="text-slate-400">{label}</div>
      <div className="font-mono font-semibold text-brand">
        {payload[0].value}
        {unit}
      </div>
    </div>
  );
}

export default function Dashboard({ metrics, connected }) {
  const [vllm, setVllm] = useState(null);

  useEffect(() => {
    const tick = () => api.modelStatus().then(setVllm).catch(() => {});
    tick();
    const id = setInterval(tick, 4000);
    return () => clearInterval(id);
  }, []);

  const m = metrics || {};
  const cur = m.current || {};
  const counters = m.counters || {};
  const lat = m.latency || {};
  const series = toSeries(m.history);
  const memPct = cur.mem_total_mb
    ? Math.round((cur.mem_used_mb / cur.mem_total_mb) * 100)
    : 0;
  const loadedModels = vllm?.running ? 1 : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-white">Centre de contrôle</h1>
          <p className="text-sm text-slate-400">
            Démo RAG MCP · vLLM local sur NVIDIA GB10 (mémoire unifiée)
          </p>
        </div>
        <Badge tone={connected ? "green" : "red"}>
          {connected ? "● Temps réel" : "● Hors ligne"}
        </Badge>
      </div>

      {/* Hero: tokens/s — point principal de la démo */}
      <Card className="relative overflow-hidden border-brand/30">
        <div className="absolute inset-0 bg-gradient-to-r from-brand/10 to-transparent" />
        <div className="relative flex flex-wrap items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 text-brand">
              <Zap size={18} />
              <span className="label text-brand">Débit du serveur local</span>
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-mono text-6xl font-extrabold text-white tabular-nums">
                {fmt(m.tokens_per_second)}
              </span>
              <span className="text-xl text-slate-300">tokens/s</span>
            </div>
            <p className="mt-1 text-sm text-slate-400">
              Total traité&nbsp;:{" "}
              <span className="font-mono text-brand">
                {fmt(counters.total_tokens_in + counters.total_tokens_out)}
              </span>{" "}
              tokens · {fmt(counters.total_tokens_in)} entrée /{" "}
              {fmt(counters.total_tokens_out)} sortie
            </p>
          </div>
          <div className="grid grid-cols-3 gap-6 text-center">
            <div>
              <div className="font-mono text-2xl font-bold text-white">
                {fmt(counters.total_requests)}
              </div>
              <div className="label">Requêtes</div>
            </div>
            <div>
              <div className="font-mono text-2xl font-bold text-white">
                {Math.round(lat.p50 || 0)}
                <span className="text-sm text-slate-400">ms</span>
              </div>
              <div className="label">Latence p50</div>
            </div>
            <div>
              <div className="font-mono text-2xl font-bold text-white">
                {Math.round(lat.p95 || 0)}
                <span className="text-sm text-slate-400">ms</span>
              </div>
              <div className="label">Latence p95</div>
            </div>
          </div>
        </div>
      </Card>

      {/* Stat grid */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          icon={Cpu}
          label="Modèles chargés"
          value={loadedModels}
          accent="brand"
          hint={vllm?.model || "Aucun modèle actif"}
        />
        <StatCard
          icon={HardDrive}
          label="Mémoire unifiée"
          value={memPct}
          unit="%"
          accent="violet"
          hint={`${fmt(cur.mem_used_mb)} / ${fmt(cur.mem_total_mb)} MB`}
        />
        <StatCard
          icon={FileText}
          label="Fichiers indexés"
          value={fmt(counters.indexed_files)}
          accent="blue"
          hint={`${fmt(counters.indexed_chunks)} chunks vectorisés`}
        />
        <StatCard
          icon={Users}
          label="Clients MCP"
          value={fmt(counters.connected_clients)}
          accent="amber"
          hint="connectés au serveur"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <SectionTitle
            icon={Gauge}
            title="Utilisation GPU"
            subtitle="Historique 15 minutes"
            right={
              <span className="font-mono text-2xl font-bold text-brand">
                {Math.round(cur.gpu_util || 0)}%
              </span>
            }
          />
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={series}>
                <defs>
                  <linearGradient id="gpuGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#76b900" stopOpacity={0.6} />
                    <stop offset="100%" stopColor="#76b900" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
                <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 10 }} minTickGap={40} />
                <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 10 }} width={28} />
                <Tooltip content={<ChartTip unit="%" />} />
                <Area
                  type="monotone"
                  dataKey="gpu"
                  stroke="#76b900"
                  strokeWidth={2}
                  fill="url(#gpuGrad)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <SectionTitle
            icon={HardDrive}
            title="Mémoire & énergie"
            subtitle="Historique 15 minutes"
            right={
              <span className="flex items-center gap-1 font-mono text-sm text-amber-400">
                <Thermometer size={14} /> {Math.round(cur.temp_c || 0)}°C ·{" "}
                {Math.round(cur.power_w || 0)}W
              </span>
            }
          />
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={series}>
                <defs>
                  <linearGradient id="memGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.6} />
                    <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
                <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 10 }} minTickGap={40} />
                <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 10 }} width={28} />
                <Tooltip content={<ChartTip unit="%" />} />
                <Area
                  type="monotone"
                  dataKey="mem"
                  stroke="#a78bfa"
                  strokeWidth={2}
                  fill="url(#memGrad)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Active model details */}
      <Card>
        <SectionTitle icon={Cpu} title="Modèle actif" subtitle="État du serveur vLLM" />
        {vllm?.running ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Detail label="Nom du modèle" value={vllm.model} />
            <Detail
              label="État"
              value={vllm.ready ? "Prêt" : "Chargement…"}
              tone={vllm.ready ? "green" : "amber"}
            />
            <Detail label="max_model_len" value={vllm.params?.max_model_len || "—"} />
            <Detail label="dtype / quant" value={`${vllm.params?.dtype || "auto"} ${vllm.params?.quantization || ""}`} />
          </div>
        ) : (
          <p className="text-sm text-slate-400">
            Aucun modèle vLLM en cours d'exécution. Lancez-en un depuis l'onglet
            «&nbsp;Modèles vLLM&nbsp;».
          </p>
        )}
      </Card>
    </div>
  );
}

function Detail({ label, value, tone }) {
  return (
    <div className="rounded-xl border border-ink-border bg-ink-900/40 p-3">
      <div className="label">{label}</div>
      <div className="mt-1 font-mono text-sm text-white">
        {tone ? <Badge tone={tone}>{value}</Badge> : value}
      </div>
    </div>
  );
}
