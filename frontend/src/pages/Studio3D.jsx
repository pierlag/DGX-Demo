import React, { useEffect, useRef, useState } from "react";
import {
  Boxes,
  Sparkles,
  Image as ImageIcon,
  Upload,
  Wand2,
  Download,
  RotateCw,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  MousePointer2,
  Server,
  Hammer,
  Play,
  Square,
  Cpu,
  Trash2,
  Eye,
  Clock,
  History,
  Settings2,
  Dices,
  ChevronDown,
} from "lucide-react";
import { Card, SectionTitle, Badge, Field, Spinner } from "../components/ui.jsx";
import Viewer3D from "../components/Viewer3D.jsx";
import { api } from "../api.js";

function ModelStatusRow({ title, st, onLoad }) {
  const tone = st?.available ? (st?.loaded ? "green" : "amber") : "red";
  const label = !st?.available
    ? "Indisponible"
    : st?.loaded
    ? "Chargé"
    : st?.loading
    ? "Chargement…"
    : "Prêt à charger";
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-ink-border bg-ink-900/40 px-3 py-2.5">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white">{title}</span>
          <Badge tone={tone}>{label}</Badge>
          {st?.downloaded ? (
            <Badge tone="blue">Téléchargé</Badge>
          ) : (
            <Badge tone="slate">Non téléchargé</Badge>
          )}
        </div>
        <p className="mt-0.5 truncate text-xs text-slate-500">{st?.model}</p>
        {st?.message && <p className="mt-0.5 text-xs text-slate-400">{st.message}</p>}
      </div>
      <button
        className="btn-secondary shrink-0"
        onClick={onLoad}
        disabled={!st?.available || st?.loaded || st?.loading}
      >
        {st?.loading ? <Spinner size={14} /> : <RotateCw size={14} />} Charger
      </button>
    </div>
  );
}

