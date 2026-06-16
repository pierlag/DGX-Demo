import React, { useEffect, useState } from "react";
import {
  Globe,
  Github,
  Play,
  Square,
  Trash2,
  Copy,
  Link2,
  Plus,
  RefreshCw,
  LayoutDashboard,
  Network,
  Bug,
  LogOut,
} from "lucide-react";
import { Card, SectionTitle, Badge, Field, Spinner } from "../components/ui.jsx";
import { api } from "../api.js";

export default function TunnelsAdmin() {
  const [login, setLogin] = useState(null);
  const [tunnels, setTunnels] = useState([]);
  const [defaults, setDefaults] = useState([]);
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({ name: "", port: "", protocol: "http" });
  // Per-tunnel creation progress: { [name]: { value, message, ok, active } }
  const [progress, setProgress] = useState({});

  // GitHub repo integration (issue reporting)
  const [gh, setGh] = useState(null);
  const [repos, setRepos] = useState([]);
  const [selectedRepo, setSelectedRepo] = useState(
    () => localStorage.getItem("vibemcp.gh.repo") || ""
  );
  const [tokenInput, setTokenInput] = useState("");
  const [reportMsg, setReportMsg] = useState(null);

  const refresh = () => {
    api.tunnelLoginStatus().then(setLogin).catch(() => {});
    api.tunnelList().then((r) => setTunnels(r.tunnels || [])).catch(() => {});
  };

  const loadRepos = () => {
    api.ghRepos().then((r) => setRepos(r.repos || [])).catch(() => setRepos([]));
  };

  const refreshGh = () => {
    api.ghStatus().then((s) => {
      setGh((prev) => {
        if (s?.connected && !prev?.connected) loadRepos();
        return s;
      });
    }).catch(() => {});
  };

  useEffect(() => {
    api.tunnelDefaults().then((r) => setDefaults(r.tunnels || [])).catch(() => {});
    refreshGh();
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, []);

  // Poll GitHub status while a device-flow authorisation is pending.
  useEffect(() => {
    if (!gh?.device?.in_progress) return;
    const id = setInterval(refreshGh, 2500);
    return () => clearInterval(id);
  }, [gh?.device?.in_progress]);

  const ghLogin = async () => {
    setBusy("login");
    const r = await api.tunnelLogin().catch(() => null);
    if (r) setLogin(r);
    setBusy("");
  };

  const ghLogoutDevtunnel = async () => {
    setBusy("logout");
    const r = await api.tunnelLogout().catch(() => null);
    if (r) setLogin(r);
    setBusy("");
  };

  const connectDevice = async () => {
    setBusy("ghdevice");
    const s = await api.ghDevice().catch(() => null);
    setBusy("");
    if (s) {
      setGh(s);
      if (s.connected) loadRepos();
    }
  };

  const saveToken = async () => {
    if (!tokenInput.trim()) return;
    setBusy("ghtoken");
    const s = await api.ghSetToken(tokenInput.trim()).catch(() => null);
    setBusy("");
    if (s) {
      setGh(s);
      if (s.connected) {
        setTokenInput("");
        loadRepos();
      }
    }
  };

  const ghLogout = async () => {
    await api.ghLogout().catch(() => {});
    setGh({ connected: false, login: "" });
    setRepos([]);
  };

  const selectRepo = (full) => {
    setSelectedRepo(full);
    if (full) localStorage.setItem("vibemcp.gh.repo", full);
    else localStorage.removeItem("vibemcp.gh.repo");
  };

  const reportTunnel = async (t) => {
    if (!selectedRepo) return;
    setBusy(`report:${t.name}`);
    setReportMsg(null);
    const r = await api.ghReport(selectedRepo, t.name, t.url || "").catch(() => null);
    setBusy("");
    if (r) {
      setReportMsg({
        ok: r.ok,
        text: r.message || (r.ok ? "Signalé." : "Échec."),
        url: r.issue_url,
      });
    }
  };

  const createTunnel = async (name, port, protocol = "http") => {
    setBusy(`create:${name}`);
    setProgress((p) => ({
      ...p,
      [name]: { value: 0, message: "Initialisation…", ok: true, active: true },
    }));
    try {
      const resp = await api.tunnelCreateStream(name, Number(port), protocol);
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          let ev;
          try {
            ev = JSON.parse(line);
          } catch {
            continue;
          }
          setProgress((p) => ({
            ...p,
            [name]: {
              value: ev.progress ?? p[name]?.value ?? 0,
              message: ev.message ?? p[name]?.message ?? "",
              ok: ev.ok !== false,
              active: !ev.done,
            },
          }));
          if (ev.done || ev.tunnel) refresh();
        }
      }
    } catch (e) {
      setProgress((p) => ({
        ...p,
        [name]: { value: 100, message: `Erreur: ${e.message}`, ok: false, active: false },
      }));
    } finally {
      setBusy("");
      refresh();
      // Clear the progress bar a few seconds after a successful run.
      setTimeout(() => {
        setProgress((p) => {
          const cur = p[name];
          if (cur && cur.ok && !cur.active) {
            const { [name]: _omit, ...rest } = p;
            return rest;
          }
          return p;
        });
      }, 5000);
    }
  };

  const stopTunnel = async (name) => {
    setBusy(`stop:${name}`);
    await api.tunnelStop(name).catch(() => {});
    setBusy("");
    refresh();
  };

  const deleteTunnel = async (name) => {
    if (!window.confirm(`Supprimer le tunnel « ${name} » ?`)) return;
    setBusy(`del:${name}`);
    await api.tunnelDelete(name).catch(() => {});
    setBusy("");
    refresh();
  };

  const submitForm = async (e) => {
    e.preventDefault();
    if (!form.name || !form.port) return;
    await createTunnel(form.name, form.port, form.protocol);
    setForm({ name: "", port: "", protocol: "http" });
  };

  const copy = (txt) => navigator.clipboard?.writeText(txt);

  return (
    <div className="space-y-6">
      <SectionTitle
        icon={Globe}
        title="Admin · Tunnels (DevTunnel)"
        subtitle="Créer, héberger et supprimer les tunnels publics liés à GitHub"
        right={
          login?.logged_in ? (
            <Badge tone="green">● Connecté GitHub</Badge>
          ) : (
            <Badge tone="slate">Non connecté</Badge>
          )
        }
      />

      {/* GitHub login */}
      <Card>
        <SectionTitle
          icon={Github}
          title="Compte GitHub"
          subtitle="Requis pour créer et héberger des tunnels"
        />
        <p className="mb-3 text-xs text-slate-500">
          {login?.logged_in
            ? `Connecté : ${login.account || "compte GitHub"}`
            : "Non connecté. Lancez la connexion par code d'appareil."}
        </p>
        {!login?.logged_in && (
          <button className="btn-ghost" onClick={ghLogin} disabled={busy === "login"}>
            <Github size={16} /> Se connecter à GitHub
          </button>
        )}
        {login?.logged_in && (
          <button
            className="btn-ghost text-rose-300 hover:text-rose-200"
            onClick={ghLogoutDevtunnel}
            disabled={busy === "logout"}
          >
            {busy === "logout" ? <Spinner size={16} /> : <LogOut size={16} />} Se
            déconnecter
          </button>
        )}

        {!login?.logged_in && login?.device_code && (
          <div className="mt-4 rounded-xl border border-brand/40 bg-brand/5 p-4">
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-brand">
              Étape 1 · Copiez ce code
            </div>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-lg bg-ink-900 px-3 py-2 text-center font-mono text-2xl font-bold tracking-[0.3em] text-white">
                {login.device_code}
              </code>
              <button
                className="btn-ghost px-2 py-2"
                title="Copier le code"
                onClick={() => copy(login.device_code)}
              >
                <Copy size={16} />
              </button>
            </div>
            <div className="mt-3 text-xs font-medium uppercase tracking-wide text-brand">
              Étape 2 · Ouvrez GitHub et saisissez-le
            </div>
            <a
              href={login.verification_url || "https://github.com/login/device"}
              target="_blank"
              rel="noreferrer"
              className="btn-primary mt-2 w-full justify-center"
            >
              <Link2 size={16} />
              {login.verification_url || "github.com/login/device"}
            </a>
          </div>
        )}

        {!login?.logged_in && login?.login_in_progress && !login?.device_code && (
          <p className="mt-3 text-xs text-amber-300">Récupération du code d'appareil…</p>
        )}

        {/* GitHub repo integration (issue reporting) */}
        <div className="mt-5 border-t border-ink-border pt-5">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
              <Bug size={16} className="text-brand" /> Dépôt GitHub pour le suivi
            </div>
            {gh?.connected ? (
              <Badge tone="green">● {gh.login}</Badge>
            ) : (
              <Badge tone="slate">Non connecté</Badge>
            )}
          </div>
          <p className="mb-3 text-xs text-slate-500">
            Connectez-vous à GitHub (scope{" "}
            <code className="text-slate-300">repo</code>) pour signaler les
            tunnels via des issues GitHub.
          </p>

          {!gh?.connected ? (
            <div className="space-y-3">
              <button
                className="btn-primary"
                onClick={connectDevice}
                disabled={busy === "ghdevice" || gh?.device?.in_progress}
              >
                {busy === "ghdevice" || gh?.device?.in_progress ? (
                  <Spinner size={16} />
                ) : (
                  <Github size={16} />
                )}{" "}
                Se connecter à GitHub
              </button>

              {gh?.device?.in_progress && gh?.device?.user_code && (
                <div className="rounded-xl border border-brand/40 bg-brand/5 p-4">
                  <div className="mb-2 text-xs font-medium uppercase tracking-wide text-brand">
                    Étape 1 · Copiez ce code
                  </div>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 rounded-lg bg-ink-900 px-3 py-2 text-center font-mono text-2xl font-bold tracking-[0.3em] text-white">
                      {gh.device.user_code}
                    </code>
                    <button
                      className="btn-ghost px-2 py-2"
                      title="Copier le code"
                      onClick={() => copy(gh.device.user_code)}
                    >
                      <Copy size={16} />
                    </button>
                  </div>
                  <div className="mt-3 text-xs font-medium uppercase tracking-wide text-brand">
                    Étape 2 · Ouvrez GitHub et saisissez-le
                  </div>
                  <a
                    href={gh.device.verification_uri || "https://github.com/login/device"}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-primary mt-2 w-full justify-center"
                  >
                    <Link2 size={16} />
                    {gh.device.verification_uri || "github.com/login/device"}
                  </a>
                </div>
              )}

              <details className="text-xs text-slate-500">
                <summary className="cursor-pointer select-none hover:text-slate-300">
                  Ou utiliser un jeton personnel (PAT)
                </summary>
                <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
                  <input
                    className="input flex-1"
                    type="password"
                    placeholder="GitHub Personal Access Token (ghp_…, scope repo)"
                    value={tokenInput}
                    onChange={(e) => setTokenInput(e.target.value)}
                  />
                  <button
                    className="btn-ghost"
                    onClick={saveToken}
                    disabled={busy === "ghtoken" || !tokenInput.trim()}
                  >
                    {busy === "ghtoken" ? <Spinner size={16} /> : <Github size={16} />}{" "}
                    Connecter
                  </button>
                </div>
              </details>
            </div>
          ) : (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="flex-1">
                <Field label="Dépôt cible">
                  <select
                    className="input"
                    value={selectedRepo}
                    onChange={(e) => selectRepo(e.target.value)}
                  >
                    <option value="">— Aucun dépôt sélectionné —</option>
                    {repos.map((r) => (
                      <option key={r.full_name} value={r.full_name}>
                        {r.full_name} {r.private ? "🔒 privé" : "🌐 public"}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <button
                className="btn-ghost px-2 py-2"
                onClick={loadRepos}
                title="Rafraîchir la liste des dépôts"
              >
                <RefreshCw size={16} />
              </button>
              <button
                className="btn-ghost px-2 py-2 text-rose-300 hover:text-rose-200"
                onClick={ghLogout}
                title="Déconnecter le jeton GitHub"
              >
                <LogOut size={16} />
              </button>
            </div>
          )}

          {gh?.message && !gh?.connected && (
            <p className="mt-2 text-xs text-amber-300">{gh.message}</p>
          )}
          {selectedRepo && (
            <p className="mt-2 text-xs text-slate-500">
              Dépôt actif : <span className="text-brand">{selectedRepo}</span> ·
              une action « Signaler » apparaît dans la liste des tunnels.
            </p>
          )}
          {reportMsg && (
            <p
              className={`mt-2 text-xs ${
                reportMsg.ok ? "text-brand" : "text-rose-300"
              }`}
            >
              {reportMsg.text}{" "}
              {reportMsg.url && (
                <a
                  href={reportMsg.url}
                  target="_blank"
                  rel="noreferrer"
                  className="underline"
                >
                  voir l'issue
                </a>
              )}
            </p>
          )}
        </div>
      </Card>

      {/* Quick create the 2 standard tunnels */}
      <Card>
        <SectionTitle
          title="Créer un tunnel standard"
          subtitle="Dashboard (5173) et serveur MCP (9000)"
        />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {defaults.map((d) => {
            const live = tunnels.find((t) => t.name === d.name);
            const Icon = d.name === "dashboard" ? LayoutDashboard : Network;
            const isBusy = busy === `create:${d.name}`;
            return (
              <div
                key={d.name}
                className="rounded-xl border border-ink-border bg-ink-900/40 p-4"
              >
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
                    <Icon size={16} className="text-brand" />
                    {d.name}
                  </div>
                  {live?.hosting ? (
                    <Badge tone="green">● Actif</Badge>
                  ) : (
                    <Badge tone="slate">Inactif</Badge>
                  )}
                </div>
                <p className="mb-3 text-xs text-slate-500">
                  Port local {d.port} · protocole http · accès anonyme
                </p>
                <button
                  className="btn-primary"
                  onClick={() => createTunnel(d.name, d.port)}
                  disabled={isBusy || !login?.logged_in || live?.hosting}
                >
                  {isBusy ? <Spinner /> : <Play size={16} />} Créer & héberger
                </button>
                {!login?.logged_in && (
                  <p className="mt-2 text-xs text-amber-300">
                    Connectez-vous à GitHub d'abord.
                  </p>
                )}
                {progress[d.name] && (
                  <div className="mt-3">
                    <div className="h-2 w-full overflow-hidden rounded-full bg-ink-700">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          progress[d.name].ok ? "bg-brand" : "bg-rose-500"
                        }`}
                        style={{ width: `${progress[d.name].value}%` }}
                      />
                    </div>
                    <p
                      className={`mt-1.5 whitespace-pre-wrap break-words text-xs ${
                        progress[d.name].ok ? "text-slate-400" : "text-rose-300"
                      }`}
                    >
                      {progress[d.name].message}
                    </p>
                  </div>
                )}
                {live?.url && (
                  <div className="mt-3 rounded-lg border border-ink-border bg-ink-950/60 p-2">
                    <div className="flex items-center gap-2">
                      <a
                        href={live.url}
                        target="_blank"
                        rel="noreferrer"
                        className="min-w-0 flex-1 break-all font-mono text-xs text-brand hover:underline"
                      >
                        {live.url}
                      </a>
                      <button
                        className="btn-ghost shrink-0 px-2 py-1"
                        title="Copier l'URL"
                        onClick={() => copy(live.url)}
                      >
                        <Copy size={14} />
                      </button>
                    </div>
                  </div>
                )}
                {live?.hosting && !live?.url && (
                  <p className="mt-2 text-xs text-slate-400">Récupération de l'URL…</p>
                )}
              </div>
            );
          })}
        </div>

        {/* Custom tunnel form */}
        <form
          onSubmit={submitForm}
          className="mt-5 grid grid-cols-1 gap-3 border-t border-ink-border pt-5 sm:grid-cols-[1fr_140px_120px_auto] sm:items-end"
        >
          <Field label="Nom du tunnel">
            <input
              className="input"
              placeholder="ex. mon-app"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Port local">
            <input
              className="input"
              type="number"
              placeholder="5173"
              value={form.port}
              onChange={(e) => setForm({ ...form, port: e.target.value })}
            />
          </Field>
          <Field label="Protocole">
            <select
              className="input"
              value={form.protocol}
              onChange={(e) => setForm({ ...form, protocol: e.target.value })}
            >
              <option value="http">http</option>
              <option value="https">https</option>
            </select>
          </Field>
          <button className="btn-primary" type="submit" disabled={!login?.logged_in}>
            <Plus size={16} /> Créer
          </button>
        </form>

        {/* Progress for custom (non-standard) tunnels */}
        {Object.entries(progress)
          .filter(([n]) => !defaults.some((d) => d.name === n))
          .map(([n, pr]) => (
            <div key={n} className="mt-3">
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-medium text-slate-300">{n}</span>
                <span className="font-mono text-slate-500">{pr.value}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-ink-700">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    pr.ok ? "bg-brand" : "bg-rose-500"
                  }`}
                  style={{ width: `${pr.value}%` }}
                />
              </div>
              <p className={`mt-1 whitespace-pre-wrap break-words text-xs ${pr.ok ? "text-slate-400" : "text-rose-300"}`}>
                {pr.message}
              </p>
            </div>
          ))}
      </Card>

      {/* All configured tunnels */}
      <Card>
        <SectionTitle
          title="Tunnels configurés"
          subtitle="Tous les tunnels de votre compte"
          right={
            <button className="btn-ghost px-2 py-1" onClick={refresh} title="Rafraîchir">
              <RefreshCw size={16} />
            </button>
          }
        />
        {tunnels.length === 0 ? (
          <p className="text-sm text-slate-500">Aucun tunnel configuré.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-ink-border">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="bg-ink-900/60 text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-2.5">Nom</th>
                  <th className="px-4 py-2.5">Port</th>
                  <th className="px-4 py-2.5">État</th>
                  <th className="w-1/2 px-4 py-2.5">URL publique</th>
                  <th className="px-4 py-2.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-border">
                {tunnels.map((t) => (
                  <tr key={t.name} className="hover:bg-ink-900/30">
                    <td className="px-4 py-3">
                      <div className="font-medium text-white">{t.name}</div>
                      {t.tunnel_id && (
                        <div className="font-mono text-[11px] text-slate-500">
                          {t.tunnel_id}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-300">
                      {t.port || "—"}
                    </td>
                    <td className="px-4 py-3">
                      {t.hosting ? (
                        <Badge tone="green">● Actif</Badge>
                      ) : (
                        <Badge tone="slate">Inactif</Badge>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {t.url ? (
                        <div className="flex items-center gap-2">
                          <a
                            href={t.url}
                            target="_blank"
                            rel="noreferrer"
                            className="min-w-0 flex-1 break-all font-mono text-xs text-brand hover:underline"
                          >
                            {t.url}
                          </a>
                          <button
                            className="btn-ghost shrink-0 px-2 py-1"
                            onClick={() => copy(t.url)}
                            title="Copier l'URL"
                          >
                            <Copy size={13} />
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-500">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <div className="flex items-center justify-end gap-2">
                        {selectedRepo && (
                          <button
                            className="btn-ghost px-2 py-1"
                            onClick={() => reportTunnel(t)}
                            disabled={busy === `report:${t.name}`}
                            title={`Signaler « ${t.name} » sur ${selectedRepo}`}
                          >
                            {busy === `report:${t.name}` ? (
                              <Spinner size={14} />
                            ) : (
                              <Bug size={14} />
                            )}
                          </button>
                        )}
                        {t.hosting ? (
                          <button
                            className="btn-ghost px-2 py-1"
                            onClick={() => stopTunnel(t.name)}
                            disabled={busy === `stop:${t.name}`}
                            title="Arrêter l'hébergement"
                          >
                            <Square size={14} />
                          </button>
                        ) : (
                          t.port > 0 && (
                            <button
                              className="btn-ghost px-2 py-1"
                              onClick={() => createTunnel(t.name, t.port, t.protocol)}
                              disabled={
                                busy === `create:${t.name}` || !login?.logged_in
                              }
                              title="Héberger"
                            >
                              <Play size={14} />
                            </button>
                          )
                        )}
                        <button
                          className="btn-ghost px-2 py-1 text-rose-300 hover:text-rose-200"
                          onClick={() => deleteTunnel(t.name)}
                          disabled={busy === `del:${t.name}`}
                          title="Supprimer le tunnel"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
