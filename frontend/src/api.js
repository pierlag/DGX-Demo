// Thin API client for the vibeMCP backend.
const J = { "Content-Type": "application/json" };

async function req(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

export const api = {
  // Models
  curated: () => req("/api/models/curated"),
  searchModels: (q) => req(`/api/models/search?q=${encodeURIComponent(q)}`),
  downloadedModels: () => req("/api/models/downloaded"),
  downloadModel: (model_id, hf_token) =>
    req("/api/models/download", { method: "POST", headers: J, body: JSON.stringify({ model_id, hf_token }) }),
  downloadStatus: (model_id) => req(`/api/models/download/status?model_id=${encodeURIComponent(model_id)}`),
  launchModel: (params) =>
    req("/api/models/launch", { method: "POST", headers: J, body: JSON.stringify(params) }),
  stopModel: () => req("/api/models/stop", { method: "POST" }),
  modelStatus: () => req("/api/models/status"),

  // MCP server
  getMcpConfig: () => req("/api/mcp/config"),
  setMcpConfig: (meta_prompt) =>
    req("/api/mcp/config", { method: "POST", headers: J, body: JSON.stringify({ meta_prompt }) }),
  startMcp: () => req("/api/mcp/start", { method: "POST" }),
  stopMcp: () => req("/api/mcp/stop", { method: "POST" }),
  mcpStatus: () => req("/api/mcp/status"),

  // DevTunnel management (named tunnels)
  tunnelDefaults: () => req("/api/tunnels/defaults"),
  tunnelLoginStatus: () => req("/api/tunnels/login-status"),
  tunnelLogin: () => req("/api/tunnels/login", { method: "POST" }),
  tunnelList: () => req("/api/tunnels/list"),
  tunnelCreate: (name, port, protocol = "http") =>
    req("/api/tunnels/create", { method: "POST", headers: J, body: JSON.stringify({ name, port, protocol }) }),
  tunnelStop: (name) =>
    req("/api/tunnels/stop", { method: "POST", headers: J, body: JSON.stringify({ name }) }),
  tunnelDelete: (name) =>
    req("/api/tunnels/delete", { method: "POST", headers: J, body: JSON.stringify({ name }) }),

  // RAG
  ragFiles: () => req("/api/rag/files"),
  ragUpload: (formData) => req("/api/rag/upload", { method: "POST", body: formData }),
  ragDelete: (name) => req(`/api/rag/file?name=${encodeURIComponent(name)}`, { method: "DELETE" }),
  ragIndex: () => req("/api/rag/index", { method: "POST" }),
  ragIndexStatus: () => req("/api/rag/index/status"),

  // Docker
  listDockerContainers: (all = true) =>
    req(`/api/docker/containers?all_=${all}`),
  startDockerContainer: (container_id) =>
    req(`/api/docker/containers/${container_id}/start`, { method: "POST" }),
  stopDockerContainer: (container_id) =>
    req(`/api/docker/containers/${container_id}/stop`, { method: "POST" }),
  getDockerContainerConfig: (container_id) =>
    req(`/api/docker/containers/${container_id}/config`),

  // Metrics
  snapshot: () => req("/api/metrics/snapshot"),
};
