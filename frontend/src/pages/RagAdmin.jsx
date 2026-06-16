import React, { useEffect, useRef, useState } from "react";
import {
  Database,
  Upload,
  Trash2,
  Play,
  FileText,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Card, SectionTitle, Badge } from "../components/ui.jsx";
import { api } from "../api.js";

export default function RagAdmin() {
  const [files, setFiles] = useState([]);
  const [index, setIndex] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const refresh = () => {
    api.ragFiles().then((r) => setFiles(r.files || [])).catch(() => {});
    api.ragIndexStatus().then(setIndex).catch(() => {});
  };

  useEffect(() => {
    refresh();
    const id = setInterval(() => api.ragIndexStatus().then(setIndex).catch(() => {}), 1500);
    return () => clearInterval(id);
  }, []);

  const onUpload = async (e) => {
    const list = e.target.files;
    if (!list?.length) return;
    setUploading(true);
    const fd = new FormData();
    Array.from(list).forEach((f) => fd.append("files", f));
    try {
      await api.ragUpload(fd);
      refresh();
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const del = async (name) => {
    await api.ragDelete(name);
    refresh();
  };

  const reindex = async () => {
    await api.ragIndex();
    refresh();
  };

  const running = index?.status === "running";
  const pct =
    index?.total_files > 0
      ? Math.round((index.processed_files / index.total_files) * 100)
      : 0;

  return (
    <div className="space-y-6">
      <SectionTitle
        icon={Database}
        title="Admin · RAG / Documents"
        subtitle="Répertoire ragdoclocal · vectorisation Qdrant"
        right={<Badge tone="blue">{files.length} fichiers</Badge>}
      />

      <Card>
        <SectionTitle title="Importer des documents" subtitle="Formats: .txt .md .pdf .docx" />
        <div className="flex flex-wrap items-center gap-3">
          <button
            className="btn-primary"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
            Choisir des fichiers
          </button>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".txt,.md,.markdown,.pdf,.docx"
            className="hidden"
            onChange={onUpload}
          />
          <button className="btn-ghost" onClick={refresh}>
            <RefreshCw size={16} /> Rafraîchir
          </button>
        </div>
      </Card>

      <Card>
        <SectionTitle
          title="Vectorisation"
          subtitle="Embeddings multilingues (fastembed) → Qdrant"
          right={
            <button className="btn-primary" onClick={reindex} disabled={running}>
              {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {running ? "Indexation…" : "Lancer la vectorisation"}
            </button>
          }
        />
        {index && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">{index.message || "Prêt"}</span>
              <Badge
                tone={
                  index.status === "done"
                    ? "green"
                    : index.status === "error"
                    ? "red"
                    : index.status === "running"
                    ? "amber"
                    : "slate"
                }
              >
                {index.status}
              </Badge>
            </div>
            {running && (
              <div className="h-2 w-full overflow-hidden rounded-full bg-ink-900">
                <div
                  className="h-full bg-brand transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
            )}
            <div className="text-xs text-slate-500">
              {index.processed_files}/{index.total_files} fichiers · {index.chunks} chunks
            </div>
          </div>
        )}
      </Card>

      <Card>
        <SectionTitle title="Documents indexables" subtitle="Contenu du répertoire ragdoclocal" />
        {files.length === 0 ? (
          <p className="text-sm text-slate-400">Aucun document. Importez des fichiers ci-dessus.</p>
        ) : (
          <div className="divide-y divide-ink-border">
            {files.map((f) => (
              <div key={f.name} className="flex items-center justify-between py-2.5">
                <div className="flex items-center gap-3 min-w-0">
                  <FileText size={16} className="text-slate-500 shrink-0" />
                  <span className="truncate font-mono text-sm text-slate-200">{f.name}</span>
                  <Badge tone="slate">{f.ext}</Badge>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs text-slate-500">{f.size_kb} Ko</span>
                  <button
                    className="text-slate-500 hover:text-rose-400"
                    onClick={() => del(f.name)}
                  >
                    <Trash2 size={16} />
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
