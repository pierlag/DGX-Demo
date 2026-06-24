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
  allDownloads: () => req("/api/models/downloads"),
  deleteDownloadedModel: (model_id) =>
    req(`/api/models/downloaded?model_id=${encodeURIComponent(model_id)}`, { method: "DELETE" }),
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
  tunnelLogout: () => req("/api/tunnels/logout", { method: "POST" }),
  tunnelList: () => req("/api/tunnels/list"),
  tunnelCreate: (name, port, protocol = "http") =>
    req("/api/tunnels/create", { method: "POST", headers: J, body: JSON.stringify({ name, port, protocol }) }),
  tunnelCreateStream: (name, port, protocol = "http") =>
    fetch("/api/tunnels/create-stream", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ name, port, protocol }),
    }),
  tunnelStop: (name) =>
    req("/api/tunnels/stop", { method: "POST", headers: J, body: JSON.stringify({ name }) }),
  tunnelDelete: (name) =>
    req("/api/tunnels/delete", { method: "POST", headers: J, body: JSON.stringify({ name }) }),

  // GitHub repo integration (issue reporting)
  ghStatus: () => req("/api/tunnels/github/status"),
  ghDevice: () => req("/api/tunnels/github/device", { method: "POST" }),
  ghSetToken: (token) =>
    req("/api/tunnels/github/token", { method: "POST", headers: J, body: JSON.stringify({ token }) }),
  ghLogout: () => req("/api/tunnels/github/logout", { method: "POST" }),
  ghRepos: () => req("/api/tunnels/github/repos"),
  ghReport: (repo, name, url) =>
    req("/api/tunnels/github/report", { method: "POST", headers: J, body: JSON.stringify({ repo, name, url }) }),

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

  // Studio 3D (TRELLIS.2 image->3D + text->image)
  studioStatus: () => req("/api/studio3d/status"),
  studioLoadImageGen: () => req("/api/studio3d/image-gen/load", { method: "POST" }),
  studioLoadTrellis: () => req("/api/studio3d/trellis/load", { method: "POST" }),
  studioSetTrellisRuntime: (runtime) =>
    req("/api/studio3d/trellis/runtime", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ runtime }),
    }),
  studioTrellisBuild: () => req("/api/studio3d/trellis/container/build", { method: "POST" }),
  studioTrellisStart: () => req("/api/studio3d/trellis/container/start", { method: "POST" }),
  studioTrellisStop: () => req("/api/studio3d/trellis/container/stop", { method: "POST" }),
  studioTextToImage: (prompt, params = {}) =>
    req("/api/studio3d/text-to-image", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ prompt, ...params }),
    }),
  studioUpload: (formData) =>
    req("/api/studio3d/upload", { method: "POST", body: formData }),
  studioGenerate: (image_name, params = {}) =>
    req("/api/studio3d/generate", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ image_name, ...params }),
    }),
  studioJob: (job_id) => req(`/api/studio3d/job?job_id=${encodeURIComponent(job_id)}`),
  studioJobs: () => req("/api/studio3d/jobs"),
  studioQueue: () => req("/api/studio3d/queue"),
  studioHistory: () => req("/api/studio3d/history"),
  studioSetPreview: (name, image) =>
    req("/api/studio3d/preview", {
      method: "POST",
      headers: J,
      body: JSON.stringify({ name, image }),
    }),
  studioDelete: (name) =>
    req(`/api/studio3d/file/${encodeURIComponent(name)}`, { method: "DELETE" }),

  // Metrics
  snapshot: () => req("/api/metrics/snapshot"),
};
