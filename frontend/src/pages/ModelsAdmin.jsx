import React, { useEffect, useState } from "react";
import {
  Cpu,
  Download,
  Play,
  Square,
  Search,
  Sparkles,
  CheckCircle2,
  Loader2,
  RotateCw,
  Trash2,
} from "lucide-react";
import { Card, SectionTitle, Badge, Field, Spinner } from "../components/ui.jsx";
import { api } from "../api.js";

function chatLanguageModelsSample(status) {
  const apiUrl = status?.openai_api_url || "http://127.0.0.1:8001/v1";
  const modelName = status?.model || "your-served-model-name";
  return JSON.stringify(
    {
      "$schema": "vscode://schemas/chatLanguageModels",
      "models": [
        {
          "id": "local-vllm",
          "name": "Local vLLM",
          "provider": "openai-compatible",
          "baseURL": apiUrl,
          "apiKey": "not-required-or-your-key",
          "model": modelName,
        },
      ],
    },
    null,
    2
  );
}

function fmtBytes(n) {
  if (!n || n < 0) return "0 o";
  const u = ["o", "Ko", "Mo", "Go", "To"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${u[i]}`;
}

function DownloadProgress({ job }) {
  const pct = Math.max(0, Math.min(100, job?.progress || 0));
  return (
    <div className="mt-2">
      <div className="h-2 w-full overflow-hidden rounded-full bg-ink-900">
        <div
          className="h-full rounded-full bg-brand transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-slate-500">
        <span>{pct.toFixed(0)}%</span>
        {job?.total_bytes > 0 && (
          <span>
            {fmtBytes(job.downloaded_bytes)} / {fmtBytes(job.total_bytes)}
          </span>
        )}
      </div>
    </div>
  );
}

export default function ModelsAdmin() {
  const [curated, setCurated] = useState([]);
  const [downloaded, setDownloaded] = useState([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [hfToken, setHfToken] = useState("");
  const [jobs, setJobs] = useState({});
  const [selected, setSelected] = useState("");
  const [status, setStatus] = useState(null);
  const [params, setParams] = useState({
    dtype: "auto",
    quantization: "",
    max_model_len: 8192,
    gpu_memory_utilization: 0.9,
    tensor_parallel_size: 1,
    max_num_seqs: 256,
    trust_remote_code: true,
    enforce_eager: false,
    enable_auto_tool_choice: false,
    tool_call_parser: "",
    extra_args: "",
    runtime: "docker",  // NEW: hybrid runtime selector
  });

  const refresh = () => {
    api.curated().then((r) => setCurated(r.models)).catch(() => {});
    api.downloadedModels().then((r) => setDownloaded(r.models)).catch(() => {});
    api.modelStatus().then(setStatus).catch(() => {});
    // Seed jobs from the backend so in-progress downloads (started earlier or
    // before a page reload) show their progress on the DGX cards.
    api
      .allDownloads()
      .then((r) => {
        const byId = {};
        (r.jobs || []).forEach((j) => {
          byId[j.model_id] = j;
        });
        if (Object.keys(byId).length) {
          setJobs((p) => ({ ...byId, ...p }));
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    refresh();
    const id = setInterval(() => api.modelStatus().then(setStatus).catch(() => {}), 4000);
    return () => clearInterval(id);
  }, []);

  // Poll active download jobs
  useEffect(() => {
    const active = Object.entries(jobs).filter(
      ([, j]) => j.status === "pending" || j.status === "downloading"
    );
    if (!active.length) return;
    const id = setInterval(() => {
      active.forEach(([mid]) => {
        api.downloadStatus(mid).then((r) => {
          if (r.job) setJobs((p) => ({ ...p, [mid]: r.job }));
          if (r.job?.status === "done") refresh();
        });
      });
    }, 1500);
    return () => clearInterval(id);
  }, [jobs]);

  const doSearch = async () => {
    setSearching(true);
    try {
      const r = await api.searchModels(query);
      setResults(r.results || []);
    } finally {
      setSearching(false);
    }
  };

  const download = async (model_id) => {
    const r = await api.downloadModel(model_id, hfToken || null);
    setJobs((p) => ({ ...p, [model_id]: r.job }));
  };

  const deleteModel = async (model_id) => {
    if (!window.confirm(`Supprimer le modèle « ${model_id} » du disque ?`)) return;
    try {
      await api.deleteDownloadedModel(model_id);
    } catch {}
    if (selected === model_id) setSelected("");
    setJobs((p) => {
      const next = { ...p };
      delete next[model_id];
      return next;
    });
    refresh();
  };

  const launch = async () => {
    if (!selected) return;
    setStatus({ ...status, message: "Lancement…" });
    const body = {
      model: selected,
      ...params,
      quantization: params.quantization || null,
    };
    const r = await api.launchModel(body);
    setStatus(r.state);
    setTimeout(refresh, 1000);
  };

  const stop = async () => {
    await api.stopModel();
    setTimeout(refresh, 500);
  };

  const copy = (txt) => navigator.clipboard?.writeText(txt);

  const isDownloaded = (id) => downloaded.includes(id);

  // Merge curated models with any locally-downloaded models not already curated,
  // so the DGX section reflects what is actually present on disk.
  const curatedIds = new Set(curated.map((m) => m.id));
  const extraDownloaded = downloaded
    .filter((id) => !curatedIds.has(id))
    .map((id) => ({
      id,
      label: id,
      params: "local",
      approx_vram_gb: "?",
      quant: "—",
      note: "Modèle téléchargé localement.",
      gated: false,
      _local: true,
    }));
  const dgxModels = [...curated, ...extraDownloaded];

  return (
    <div className="space-y-6">
      <SectionTitle
        icon={Cpu}
        title="Admin · Modèles vLLM"
        subtitle="Sélection HuggingFace · téléchargement local · lancement"
        right={
          status?.running ? (
            <Badge tone="green">● {status.model} {status.ready ? "(prêt)" : "(chargement)"}</Badge>
          ) : (
            <Badge tone="slate">Aucun modèle actif</Badge>
          )
        }
      />

      {/* Curated DGX-compatible models */}
      <Card>
        <SectionTitle
          icon={Sparkles}
          title="Sélection compatible DGX Spark (GB10)"
          subtitle="Modèles validés pour la mémoire unifiée ~128 Go"
        />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {dgxModels.map((m) => {
            const job = jobs[m.id];
            const done = isDownloaded(m.id) || job?.status === "done";
            const busy = job?.status === "downloading" || job?.status === "pending";
            return (
              <div
                key={m.id}
                className={`rounded-xl border p-4 transition-all ${
                  selected === m.id
                    ? "border-brand bg-brand/5"
                    : "border-ink-border bg-ink-900/40"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-white">{m.label}</span>
                  <Badge tone={m._local ? "green" : "blue"}>{m.params}</Badge>
                </div>
                <p className="mt-1 text-xs text-slate-400">{m.note}</p>
                <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                  <span>~{m.approx_vram_gb} Go</span>·<span>{m.quant}</span>
                  {m.gated && <Badge tone="amber">gated</Badge>}
                  {done && <Badge tone="green">téléchargé</Badge>}
                </div>
                <div className="mt-3 flex gap-2">
                  {done ? (
                    <>
                      <button
                        className="btn-primary flex-1 justify-center"
                        onClick={() => setSelected(m.id)}
                      >
                        <CheckCircle2 size={16} /> Sélectionner
                      </button>
                      <button
                        className="btn-ghost justify-center text-rose-400 hover:text-rose-300"
                        title="Supprimer du disque"
                        onClick={() => deleteModel(m.id)}
                      >
                        <Trash2 size={16} />
                      </button>
                    </>
                  ) : busy ? (
                    <button className="btn-ghost flex-1 justify-center" disabled>
                      <Loader2 size={16} className="animate-spin" /> Téléchargement…
                    </button>
                  ) : job?.status === "error" ? (
                    <button
                      className="btn-ghost flex-1 justify-center"
                      onClick={() => download(m.id)}
                    >
                      <RotateCw size={16} /> Réessayer
                    </button>
                  ) : (
                    <button
                      className="btn-ghost flex-1 justify-center"
                      onClick={() => download(m.id)}
                    >
                      <Download size={16} /> Télécharger
                    </button>
                  )}
                </div>
                {busy && <DownloadProgress job={job} />}
                {job?.status === "error" && (
                  <p className="mt-2 text-xs text-rose-400">{job.message}</p>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* HF search */}
      <Card>
        <SectionTitle icon={Search} title="Recherche HuggingFace" subtitle="Modèles text-generation" />
        <div className="flex gap-2">
          <input
            className="input"
            placeholder="ex: mistral, qwen, llama…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && doSearch()}
          />
          <button className="btn-primary" onClick={doSearch} disabled={searching}>
            {searching ? <Spinner /> : <Search size={16} />} Rechercher
          </button>
        </div>
        <Field label="Token HuggingFace (modèles gated, optionnel)">
          <input
            className="input mt-1"
            type="password"
            placeholder="hf_..."
            value={hfToken}
            onChange={(e) => setHfToken(e.target.value)}
          />
        </Field>
        <div className="mt-3 max-h-72 space-y-2 overflow-y-auto">
          {results.map((r) => {
            const job = jobs[r.id];
            const busy = job?.status === "downloading" || job?.status === "pending";
            return (
              <div
                key={r.id}
                className="rounded-lg border border-ink-border bg-ink-900/40 px-3 py-2"
              >
                <div className="flex items-center justify-between">
                  <div className="min-w-0">
                    <div className="truncate font-mono text-sm text-white">{r.id}</div>
                    <div className="text-xs text-slate-500">
                      ↓ {r.downloads?.toLocaleString?.() || 0} · ♥ {r.likes || 0}
                      {r.gated && " · gated"}
                    </div>
                  </div>
                  {isDownloaded(r.id) || job?.status === "done" ? (
                    <button className="btn-primary" onClick={() => setSelected(r.id)}>
                      <CheckCircle2 size={16} /> Choisir
                    </button>
                  ) : job?.status === "error" ? (
                    <button className="btn-ghost" onClick={() => download(r.id)}>
                      <RotateCw size={16} /> Réessayer
                    </button>
                  ) : (
                    <button
                      className="btn-ghost"
                      onClick={() => download(r.id)}
                      disabled={busy}
                    >
                      {busy ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Download size={16} />
                      )}
                    </button>
                  )}
                </div>
                {busy && <DownloadProgress job={job} />}
                {job?.status === "error" && (
                  <p className="mt-1 text-xs text-rose-400">{job.message}</p>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* Launch params */}
      <Card>
        <SectionTitle
          icon={Play}
          title="Lancement vLLM"
          subtitle={selected ? `Modèle: ${selected}` : "Sélectionnez d'abord un modèle"}
        />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          <Field label="dtype">
            <select
              className="input"
              value={params.dtype}
              onChange={(e) => setParams({ ...params, dtype: e.target.value })}
            >
              {["auto", "bfloat16", "float16", "half"].map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </Field>
          <Field label="quantization">
            <select
              className="input"
              value={params.quantization}
              onChange={(e) => setParams({ ...params, quantization: e.target.value })}
            >
              <option value="">aucune</option>
              {["fp8", "awq", "gptq"].map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </Field>
          <Field label="max_model_len">
            <input
              className="input"
              type="number"
              value={params.max_model_len}
              onChange={(e) => setParams({ ...params, max_model_len: +e.target.value })}
            />
          </Field>
          <Field label="gpu_memory_utilization">
            <input
              className="input"
              type="number"
              step="0.05"
              min="0.1"
              max="1"
              value={params.gpu_memory_utilization}
              onChange={(e) =>
                setParams({ ...params, gpu_memory_utilization: +e.target.value })
              }
            />
          </Field>
          <Field label="tensor_parallel_size">
            <input
              className="input"
              type="number"
              value={params.tensor_parallel_size}
              onChange={(e) =>
                setParams({ ...params, tensor_parallel_size: +e.target.value })
              }
            />
          </Field>
          <Field label="max_num_seqs">
            <input
              className="input"
              type="number"
              value={params.max_num_seqs}
              onChange={(e) => setParams({ ...params, max_num_seqs: +e.target.value })}
            />
          </Field>
          <Field label="extra_args (CLI vLLM)">
            <input
              className="input"
              placeholder="--rope-scaling ..."
              value={params.extra_args}
              onChange={(e) => setParams({ ...params, extra_args: e.target.value })}
            />
          </Field>
          <Field label="tool_call_parser">
            <input
              className="input"
              placeholder="auto (laisser vide)"
              value={params.tool_call_parser}
              onChange={(e) => setParams({ ...params, tool_call_parser: e.target.value })}
            />
          </Field>
          <Field label="Runtime">
            <select
              className="input"
              value={params.runtime}
              onChange={(e) => setParams({ ...params, runtime: e.target.value })}
            >
              <option value="docker">Docker (conteneur)</option>
              <option value="native">CLI natif (subprocess)</option>
            </select>
          </Field>
          <label className="flex items-center gap-2 self-end text-sm text-slate-300">
            <input
              type="checkbox"
              checked={params.trust_remote_code}
              onChange={(e) =>
                setParams({ ...params, trust_remote_code: e.target.checked })
              }
            />
            trust_remote_code
          </label>
          <label className="flex items-center gap-2 self-end text-sm text-slate-300">
            <input
              type="checkbox"
              checked={params.enforce_eager}
              onChange={(e) => setParams({ ...params, enforce_eager: e.target.checked })}
            />
            enforce_eager
          </label>
          <label className="flex items-center gap-2 self-end text-sm text-slate-300">
            <input
              type="checkbox"
              checked={params.enable_auto_tool_choice}
              onChange={(e) =>
                setParams({ ...params, enable_auto_tool_choice: e.target.checked })
              }
            />
            enable_auto_tool_choice
          </label>
        </div>

        {params.enable_auto_tool_choice && (
          <p className="mt-2 text-xs text-slate-400">
            Tool calling activé (compatible GitHub Copilot). Si{" "}
            <code className="text-brand">tool_call_parser</code> est vide, il est
            choisi automatiquement selon le modèle (phi4_mini_json, llama3_json,
            hermes, mistral…).
          </p>
        )}

        <div className="mt-4 flex items-center gap-3">
          <button className="btn-primary" onClick={launch} disabled={!selected}>
            <Play size={16} /> Lancer le modèle
          </button>
          <button className="btn-ghost" onClick={stop} disabled={!status?.running}>
            <Square size={16} /> Arrêter
          </button>
          {status?.message && (
            <span className="text-sm text-slate-400">{status.message}</span>
          )}
        </div>

        {status?.exposed_url && (
          <div className="mt-4 rounded-xl border border-ink-border bg-ink-900/40 p-3">
            <p className="label">URL du serveur vLLM exposé</p>
            <a
              href={status.exposed_url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 block truncate font-mono text-sm text-brand hover:underline"
            >
              {status.exposed_url}
            </a>
            <p className="mt-2 text-xs text-slate-500">API OpenAI-compatible</p>
            <a
              href={status.openai_api_url}
              target="_blank"
              rel="noreferrer"
              className="block truncate font-mono text-xs text-slate-300 hover:underline"
            >
              {status.openai_api_url}
            </a>

            <div className="mt-4 border-t border-ink-border pt-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="label">Sample `chatLanguageModels.json` (VS Code)</p>
                <button
                  className="btn-ghost px-2 py-1"
                  onClick={() => copy(chatLanguageModelsSample(status))}
                >
                  Copier
                </button>
              </div>
              <pre className="max-h-52 overflow-auto rounded-lg bg-ink-900 p-3 text-xs text-slate-300">
                {chatLanguageModelsSample(status)}
              </pre>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
