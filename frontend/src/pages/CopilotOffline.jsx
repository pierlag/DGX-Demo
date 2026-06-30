import React, { useEffect, useRef, useState } from "react";
import {
  Bot,
  Search,
  Download,
  Play,
  Trash2,
  RefreshCw,
  Power,
  PowerOff,
  Square,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Copy,
  Check,
  Terminal,
  Code2,
  ChevronDown,
  ChevronRight,
  Star,
  FlaskConical,
} from "lucide-react";
import { Card, SectionTitle, Badge, Spinner, Field } from "../components/ui.jsx";
import { api } from "../api.js";

function CopyButton({ text, label = "Copier" }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="btn-ghost text-xs"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          /* clipboard unavailable */
        }
      }}
    >
      {done ? <Check size={14} /> : <Copy size={14} />}
      {done ? "Copié" : label}
    </button>
  );
}

function StatusPill({ ok, label, hint, tone }) {
  // tone overrides the ok->green/red mapping; "neutral" renders an informative
  // grey dot for optional/non-blocking checks.
  const dotTone = tone || (ok ? "ok" : "error");
  const dotClass =
    { ok: "bg-brand", error: "bg-rose-500", neutral: "bg-slate-500" }[dotTone] ||
    "bg-rose-500";
  return (
    <div className="flex items-center gap-2 rounded-xl border border-ink-border px-3 py-2">
      <span className={`h-2.5 w-2.5 rounded-full ${dotClass}`} />
      <div className="min-w-0">
        <div className="text-sm font-semibold text-slate-100">{label}</div>
        {hint && <div className="truncate text-xs text-slate-500">{hint}</div>}
      </div>
    </div>
  );
}

const CHECK_ICON = {
  pass: <CheckCircle2 size={18} className="text-brand" />,
  warn: <AlertTriangle size={18} className="text-amber-400" />,
  fail: <XCircle size={18} className="text-rose-400" />,
};

