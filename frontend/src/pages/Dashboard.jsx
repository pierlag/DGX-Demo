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
  Smartphone,
  QrCode,
  Leaf,
  ArrowDownToLine,
  ArrowUpFromLine,
  Boxes,
  Image as ImageIcon,
  Bot,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { Card, StatCard, Badge, SectionTitle } from "../components/ui.jsx";
import { api } from "../api.js";

function fmt(n) {
  if (n == null) return "0";
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(Math.round(n));
}

// Energy in Wh -> compact "Wh" / "mWh" string.
function fmtEnergy(wh) {
  if (wh == null) return "0";
  if (wh >= 1) return `${wh.toFixed(2)} Wh`;
  return `${(wh * 1000).toFixed(1)} mWh`;
}

// CO2 in grams -> compact "g" / "mg" string.
function fmtCo2(g) {
  if (g == null) return "0";
  if (g >= 1) return `${g.toFixed(2)} g`;
  return `${(g * 1000).toFixed(1)} mg`;
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
  const [dashTunnel, setDashTunnel] = useState(null);
  const [studio, setStudio] = useState(null);
  const [ollama, setOllama] = useState(null);

  useEffect(() => {
    const tick = () => api.modelStatus().then(setVllm).catch(() => {});
    tick();
    const id = setInterval(tick, 4000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const tick = () => api.ollamaMetrics().then(setOllama).catch(() => setOllama(null));
    tick();
    const id = setInterval(tick, 4000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const tick = () => api.studioStatus().then(setStudio).catch(() => {});
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const tick = () =>
      api
        .tunnelList()
        .then((r) =>
          setDashTunnel((r.tunnels || []).find((t) => t.name === "dashboard") || null)
        )
        .catch(() => {});
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, []);

  const chatUrl = dashTunnel?.url ? `${dashTunnel.url.replace(/\/$/, "")}/chat` : "";

  const m = metrics || {};
  const cur = m.current || {};
  const counters = m.counters || {};
  const lat = m.latency || {};
  const series = toSeries(m.history);
  const memPct = cur.mem_total_mb
    ? Math.round((cur.mem_used_mb / cur.mem_total_mb) * 100)
    : 0;
  const studioImageLoaded = !!studio?.image_gen?.loaded;
  const studioTrellisLoaded = !!studio?.trellis?.loaded;
  const studioLoaded = (studioImageLoaded ? 1 : 0) + (studioTrellisLoaded ? 1 : 0);
  const loadedModels = (vllm?.running ? 1 : 0) + studioLoaded;
  const recent = m.recent_requests || [];
  const carbonIntensity = m.carbon_intensity_g_per_kwh;
  const ollamaRecent = ollama?.recent_requests || [];
  const studioMetrics = m.studio || {};
  const studioTotals = studioMetrics.totals || {};
  const studioRecent = studioMetrics.recent || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-extrabold text-white sm:text-2xl">Centre de contrôle</h1>
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
              <span className="font-mono text-4xl font-extrabold text-white tabular-nums sm:text-6xl">
                {fmt(m.tokens_per_second)}
              </span>
              <span className="text-lg text-slate-300 sm:text-xl">tokens/s</span>
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
          <div className="grid w-full grid-cols-3 gap-4 text-center sm:w-auto sm:gap-6">
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

      {/* Copilot hors-ligne (Ollama) : requêtes & débit du modèle chargé */}
      <Card className="relative overflow-hidden border-violet-500/30">
        <div className="absolute inset-0 bg-gradient-to-r from-violet-500/10 to-transparent" />
        <div className="relative flex flex-wrap items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 text-violet-300">
              <Bot size={18} />
              <span className="label text-violet-300">Copilot hors-ligne (Ollama)</span>
              {ollama?.available && ollama?.loaded ? (
                <Badge tone={ollama.generating ? "green" : "violet"}>
                  {ollama.generating ? "● en génération" : "chargé"}
                </Badge>
              ) : (
                <Badge tone="slate">inactif</Badge>
              )}
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-mono text-4xl font-extrabold text-white tabular-nums sm:text-5xl">
                {fmt(ollama?.tokens_per_second)}
              </span>
              <span className="text-lg text-slate-300">tokens/s</span>
            </div>
            <p className="mt-1 text-sm text-slate-400">
              {ollama?.available && ollama?.model?.name ? (
                <>
                  Modèle&nbsp;:{" "}
                  <span className="font-mono text-violet-300">{ollama.model.name}</span>
                  {ollama.model.params ? ` · ${ollama.model.params}` : ""}
                  {ollama.model.processor ? ` · ${ollama.model.processor}` : ""}
                  {ollama.generating ? "" : " · débit du dernier échange"}
                </>
              ) : (
                "Aucun modèle Ollama chargé — lancez-en un depuis l'onglet « Copilot hors-ligne »."
              )}
            </p>
          </div>
          <div className="grid w-full grid-cols-3 gap-4 text-center sm:w-auto sm:gap-6">
            <div>
              <div className="font-mono text-2xl font-bold text-white">
                {fmt(ollama?.requests)}
              </div>
              <div className="label">Requêtes</div>
            </div>
            <div>
              <div className="font-mono text-2xl font-bold text-white">
                {fmt(ollama?.generated_tokens_total)}
              </div>
              <div className="label">Tokens générés</div>
            </div>
            <div>
              <div className="font-mono text-2xl font-bold text-white">
                {fmt(ollama?.turns)}
              </div>
              <div className="label">Échanges</div>
            </div>
          </div>
        </div>
      </Card>

      {/* Historique des 5 dernières requêtes Copilot hors-ligne (énergie & CO2) */}
      <Card>
        <SectionTitle
          icon={Bot}
          title="5 dernières requêtes · Copilot hors-ligne"
          subtitle="Tokens, énergie consommée et émissions CO₂ par requête Ollama"
          right={
            carbonIntensity != null ? (
              <span className="flex items-center gap-1 font-mono text-xs text-emerald-400">
                <Leaf size={14} /> {carbonIntensity} gCO₂/kWh · France
              </span>
            ) : null
          }
        />
        {ollamaRecent.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="label border-b border-ink-border text-left">
                  <th className="py-2 pr-4 font-medium">Heure</th>
                  <th className="py-2 pr-4 text-right font-medium">
                    <span className="inline-flex items-center gap-1">
                      <ArrowDownToLine size={13} /> Entrée
                    </span>
                  </th>
                  <th className="py-2 pr-4 text-right font-medium">
                    <span className="inline-flex items-center gap-1">
                      <ArrowUpFromLine size={13} /> Sortie
                    </span>
                  </th>
                  <th className="py-2 pr-4 text-right font-medium">Débit</th>
                  <th className="py-2 pr-4 text-right font-medium">Énergie</th>
                  <th className="py-2 text-right font-medium">CO₂</th>
                </tr>
              </thead>
              <tbody className="font-mono text-white">
                {ollamaRecent.map((r, i) => (
                  <tr key={i} className="border-b border-ink-border/50 last:border-0">
                    <td className="py-2 pr-4 text-slate-300">
                      {new Date(r.ts * 1000).toLocaleTimeString("fr-FR")}
                    </td>
                    <td className="py-2 pr-4 text-right">{fmt(r.tokens_in)}</td>
                    <td className="py-2 pr-4 text-right">{fmt(r.tokens_out)}</td>
                    <td className="py-2 pr-4 text-right text-violet-300">
                      {fmt(r.gen_tps)} <span className="text-slate-500">t/s</span>
                    </td>
                    <td className="py-2 pr-4 text-right text-amber-400">
                      {fmtEnergy(r.energy_wh)}
                    </td>
                    <td className="py-2 text-right text-emerald-400">
                      {fmtCo2(r.co2_g)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-400">
            Aucune requête Copilot hors-ligne enregistrée pour le moment. Lancez
            une conversation avec le modèle Ollama chargé pour voir apparaître la
            consommation énergétique et les émissions CO₂.
          </p>
        )}
      </Card>

      {/* Dernières requêtes : tokens, énergie & CO2 (mix France) */}
      <Card>
        <SectionTitle
          icon={Leaf}
          title="3 dernières requêtes"
          subtitle="Tokens, énergie consommée et émissions CO₂"
          right={
            carbonIntensity != null ? (
              <span className="flex items-center gap-1 font-mono text-xs text-emerald-400">
                <Leaf size={14} /> {carbonIntensity} gCO₂/kWh · France
              </span>
            ) : null
          }
        />
        {recent.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="label border-b border-ink-border text-left">
                  <th className="py-2 pr-4 font-medium">Heure</th>
                  <th className="py-2 pr-4 text-right font-medium">
                    <span className="inline-flex items-center gap-1">
                      <ArrowDownToLine size={13} /> Entrée
                    </span>
                  </th>
                  <th className="py-2 pr-4 text-right font-medium">
                    <span className="inline-flex items-center gap-1">
                      <ArrowUpFromLine size={13} /> Sortie
                    </span>
                  </th>
                  <th className="py-2 pr-4 text-right font-medium">Énergie</th>
                  <th className="py-2 text-right font-medium">CO₂</th>
                </tr>
              </thead>
              <tbody className="font-mono text-white">
                {recent.map((r, i) => (
                  <tr key={i} className="border-b border-ink-border/50 last:border-0">
                    <td className="py-2 pr-4 text-slate-300">
                      {new Date(r.ts * 1000).toLocaleTimeString("fr-FR")}
                    </td>
                    <td className="py-2 pr-4 text-right">{fmt(r.tokens_in)}</td>
                    <td className="py-2 pr-4 text-right">{fmt(r.tokens_out)}</td>
                    <td className="py-2 pr-4 text-right text-amber-400">
                      {fmtEnergy(r.energy_wh)}
                    </td>
                    <td className="py-2 text-right text-emerald-400">
                      {fmtCo2(r.co2_g)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-400">
            Aucune requête traitée pour le moment. Lancez une conversation pour
            voir apparaître la consommation énergétique et les émissions CO₂.
          </p>
        )}
      </Card>

      {/* Studio 3D : appels, modèles chargés, énergie & CO2 */}
      <Card>
        <SectionTitle
          icon={Boxes}
          title="Studio 3D"
          subtitle="Appels texte→image & image→3D · énergie et CO₂"
          right={
            <span className="font-mono text-2xl font-bold text-brand">
              {fmt(studioTotals.requests)}
              <span className="ml-1 text-sm text-slate-400">appels</span>
            </span>
          }
        />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Detail
            label="Texte → image"
            value={
              <Badge tone={studioImageLoaded ? "green" : "slate"}>
                {studioImageLoaded ? "Chargé" : "Inactif"}
              </Badge>
            }
            tone={undefined}
          />
          <Detail
            label="Image → 3D (TRELLIS)"
            value={
              <Badge tone={studioTrellisLoaded ? "green" : "slate"}>
                {studioTrellisLoaded ? "Chargé" : "Inactif"}
              </Badge>
            }
            tone={undefined}
          />
          <Detail
            label="Énergie cumulée"
            value={<span className="text-amber-400">{fmtEnergy(studioTotals.energy_wh)}</span>}
          />
          <Detail
            label="CO₂ cumulé"
            value={<span className="text-emerald-400">{fmtCo2(studioTotals.co2_g)}</span>}
          />
        </div>

        <div className="mt-4">
          {studioRecent.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="label border-b border-ink-border text-left">
                    <th className="py-2 pr-4 font-medium">Heure</th>
                    <th className="py-2 pr-4 font-medium">Type</th>
                    <th className="py-2 pr-4 font-medium">Détail</th>
                    <th className="py-2 pr-4 text-right font-medium">Durée</th>
                    <th className="py-2 pr-4 text-right font-medium">Énergie</th>
                    <th className="py-2 text-right font-medium">CO₂</th>
                  </tr>
                </thead>
                <tbody className="text-white">
                  {studioRecent.map((r, i) => (
                    <tr key={i} className="border-b border-ink-border/50 last:border-0">
                      <td className="py-2 pr-4 font-mono text-slate-300">
                        {new Date(r.ts * 1000).toLocaleTimeString("fr-FR")}
                      </td>
                      <td className="py-2 pr-4">
                        <span className="inline-flex items-center gap-1 text-slate-200">
                          {r.kind === "mesh" ? (
                            <Boxes size={13} className="text-brand" />
                          ) : (
                            <ImageIcon size={13} className="text-violet-400" />
                          )}
                          {r.kind === "mesh" ? "3D" : "Image"}
                        </span>
                      </td>
                      <td className="max-w-[16rem] truncate py-2 pr-4 text-slate-400" title={r.label}>
                        {r.label || "—"}
                      </td>
                      <td className="py-2 pr-4 text-right font-mono">{Math.round(r.duration_s)}s</td>
                      <td className="py-2 pr-4 text-right font-mono text-amber-400">
                        {fmtEnergy(r.energy_wh)}
                      </td>
                      <td className="py-2 text-right font-mono text-emerald-400">
                        {fmtCo2(r.co2_g)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-400">
              Aucune génération Studio 3D pour le moment. Lancez une génération
              depuis l'onglet «&nbsp;Studio 3D&nbsp;» pour suivre l'énergie et les
              émissions CO₂.
            </p>
          )}
        </div>
      </Card>

      {/* Stat grid */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          icon={Cpu}
          label="Modèles chargés"
          value={loadedModels}
          accent="brand"
          hint={vllm?.model || (studioLoaded ? "Studio 3D actif" : "Aucun modèle actif")}
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

      {/* Mobile chat via tunnel QR code */}
      <Card>
        <SectionTitle
          icon={Smartphone}
          title="Chat mobile"
          subtitle="Scannez pour ouvrir le chat sur votre téléphone via le tunnel"
          right={
            <Badge tone={chatUrl ? "green" : "slate"}>
              {chatUrl ? "● Tunnel actif" : "Tunnel inactif"}
            </Badge>
          }
        />
        {chatUrl ? (
          <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center">
            <div className="rounded-2xl bg-white p-4">
              <QRCodeSVG value={chatUrl} size={176} level="M" includeMargin={false} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-slate-300">
                Scannez ce QR code avec l'appareil photo de votre téléphone pour
                lancer le chat de test directement depuis le mobile, à travers le
                tunnel public du dashboard.
              </p>
              <a
                href={chatUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-3 inline-flex max-w-full items-center gap-2 break-all font-mono text-xs text-brand hover:underline"
              >
                <QrCode size={14} className="shrink-0" />
                {chatUrl}
              </a>
            </div>
          </div>
        ) : (
          <p className="text-sm text-slate-400">
            Aucun tunnel «&nbsp;dashboard&nbsp;» actif. Créez et hébergez le tunnel
            du dashboard depuis l'onglet «&nbsp;Tunnels&nbsp;» pour générer le QR
            code d'accès mobile.
          </p>
        )}
      </Card>

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