function TrellisPanel({ st, onRefresh }) {
  const runtime = st?.runtime || "native";
  const cont = st?.container;
  const tone = st?.available ? (st?.loaded ? "green" : "amber") : "red";
  const label = st?.loaded ? "Prêt" : st?.available ? "Pas prêt" : "Indisponible";

  const setRuntime = async (r) => {
    await api.studioSetTrellisRuntime(r);
    onRefresh();
  };

  return (
    <div className="rounded-xl border border-ink-border bg-ink-900/40 px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white">TRELLIS.2 · Image → 3D</span>
          <Badge tone={tone}>{label}</Badge>
          {st?.downloaded ? (
            <Badge tone="blue">Téléchargé</Badge>
          ) : (
            <Badge tone="slate">Non téléchargé</Badge>
          )}
        </div>
        {/* Runtime selector */}
        <div className="flex overflow-hidden rounded-lg border border-ink-border text-xs">
          <button
            className={`flex items-center gap-1 px-2.5 py-1.5 ${
              runtime === "native" ? "bg-brand/20 text-brand" : "text-slate-400"
            }`}
            onClick={() => setRuntime("native")}
          >
            <Cpu size={13} /> Natif
          </button>
          <button
            className={`flex items-center gap-1 px-2.5 py-1.5 ${
              runtime === "docker" ? "bg-brand/20 text-brand" : "text-slate-400"
            }`}
            onClick={() => setRuntime("docker")}
          >
            <Server size={13} /> Docker
          </button>
        </div>
      </div>
      <p className="mt-1 truncate text-xs text-slate-500">{st?.model}</p>
      {st?.message && <p className="mt-0.5 text-xs text-slate-400">{st.message}</p>}

      {runtime === "native" ? (
        <button
          className="btn-secondary mt-2"
          onClick={() => api.studioLoadTrellis().then(onRefresh)}
          disabled={!st?.available || st?.loaded || st?.loading}
        >
          {st?.loading ? <Spinner size={14} /> : <RotateCw size={14} />} Charger
        </button>
      ) : (
        <div className="mt-2 space-y-2">
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
            <Badge tone={cont?.image_built ? "green" : "slate"}>
              Image {cont?.image_built ? "construite" : "absente"}
            </Badge>
            <Badge tone={cont?.running ? "green" : "slate"}>
              Conteneur {cont?.running ? "démarré" : "arrêté"}
            </Badge>
            <span className="truncate">{cont?.base_image}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="btn-secondary"
              onClick={() => api.studioTrellisBuild().then(onRefresh)}
              disabled={!cont?.docker || cont?.build?.building}
            >
              {cont?.build?.building ? <Spinner size={14} /> : <Hammer size={14} />}
              Construire l'image
            </button>
            <button
              className="btn-secondary"
              onClick={() => api.studioTrellisStart().then(onRefresh)}
              disabled={!cont?.image_built || cont?.running}
            >
              <Play size={14} /> Démarrer
            </button>
            <button
              className="btn-secondary"
              onClick={() => api.studioTrellisStop().then(onRefresh)}
              disabled={!cont?.running}
            >
              <Square size={14} /> Arrêter
            </button>
          </div>
          {cont?.build?.log_tail && (
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-black/50 p-2 text-[10px] leading-tight text-slate-400">
              {cont.build.log_tail}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function NumberRange({ label, hint, value, min, max, step, onChange }) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-300">{label}</span>
        <span className="text-xs tabular-nums text-brand">{value}</span>
      </div>
      <input
        type="range"
        className="mt-1 w-full accent-brand"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {hint && <p className="mt-0.5 text-[10px] text-slate-500">{hint}</p>}
    </div>
  );
}

function SelectField({ label, value, options, onChange }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-300">{label}</span>
      <select
        className="input mt-1 w-full"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function ToggleRow({ label, hint, checked, onChange }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-3">
      <span>
        <span className="text-xs font-medium text-slate-300">{label}</span>
        {hint && <span className="block text-[10px] text-slate-500">{hint}</span>}
      </span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors ${
          checked ? "bg-brand" : "bg-ink-700"
        }`}
      >
        <span
          className={`block h-4 w-4 translate-y-0.5 rounded-full bg-white transition-transform ${
            checked ? "translate-x-4" : "translate-x-0.5"
          }`}
        />
      </button>
    </label>
  );
}

function SeedField({ label, value, onChange, randomMax = 2147483647, allowEmpty = false }) {
  return (
    <div>
      <span className="text-xs font-medium text-slate-300">{label}</span>
      <div className="mt-1 flex gap-1.5">
        <input
          type="number"
          className="input w-full"
          placeholder={allowEmpty ? "aléatoire" : ""}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="button"
          className="btn-secondary shrink-0 px-2.5"
          title="Aléatoire"
          onClick={() => onChange(String(Math.floor(Math.random() * randomMax)))}
        >
          <Dices size={14} />
        </button>
      </div>
    </div>
  );
}

export default function Studio3D() {
  const [status, setStatus] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [imageName, setImageName] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [glbUrl, setGlbUrl] = useState("");
  const [imgBusy, setImgBusy] = useState(false);
  const [meshBusy, setMeshBusy] = useState(false);
  const [meshProgress, setMeshProgress] = useState(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const fileRef = useRef(null);
  const pollers = useRef([]);

  // Generation parameters
  const [imgParams, setImgParams] = useState({
    steps: 1,
    guidance: 0.0,
    width: 512,
    height: 512,
    negative_prompt: "",
    seed: "",
  });
  const [meshParams, setMeshParams] = useState({
    seed: 42,
    pipeline_type: "1024_cascade",
    preprocess_image: true,
    geometry_steps: 12,
    geometry_guidance: 7.5,
    texture_steps: 12,
    texture_guidance: 1.0,
    texture_size: 2048,
  });
  const [showImgParams, setShowImgParams] = useState(false);
  const [showMeshParams, setShowMeshParams] = useState(false);

  const setImg = (k, v) => setImgParams((p) => ({ ...p, [k]: v }));
  const setMesh = (k, v) => setMeshParams((p) => ({ ...p, [k]: v }));

  const refreshStatus = () =>
    api.studioStatus().then(setStatus).catch(() => {});

  const refreshHistory = () =>
    api.studioHistory().then((r) => setHistory(r.items || [])).catch(() => {});

  const pollJob = (jobId, onDone) => {
    const id = setInterval(async () => {
      try {
        const { job } = await api.studioJob(jobId);
        if (!job) return;
        if (job.kind === "mesh") setMeshProgress(job);
        if (job.status === "done") {
          clearInterval(id);
          onDone(job);
        } else if (job.status === "error") {
          clearInterval(id);
          setError(job.message || "Échec de la tâche.");
          setImgBusy(false);
          setMeshBusy(false);
          setMeshProgress(null);
        }
      } catch {
        /* keep polling */
      }
    }, 1500);
    pollers.current.push(id);
  };

  const attachImageJob = (jobId) => {
    setImgBusy(true);
    setGlbUrl("");
    pollJob(jobId, (done) => {
      setImageName(done.result_name);
      setImageUrl(done.result_url + `?t=${Date.now()}`);
      setImgBusy(false);
      refreshHistory();
    });
  };

  const attachMeshJob = (jobId) => {
    setMeshBusy(true);
    pollJob(jobId, (done) => {
      setGlbUrl(done.result_url + `?t=${Date.now()}`);
      setMeshBusy(false);
      setMeshProgress(null);
      refreshHistory();
    });
  };

  useEffect(() => {
    refreshStatus();
    refreshHistory();
    // Resume any job still running on the backend (e.g. after navigating away).
    api
      .studioJobs()
      .then(({ jobs }) => {
        const running = (jobs || []).filter(
          (j) => j.status === "running" || j.status === "pending"
        );
        const mesh = running.find((j) => j.kind === "mesh");
        const img = running.find((j) => j.kind === "image");
        if (mesh) {
          setMeshProgress(mesh);
          attachMeshJob(mesh.id);
        }
        if (img) attachImageJob(img.id);
      })
      .catch(() => {});
    const id = setInterval(refreshStatus, 4000);
    return () => {
      clearInterval(id);
      pollers.current.forEach(clearInterval);
      pollers.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const genImage = async () => {
    if (!prompt.trim() || imgBusy) return;
    setError("");
    setGlbUrl("");
    try {
      const { ok, job, message } = await api.studioTextToImage(prompt.trim(), {
        seed: imgParams.seed === "" ? null : Number(imgParams.seed),
        steps: Number(imgParams.steps),
        guidance: Number(imgParams.guidance),
        width: Number(imgParams.width),
        height: Number(imgParams.height),
        negative_prompt: imgParams.negative_prompt,
      });
      if (!ok) throw new Error(message || "Refusé.");
      attachImageJob(job.id);
    } catch (e) {
      setError(e.message);
      setImgBusy(false);
    }
  };

  const onUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setError("");
    setGlbUrl("");
    const fd = new FormData();
    fd.append("file", f);
    try {
      const { ok, image_name, image_url, message } = await api.studioUpload(fd);
      if (!ok) throw new Error(message || "Échec de l'envoi.");
      setImageName(image_name);
      setImageUrl(image_url + `?t=${Date.now()}`);
      refreshHistory();
    } catch (err) {
      setError(err.message);
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const genMesh = async () => {
    if (!imageName || meshBusy) return;
    setError("");
    setMeshProgress(null);
    setGlbUrl("");
    try {
      const { ok, job, message } = await api.studioGenerate(imageName, {
        seed: Number(meshParams.seed),
        pipeline_type: meshParams.pipeline_type,
        preprocess_image: meshParams.preprocess_image,
        geometry_steps: Number(meshParams.geometry_steps),
        geometry_guidance: Number(meshParams.geometry_guidance),
        texture_steps: Number(meshParams.texture_steps),
        texture_guidance: Number(meshParams.texture_guidance),
        texture_size: Number(meshParams.texture_size),
      });
      if (!ok) throw new Error(message || "Refusé.");
      attachMeshJob(job.id);
    } catch (e) {
      setError(e.message);
      setMeshBusy(false);
      setMeshProgress(null);
    }
  };

  const viewHistoryItem = (item) => {
    setError("");
    const url = item.url + `?t=${Date.now()}`;
    if (item.kind === "mesh") {
      setGlbUrl(url);
    } else {
      setImageName(item.name);
      setImageUrl(url);
      setGlbUrl("");
    }
  };

  const deleteHistoryItem = async (item) => {
    try {
      await api.studioDelete(item.name);
    } catch {
      /* ignore */
    }
    if (item.kind === "mesh" && glbUrl.includes(item.name)) setGlbUrl("");
    if (item.kind === "image") {
      if (imageUrl.includes(item.name)) setImageUrl("");
      if (imageName === item.name) setImageName("");
    }
    refreshHistory();
  };

  return (
    <div className="space-y-4">
      <SectionTitle
        icon={Boxes}
        title="Studio 3D · TRELLIS.2"
        subtitle="Image → objet 3D (GLB), visualisé en temps réel avec BabylonJS"
        right={
          <button className="btn-secondary" onClick={refreshStatus}>
            <RotateCw size={14} /> Actualiser
          </button>
        }
      />

      <Card>
        <div className="space-y-2">
          <ModelStatusRow
            title="Texte → Image"
            st={status?.image_gen}
            onLoad={() => api.studioLoadImageGen().then(refreshStatus)}
          />
          <TrellisPanel st={status?.trellis} onRefresh={refreshStatus} />
        </div>
        {status?.trellis?.runtime === "native" && !status.trellis.available && (
          <p className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            TRELLIS.2 n'est pas un modèle vLLM. Installez ses dépendances natives via
            <code className="mx-1 rounded bg-ink-900 px-1">scripts/setup_studio3d.sh</code>
            ou basculez sur le runtime « Docker » (aucune compilation sur l'hôte).
          </p>
        )}
      </Card>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Left: image creation / upload */}
        <Card className="space-y-4">
          <SectionTitle icon={Sparkles} title="1 · Image d'entrée" />

          <Field label="Prompt (texte → image)">
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                className="input"
                placeholder="ex. a cute red sport car, studio lighting, white background"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && genImage()}
                disabled={imgBusy}
              />
              <button
                className="btn-primary shrink-0 justify-center"
                onClick={genImage}
                disabled={imgBusy || !prompt.trim()}
              >
                {imgBusy ? <Spinner size={16} /> : <Wand2 size={16} />} Générer
              </button>
            </div>
          </Field>

          {/* Text->Image parameters */}
          <div className="rounded-xl border border-ink-border bg-ink-900/40">
            <button
              type="button"
              className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-slate-300"
              onClick={() => setShowImgParams((v) => !v)}
            >
              <span className="flex items-center gap-2">
                <Settings2 size={14} /> Paramètres · texte → image
              </span>
              <ChevronDown
                size={14}
                className={`transition-transform ${showImgParams ? "rotate-180" : ""}`}
              />
            </button>
            {showImgParams && (
              <div className="grid gap-3 border-t border-ink-border px-3 py-3 sm:grid-cols-2">
                <NumberRange
                  label="Étapes d'inférence"
                  hint="SD-Turbo : 1 suffit (1–8)"
                  value={imgParams.steps}
                  min={1}
                  max={8}
                  step={1}
                  onChange={(v) => setImg("steps", v)}
                />
                <NumberRange
                  label="Guidance (CFG)"
                  hint="SD-Turbo : 0 recommandé"
                  value={imgParams.guidance}
                  min={0}
                  max={6}
                  step={0.1}
                  onChange={(v) => setImg("guidance", v)}
                />
                <SelectField
                  label="Largeur"
                  value={String(imgParams.width)}
                  options={[384, 512, 640, 768, 1024].map((n) => ({
                    value: String(n),
                    label: `${n} px`,
                  }))}
                  onChange={(v) => setImg("width", Number(v))}
                />
                <SelectField
                  label="Hauteur"
                  value={String(imgParams.height)}
                  options={[384, 512, 640, 768, 1024].map((n) => ({
                    value: String(n),
                    label: `${n} px`,
                  }))}
                  onChange={(v) => setImg("height", Number(v))}
                />
                <SeedField
                  label="Seed"
                  value={imgParams.seed}
                  allowEmpty
                  onChange={(v) => setImg("seed", v)}
                />
                <label className="block sm:col-span-2">
                  <span className="text-xs font-medium text-slate-300">
                    Prompt négatif (optionnel)
                  </span>
                  <input
                    className="input mt-1 w-full"
                    placeholder="ex. blurry, low quality, text"
                    value={imgParams.negative_prompt}
                    onChange={(e) => setImg("negative_prompt", e.target.value)}
                  />
                </label>
              </div>
            )}
          </div>

          <div className="flex items-center gap-3 text-xs text-slate-500">
            <div className="h-px flex-1 bg-ink-border" />
            ou
            <div className="h-px flex-1 bg-ink-border" />
          </div>

          <div>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onUpload}
            />
            <button
              className="btn-secondary w-full justify-center"
              onClick={() => fileRef.current?.click()}
            >
              <Upload size={16} /> Importer une image
            </button>
          </div>

          <div className="grid aspect-square w-full place-items-center overflow-hidden rounded-xl border border-ink-border bg-ink-900/40">
            {imageUrl ? (
              <img src={imageUrl} alt="entrée" className="h-full w-full object-contain" />
            ) : (
              <div className="text-center text-slate-600">
                <ImageIcon size={40} className="mx-auto mb-2 opacity-40" />
                <p className="text-sm">Aucune image</p>
              </div>
            )}
          </div>

          {/* TRELLIS parameters */}
          <div className="rounded-xl border border-ink-border bg-ink-900/40">
            <button
              type="button"
              className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-slate-300"
              onClick={() => setShowMeshParams((v) => !v)}
            >
              <span className="flex items-center gap-2">
                <Settings2 size={14} /> Paramètres · TRELLIS.2 (image → 3D)
              </span>
              <ChevronDown
                size={14}
                className={`transition-transform ${showMeshParams ? "rotate-180" : ""}`}
              />
            </button>
            {showMeshParams && (
              <div className="grid gap-3 border-t border-ink-border px-3 py-3 sm:grid-cols-2">
                <SelectField
                  label="Qualité / résolution"
                  value={meshParams.pipeline_type}
                  options={[
                    { value: "512", label: "512 · rapide" },
                    { value: "1024", label: "1024 · standard" },
                    { value: "1024_cascade", label: "1024 cascade · recommandé" },
                    { value: "1536_cascade", label: "1536 cascade · max détail" },
                  ]}
                  onChange={(v) => setMesh("pipeline_type", v)}
                />
                <SelectField
                  label="Taille de texture"
                  value={String(meshParams.texture_size)}
                  options={[1024, 2048, 4096].map((n) => ({
                    value: String(n),
                    label: `${n} px`,
                  }))}
                  onChange={(v) => setMesh("texture_size", Number(v))}
                />
                <NumberRange
                  label="Étapes géométrie"
                  hint="forme/structure (défaut 12)"
                  value={meshParams.geometry_steps}
                  min={4}
                  max={50}
                  step={1}
                  onChange={(v) => setMesh("geometry_steps", v)}
                />
                <NumberRange
                  label="Guidance géométrie"
                  hint="défaut 7.5"
                  value={meshParams.geometry_guidance}
                  min={1}
                  max={15}
                  step={0.5}
                  onChange={(v) => setMesh("geometry_guidance", v)}
                />
                <NumberRange
                  label="Étapes texture"
                  hint="défaut 12"
                  value={meshParams.texture_steps}
                  min={4}
                  max={50}
                  step={1}
                  onChange={(v) => setMesh("texture_steps", v)}
                />
                <NumberRange
                  label="Guidance texture"
                  hint="défaut 1.0"
                  value={meshParams.texture_guidance}
                  min={0}
                  max={10}
                  step={0.5}
                  onChange={(v) => setMesh("texture_guidance", v)}
                />
                <SeedField
                  label="Seed"
                  value={meshParams.seed}
                  onChange={(v) => setMesh("seed", v === "" ? 0 : Number(v))}
                />
                <div className="flex items-end">
                  <ToggleRow
                    label="Détourer l'arrière-plan"
                    hint="RMBG-2.0 (désactiver si déjà détouré)"
                    checked={meshParams.preprocess_image}
                    onChange={(v) => setMesh("preprocess_image", v)}
                  />
                </div>
              </div>
            )}
          </div>

          <button
            className="btn-primary w-full justify-center"
            onClick={genMesh}
            disabled={!imageName || meshBusy}
          >
            {meshBusy ? <Spinner size={16} /> : <Boxes size={16} />} Générer le modèle 3D
          </button>

          {meshProgress && (
            <div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-ink-900">
                <div
                  className="h-full rounded-full bg-brand transition-all duration-500"
                  style={{ width: `${meshProgress.progress || 0}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-slate-400">
                {meshProgress.message} · {Math.round(meshProgress.progress || 0)}%
              </p>
            </div>
          )}
        </Card>

        {/* Right: 3D viewer */}
        <Card className="flex flex-col">
          <SectionTitle
            icon={Boxes}
            title="2 · Modèle 3D"
            right={
              glbUrl && (
                <a className="btn-secondary" href={glbUrl} download>
                  <Download size={14} /> GLB
                </a>
              )
            }
          />
          <div className="relative min-h-[320px] flex-1 overflow-hidden rounded-xl border border-ink-border bg-ink-900/40 lg:min-h-[420px]">
            {glbUrl ? (
              <>
                <Viewer3D src={glbUrl} />
                <div className="pointer-events-none absolute bottom-2 left-2 flex items-center gap-1.5 rounded-lg bg-black/50 px-2.5 py-1 text-[11px] text-slate-300">
                  <MousePointer2 size={12} /> Glissez pour tourner · molette pour zoomer
                </div>
              </>
            ) : (
              <div className="grid h-full place-items-center text-center text-slate-600">
                <div>
                  {meshBusy ? (
                    <>
                      <Loader2 size={40} className="mx-auto mb-2 animate-spin opacity-50" />
                      <p className="text-sm">Génération du maillage 3D…</p>
                    </>
                  ) : (
                    <>
                      <Boxes size={40} className="mx-auto mb-2 opacity-40" />
                      <p className="text-sm">Le modèle 3D s'affichera ici</p>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* History */}
      <Card>
        <SectionTitle
          icon={History}
          title="Historique"
          subtitle="Images et modèles 3D générés · rechargez ou supprimez"
          right={
            <button className="btn-secondary" onClick={refreshHistory}>
              <RotateCw size={14} /> Actualiser
            </button>
          }
        />
        {history.length === 0 ? (
          <div className="grid place-items-center py-10 text-center text-slate-600">
            <div>
              <History size={36} className="mx-auto mb-2 opacity-40" />
              <p className="text-sm">Aucune génération pour l'instant</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {history.map((item) => (
              <div
                key={item.name}
                className="group relative overflow-hidden rounded-xl border border-ink-border bg-ink-900/40"
              >
                <div className="grid aspect-square w-full place-items-center overflow-hidden bg-ink-900/60">
                  {item.kind === "image" ? (
                    <img
                      src={item.url}
                      alt={item.name}
                      className="h-full w-full object-contain"
                      loading="lazy"
                    />
                  ) : (
                    <Boxes size={36} className="text-brand/70" />
                  )}
                </div>
                <div className="px-2 py-1.5">
                  <div className="flex items-center gap-1.5">
                    <Badge tone={item.kind === "mesh" ? "blue" : "slate"}>
                      {item.kind === "mesh" ? "3D" : "Image"}
                    </Badge>
                    {item.created && (
                      <span className="flex items-center gap-1 text-[10px] text-slate-500">
                        <Clock size={10} />
                        {new Date(item.created * 1000).toLocaleString()}
                      </span>
                    )}
                  </div>
                  {item.prompt && (
                    <p className="mt-1 truncate text-[11px] text-slate-400" title={item.prompt}>
                      {item.prompt}
                    </p>
                  )}
                </div>
                <div className="flex border-t border-ink-border">
                  <button
                    className="flex flex-1 items-center justify-center gap-1 py-1.5 text-[11px] text-slate-300 hover:bg-ink-900/60"
                    onClick={() => viewHistoryItem(item)}
                  >
                    <Eye size={12} /> {item.kind === "mesh" ? "Voir" : "Utiliser"}
                  </button>
                  <button
                    className="flex items-center justify-center border-l border-ink-border px-3 py-1.5 text-rose-300 hover:bg-rose-500/10"
                    onClick={() => deleteHistoryItem(item)}
                    title="Supprimer"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