function bytes(n) {
  if (!n) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)} ${u[i]}`;
}

const CAP_TONE = { tools: "green", vision: "blue", thinking: "amber", insert: "slate" };

function CapabilityPanel({ info }) {
  const [showTpl, setShowTpl] = useState(false);
  if (info === "loading") {
    return (
      <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
        <Spinner size={14} /> Lecture des capacités…
      </div>
    );
  }
  if (!info || !info.ok) {
    return (
      <div className="mt-2 text-xs text-rose-300">
        Capacités indisponibles{info && info.message ? ` : ${info.message}` : ""}.
      </div>
    );
  }
  const caps = info.capabilities || [];
  return (
    <div className="mt-2 rounded-xl border border-ink-border bg-black/20 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-slate-400">Capacités&nbsp;:</span>
        {caps.length === 0 && <span className="text-xs text-slate-500">aucune annoncée</span>}
        {caps.map((c) => (
          <Badge key={c} tone={CAP_TONE[c] || "slate"}>
            {c}
          </Badge>
        ))}
      </div>
      <p className="mt-2 text-xs text-slate-400">
        {info.supports_tools ? (
          <>
            Annonce <span className="text-brand">tools</span> : entraîné pour les appels d'outils
            structurés. La compatibilité réelle dépend de la validité du schéma — lancez les tests
            ci-dessous pour confirmer.
          </>
        ) : (
          <>
            N'annonce pas <span className="text-amber-400">tools</span> : utilisable en chat, mais ne
            peut pas piloter le CLI Copilot agentique.
          </>
        )}
      </p>
      {info.template && (
        <div className="mt-2">
          <button
            type="button"
            className="btn-ghost text-xs"
            onClick={() => setShowTpl((v) => !v)}
          >
            {showTpl ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Template de chat
            (format des outils attendu par le modèle)
          </button>
          {showTpl && (
            <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/40 p-3 text-[11px] leading-relaxed text-slate-300">
              {info.template}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export default function CopilotOffline() {
  const [status, setStatus] = useState(null); // ollama status
  const [cli, setCli] = useState(null); // copilot/vscode tooling
  const [localModels, setLocalModels] = useState([]);
  const [activeModel, setActiveModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingName, setLoadingName] = useState(""); // model being loaded/stopped
  const [error, setError] = useState(null);

  // Search
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [expanded, setExpanded] = useState({}); // name -> tags[]

  // Pull
  const [pullName, setPullName] = useState("");
  const [pull, setPull] = useState(null); // {model, status, percent}

  // Tests + launch
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [launch, setLaunch] = useState(null);

  // Per-model capabilities (lazy /api/ollama/show)
  const [caps, setCaps] = useState({}); // name -> info | "loading"
  const [capOpen, setCapOpen] = useState({}); // name -> bool (template expander)

  const inFlight = useRef(false);
  const pullAbort = useRef(null);

  const refresh = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const [s, c] = await Promise.all([api.ollamaStatus(), api.copilotStatus()]);
      setStatus(s);
      setCli(c);
      const models = s.models || [];
      setLocalModels(models);
      setActiveModel((prev) => prev || (models[0] && models[0].name) || "");
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      inFlight.current = false;
    }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  // Load launch helpers whenever the active model changes.
  useEffect(() => {
    if (!activeModel) {
      setLaunch(null);
      return;
    }
    api.copilotLaunch(activeModel).then(setLaunch).catch(() => setLaunch(null));
  }, [activeModel]);

  const containerAction = async (start) => {
    setBusy(true);
    setError(null);
    try {
      const res = start ? await api.ollamaStartContainer() : await api.ollamaStopContainer();
      if (!res.ok) setError(res.message || "Action conteneur échouée");
      setTimeout(refresh, 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const doSearch = async (e) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const { results } = await api.ollamaSearch(query.trim());
      setResults(results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setSearching(false);
    }
  };

  const toggleTags = async (name) => {
    if (expanded[name]) {
      setExpanded((e) => ({ ...e, [name]: undefined }));
      return;
    }
    setExpanded((e) => ({ ...e, [name]: "loading" }));
    try {
      const { tags } = await api.ollamaTags(name);
      setExpanded((e) => ({ ...e, [name]: tags || [] }));
    } catch {
      setExpanded((e) => ({ ...e, [name]: [] }));
    }
  };

  const doPull = async (model) => {
    if (!model || pull) return;
    setError(null);
    setPull({ model, status: "starting", percent: 0 });
    const ctrl = new AbortController();
    pullAbort.current = ctrl;
    try {
      const resp = await api.ollamaPull(model, ctrl.signal);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          let obj;
          try {
            obj = JSON.parse(line);
          } catch {
            continue;
          }
          if (obj.error) {
            setError(`Pull: ${obj.error}`);
            continue;
          }
          const percent =
            obj.total > 0 ? Math.round((100 * (obj.completed || 0)) / obj.total) : pull?.percent || 0;
          setPull({ model, status: obj.status || "pulling", percent });
        }
      }
      setPull({ model, status: "success", percent: 100 });
      setTimeout(() => setPull(null), 1500);
      refresh();
    } catch (err) {
      if (err.name === "AbortError") {
        setPull({ model, status: "annulé", percent: 0 });
        setTimeout(() => setPull(null), 1500);
      } else {
        setError(err.message);
        setPull(null);
      }
    } finally {
      pullAbort.current = null;
    }
  };

  const cancelPull = () => {
    if (pullAbort.current) pullAbort.current.abort();
  };

  const doLoad = async (name) => {
    setBusy(true);
    setLoadingName(name);
    setError(null);
    try {
      const res = await api.ollamaLoad(name);
      if (!res.ok) setError(res.message || "Chargement échoué");
      setActiveModel(name);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingName("");
      setBusy(false);
    }
  };

  const doStop = async (name) => {
    setBusy(true);
    setLoadingName(name);
    setError(null);
    try {
      const res = await api.ollamaStop(name);
      if (!res.ok) setError(res.message || "Arrêt échoué");
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingName("");
      setBusy(false);
    }
  };

  const doDelete = async (name) => {
    setBusy(true);
    setError(null);
    try {
      await api.ollamaDelete(name);
      if (activeModel === name) setActiveModel("");
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  // Toggle the capability panel for a model, lazily fetching /api/ollama/show.
  const toggleCaps = async (name) => {
    const open = !capOpen[name];
    setCapOpen((p) => ({ ...p, [name]: open }));
    if (open && !caps[name]) {
      setCaps((p) => ({ ...p, [name]: "loading" }));
      try {
        const info = await api.ollamaShow(name);
        setCaps((p) => ({ ...p, [name]: info }));
      } catch (err) {
        setCaps((p) => ({ ...p, [name]: { ok: false, message: err.message } }));
      }
    }
  };

  const runTests = async () => {
    setTesting(true);
    setTestResult(null);
    setError(null);
    try {
      const res = await api.copilotTest(activeModel);
      setTestResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setTesting(false);
    }
  };

  const endpointUp = status?.endpoint_up;
  const browserUrl = status?.browser_openai_url || status?.openai_url || "";

  return (
    <div className="space-y-6">
      <SectionTitle
        icon={Bot}
        title="Copilot hors-ligne (Ollama)"
        subtitle="Recherche, téléchargement et exécution de modèles Ollama + tests d'intégration GitHub Copilot CLI / VS Code chat en mode airgap."
        right={
          <button className="btn-ghost" onClick={refresh} disabled={inFlight.current}>
            <RefreshCw size={16} /> Rafraîchir
          </button>
        }
      />

      {error && (
        <div className="card flex items-start gap-2 border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span className="break-words">{error}</span>
        </div>
      )}

      {/* Status row */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatusPill
          ok={status?.container_running}
          label="Conteneur Ollama"
          hint={status?.container_running ? "running" : "stopped"}
        />
        <StatusPill
          ok={endpointUp}
          label="Endpoint OpenAI"
          hint={endpointUp ? `v${status?.version}` : "injoignable"}
        />
        <StatusPill
          ok={cli?.copilot_cli?.installed}
          label="Copilot CLI"
          hint={cli?.copilot_cli?.installed ? cli.copilot_cli.version || "installé" : "non installé"}
        />
        <StatusPill
          ok={cli?.vscode_copilot_chat || cli?.vscode_ollama_configured}
          tone={
            cli?.vscode_copilot_chat || cli?.vscode_ollama_configured
              ? "ok"
              : "neutral"
          }
          label="VS Code · Copilot Chat"
          hint={
            cli?.vscode_ollama_configured
              ? "Ollama configuré dans Copilot"
              : cli?.vscode_copilot_chat
              ? "extension présente"
              : cli?.vscode?.installed
              ? "Ollama non configuré (optionnel)"
              : "poste client (optionnel)"
          }
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          className="btn-primary"
          onClick={() => containerAction(true)}
          disabled={busy || (status?.container_running && endpointUp)}
        >
          <Power size={16} />{" "}
          {status?.container_running && !endpointUp ? "Réparer Ollama" : "Démarrer Ollama"}
        </button>
        <button className="btn-ghost" onClick={() => containerAction(false)} disabled={busy || !status?.container_running}>
          <PowerOff size={16} /> Arrêter
        </button>
        {endpointUp && (
          <span className="rounded-lg border border-ink-border px-3 py-1.5 font-mono text-xs text-slate-400">
            {browserUrl}
          </span>
        )}
      </div>

      {/* Search + pull */}
      <Card>
        <SectionTitle icon={Search} title="Rechercher & télécharger des modèles" subtitle="Recherche dans la bibliothèque Ollama (ollama.com)." />
        <form onSubmit={doSearch} className="flex flex-wrap gap-2">
          <input
            className="input flex-1 min-w-[200px]"
            placeholder="ex. llama, qwen, mistral, codellama…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="btn-primary" type="submit" disabled={searching}>
            {searching ? <Spinner size={16} /> : <Search size={16} />} Rechercher
          </button>
        </form>

        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Field label="Télécharger par nom/tag">
            <input
              className="input w-72"
              placeholder="ex. llama3.2:3b"
              value={pullName}
              onChange={(e) => setPullName(e.target.value)}
            />
          </Field>
          <button className="btn-ghost" onClick={() => doPull(pullName.trim())} disabled={!pullName.trim() || !!pull}>
            <Download size={16} /> Télécharger
          </button>
        </div>

        {pull && (
          <div className="mt-3 rounded-xl border border-ink-border p-3">
            <div className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-400">
              <span className="font-mono text-slate-200">{pull.model}</span>
              <div className="flex items-center gap-2">
                <span>{pull.status} · {pull.percent}%</span>
                {pull.status !== "success" && pull.status !== "annulé" && (
                  <button className="btn-ghost text-xs text-rose-300" onClick={cancelPull}>
                    <XCircle size={14} /> Annuler
                  </button>
                )}
              </div>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-ink-900">
              <div className="h-full bg-brand transition-all" style={{ width: `${pull.percent}%` }} />
            </div>
          </div>
        )}

        {results.length > 0 && (
          <div className="mt-4 space-y-2">
            {results.map((r) => (
              <div key={r.name} className="rounded-xl border border-ink-border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-100">{r.name}</span>
                      {r.pulls && <Badge tone="slate">{r.pulls} pulls</Badge>}
                      {(r.capabilities || []).map((c) => (
                        <Badge key={c} tone="blue">{c}</Badge>
                      ))}
                    </div>
                    {r.description && <p className="mt-1 text-sm text-slate-400">{r.description}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    <button className="btn-ghost text-xs" onClick={() => toggleTags(r.name)}>
                      {expanded[r.name] ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Tags
                    </button>
                    <button className="btn-primary text-xs" onClick={() => doPull(r.name)} disabled={!!pull}>
                      <Download size={14} /> Pull
                    </button>
                  </div>
                </div>
                {expanded[r.name] === "loading" && (
                  <div className="mt-2 text-xs text-slate-500"><Spinner size={12} /> Chargement des tags…</div>
                )}
                {Array.isArray(expanded[r.name]) && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {expanded[r.name].length === 0 && <span className="text-xs text-slate-500">Aucun tag trouvé.</span>}
                    {expanded[r.name].map((t) => (
                      <button
                        key={t.full}
                        className="rounded-lg border border-ink-border px-2 py-1 font-mono text-xs text-slate-300 hover:border-brand hover:text-brand"
                        onClick={() => doPull(t.full)}
                        disabled={!!pull}
                        title={`Pull ${t.full}`}
                      >
                        {t.tag}{t.size ? ` · ${t.size}` : ""}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Local models */}
      <Card>
        <SectionTitle
          icon={Download}
          title="Modèles locaux"
          subtitle="Le badge indique si le modèle est chargé en mémoire (en cours) ou arrêté. « Exécuter » le charge et le définit comme actif ; « Arrêter » libère la VRAM."
        />
        {localModels.length === 0 ? (
          <p className="text-sm text-slate-500">Aucun modèle local. Téléchargez-en un ci-dessus.</p>
        ) : (
          <div className="space-y-2">
            {localModels.map((m) => {
              const active = m.name === activeModel;
              const run = (status?.loaded || []).find((x) => x.name === m.name);
              const running = !!run;
              const pending = loadingName === m.name;
              return (
                <div
                  key={m.name}
                  className={`rounded-xl border p-3 ${
                    active ? "border-brand/60 bg-brand/5" : "border-ink-border"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      {active && <Star size={14} className="text-brand" fill="currentColor" />}
                      <span className="font-mono text-sm text-slate-100">{m.name}</span>
                      {m.parameter_size && <Badge tone="slate">{m.parameter_size}</Badge>}
                      {m.quantization_level && <Badge tone="slate">{m.quantization_level}</Badge>}
                      <span className="text-xs text-slate-500">{bytes(m.size)}</span>
                      {pending ? (
                        <Badge tone="amber">
                          <Spinner size={12} /> {running ? "Arrêt…" : "Chargement…"}
                        </Badge>
                      ) : running ? (
                        <Badge tone="green">
                          <span className="mr-1 inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
                          En cours · {bytes(run.size_vram)} VRAM
                        </Badge>
                      ) : (
                        <Badge tone="slate">Arrêté</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button className="btn-ghost text-xs" onClick={() => toggleCaps(m.name)}>
                        {capOpen[m.name] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}{" "}
                        Capacités
                      </button>
                      {!active && (
                        <button className="btn-ghost text-xs" onClick={() => setActiveModel(m.name)}>
                          <Star size={14} /> Définir actif
                        </button>
                      )}
                      <button
                        className="btn-ghost text-xs"
                        onClick={() => doLoad(m.name)}
                        disabled={busy}
                        title={running ? "Recharger / prolonger en mémoire" : "Charger en mémoire"}
                      >
                        {pending && !running ? <Spinner size={14} /> : <Play size={14} />}{" "}
                        {running ? "Recharger" : "Exécuter"}
                      </button>
                      {running && (
                        <button
                          className="btn-ghost text-xs text-amber-300"
                          onClick={() => doStop(m.name)}
                          disabled={busy}
                        >
                          {pending ? <Spinner size={14} /> : <Square size={14} />} Arrêter
                        </button>
                      )}
                      <button className="btn-ghost text-xs text-rose-300" onClick={() => doDelete(m.name)} disabled={busy}>
                        <Trash2 size={14} /> Supprimer
                      </button>
                    </div>
                  </div>
                  {capOpen[m.name] && <CapabilityPanel info={caps[m.name]} />}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* Tests */}
      <Card>
        <SectionTitle
          icon={FlaskConical}
          title="Tests d'intégration hors-ligne"
          subtitle="Vérifie que le modèle actif satisfait les exigences du CLI Copilot agentique : /v1/models, chat, streaming (finish_reason), tool calls structurés."
          right={
            <button className="btn-primary" onClick={runTests} disabled={testing || !activeModel}>
              {testing ? <Spinner size={16} /> : <FlaskConical size={16} />} Lancer les tests
            </button>
          }
        />
        {!activeModel && <p className="text-sm text-slate-500">Sélectionnez un modèle actif ci-dessus.</p>}
        {activeModel && (
          <p className="mb-3 text-sm text-slate-400">
            Modèle testé : <span className="font-mono text-slate-200">{activeModel}</span>
          </p>
        )}
        {testResult && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Badge tone={testResult.ok ? "green" : "red"}>{testResult.ok ? "Tous réussis" : "Échecs détectés"}</Badge>
              <span className="text-xs text-slate-500">{testResult.base_url}</span>
            </div>
            {testResult.checks.map((c) => (
              <div key={c.name} className="flex items-start gap-3 rounded-xl border border-ink-border p-3">
                <div className="mt-0.5">{CHECK_ICON[c.status] || CHECK_ICON.fail}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold capitalize text-slate-100">{c.name}</span>
                    <span className="text-xs text-slate-500">{c.duration_ms} ms</span>
                  </div>
                  <p className="text-sm text-slate-400">{c.detail}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Launch helpers */}
      {launch && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <SectionTitle icon={Terminal} title="Lancer le Copilot CLI" subtitle="Inférence 100 % locale, aucune donnée ne sort de la machine." />
            <div className="relative">
              <pre className="overflow-x-auto rounded-xl border border-ink-border bg-ink-900/60 p-3 text-xs text-slate-200">
{launch.cli_command}
              </pre>
              <div className="absolute right-2 top-2">
                <CopyButton text={launch.cli_command} />
              </div>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Ou via le script : <span className="font-mono text-slate-300">{launch.script}</span>
            </p>
          </Card>

          <Card>
            <SectionTitle icon={Code2} title="VS Code chat (hors-ligne)" subtitle="Pointez le fournisseur Ollama de Copilot Chat vers l'endpoint local." />
            <p className="mb-2 text-sm text-slate-400">{launch.vscode_settings?._note}</p>
            <div className="relative">
              <pre className="overflow-x-auto rounded-xl border border-ink-border bg-ink-900/60 p-3 text-xs text-slate-200">
{JSON.stringify(
  Object.fromEntries(Object.entries(launch.vscode_settings || {}).filter(([k]) => k !== "_note")),
  null,
  2
)}
              </pre>
              <div className="absolute right-2 top-2">
                <CopyButton
                  text={JSON.stringify(
                    Object.fromEntries(Object.entries(launch.vscode_settings || {}).filter(([k]) => k !== "_note")),
                    null,
                    2
                  )}
                />
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
