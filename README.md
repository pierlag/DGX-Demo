> 🇬🇧 **English** (below) · 🇫🇷 [Français](#dgx-demo--serveur-mcp-rag--dashboard-pour-dgx-spark-gb10)

# DGX Demo — MCP RAG Server + Dashboard for DGX Spark (GB10)

An **MCP** server exposed via **devtunnel**, performing **RAG** over a local
directory (`ragdoclocal`), backed by a **vLLM** server that loads a model
locally on the **NVIDIA GB10** superchip (unified memory ~128 GB, aarch64).

Everything is driven from a highly visual **web dashboard**, built for the demo.

## Architecture

```
React Frontend (Vite + Tailwind + Recharts)  ── http/ws ──▶  FastAPI Backend
        │  Real-time dashboard                                    │
        │  Admin 1: vLLM Models                                   ├─▶ vLLM (Docker NGC)  :8001
        │  Admin 2: MCP Server                                    ├─▶ MCP Server (HTTP)  :9000 ─▶ DevTunnel
        │  Admin 3: Tunnels (DevTunnel)                           ├─▶ Qdrant (Docker)    :6333
        │  Admin 4: RAG / Documents                               └─▶ fastembed (embeddings)
        └  MCP test chat
```

## Components

| Building block | Choice | Why |
|---|---|---|
| Frontend | React + Vite + TailwindCSS + Recharts + lucide | Elegant dashboard, real-time charts |
| Backend | FastAPI + WebSocket | Glues vLLM/HF/MCP together, live metrics |
| Vector DB | **Qdrant** (Docker) | ARM binary, fast, built-in UI |
| Embeddings | **fastembed** (ONNX, `multilingual-e5-large`) | Multilingual, no PyTorch, ARM-friendly |
| LLM | **vLLM** (NGC container) | OpenAI-compatible inference on GB10 |
| MCP | `mcp` SDK (streamable-HTTP transport) | Compatible with devtunnel |
| Tunnel | `devtunnel` (Microsoft) | External exposure tied to GitHub |
| Monitoring | NVML (`nvidia-ml-py`) + psutil | GPU util / unified memory / tokens |

## The interfaces

1. **Dashboard** — tokens/s (headline metric), total tokens, requests, p50/p95
   latencies, loaded models, unified memory, indexed files, MCP clients, GPU
   and memory charts over 15 min, active model details.
2. **vLLM Models Admin** — DGX-compatible selection, HuggingFace search, local
   download, standard vLLM parameters (dtype, quantization, max_model_len,
   gpu_memory_utilization, tensor_parallel_size, …), launch.
3. **MCP Admin** — meta-prompt and start/stop of the MCP server.
4. **Tunnels Admin (DevTunnel)** — GitHub connection, creation/hosting of named
   tunnels (dashboard on 5173, MCP server on 9000), list of all configured
   tunnels, deletion, display of dynamic public URLs.
5. **RAG Admin** — document import (.txt/.md/.pdf/.docx), Qdrant vectorization
   with a progress bar, file listing.
6. **Test chat** — validates the RAG + vLLM chain, shows sources, latency, and
   tokens per request.

## Prerequisites

- DGX Spark (GB10), Ubuntu 24.04 aarch64
- Docker, devtunnel CLI (already present)
- Python 3.12, Node.js (installed locally in `~/.local/node`)

## Installation

```bash
# 1) Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) Frontend
export PATH="$HOME/.local/node/bin:$PATH"
cd ../frontend && npm install

# 3) Config
Edit `.env` and adjust the vLLM image if needed.
```

## Startup

```bash
./scripts/start.sh
```

Then open **http://localhost:5173** (dev) — the backend runs on `:8000`,
Qdrant on `:6333`.

> In production, `npm run build` generates `frontend/dist`, served directly by
> the FastAPI backend on `:8000`.

## Launch a vLLM model (GB10)

By default, the project uses `vllm/vllm-openai:latest` (multi-arch, including
`linux/arm64`). You can override it in `.env`
(`DGX_DEMO_VLLM_DOCKER_IMAGE`) with a private NGC image if needed.
From the **vLLM Models** admin:
download a model (e.g. `Qwen/Qwen2.5-14B-Instruct`), set the parameters,
then **Launch**. The dashboard then shows tokens/s in real time.

## Notes

- **Unified** memory: the dashboard reports system memory usage (NVML does not
  separate VRAM on GB10).
- Gated models (Llama, Gemma): provide a HuggingFace token in the admin.
- The `data/` folder (Qdrant, root via Docker) is separate from `appdata/`
  (models/state, written by the backend).

---

> 🇫🇷 **Français** (ci-dessous) · 🇬🇧 [English](#dgx-demo--mcp-rag-server--dashboard-for-dgx-spark-gb10)

# DGX Demo — Serveur MCP RAG + Dashboard pour DGX Spark (GB10)

Serveur **MCP** exposé par **devtunnel**, faisant du **RAG** sur un répertoire
local (`ragdoclocal`), adossé à un serveur **vLLM** qui charge un modèle
localement sur le superchip **NVIDIA GB10** (mémoire unifiée ~128 Go, aarch64).

Le tout piloté depuis un **dashboard web** très visuel, conçu pour la démo.

## Architecture

```
Frontend React (Vite + Tailwind + Recharts)  ── http/ws ──▶  Backend FastAPI
        │  Dashboard temps réel                                   │
        │  Admin 1 : Modèles vLLM                                 ├─▶ vLLM (Docker NGC)  :8001
        │  Admin 2 : Serveur MCP                                  ├─▶ Serveur MCP (HTTP) :9000 ─▶ DevTunnel
        │  Admin 3 : Tunnels (DevTunnel)                          ├─▶ Qdrant (Docker)    :6333
        │  Admin 4 : RAG / Documents                              └─▶ fastembed (embeddings)
        └  Chat de test MCP
```

## Composants

| Brique | Choix | Pourquoi |
|---|---|---|
| Frontend | React + Vite + TailwindCSS + Recharts + lucide | Dashboard élégant, graphes temps réel |
| Backend | FastAPI + WebSocket | Colle à vLLM/HF/MCP, métriques en direct |
| Vector DB | **Qdrant** (Docker) | Binaire ARM, rapide, UI intégrée |
| Embeddings | **fastembed** (ONNX, `multilingual-e5-large`) | Multilingue, sans PyTorch, ARM-friendly |
| LLM | **vLLM** (conteneur NGC) | Inférence OpenAI-compatible sur GB10 |
| MCP | SDK `mcp` (transport streamable-HTTP) | Compatible devtunnel |
| Tunnel | `devtunnel` (Microsoft) | Exposition externe liée à GitHub |
| Monitoring | NVML (`nvidia-ml-py`) + psutil | Util GPU / mémoire unifiée / tokens |

## Les interfaces

1. **Dashboard** — tokens/s (métrique vedette), total tokens, requêtes, latences
   p50/p95, modèles chargés, mémoire unifiée, fichiers indexés, clients MCP,
   graphes GPU et mémoire sur 15 min, détail du modèle actif.
2. **Admin Modèles vLLM** — sélection compatible DGX, recherche HuggingFace,
   téléchargement local, paramètres standard vLLM (dtype, quantization,
   max_model_len, gpu_memory_utilization, tensor_parallel_size, …), lancement.
3. **Admin MCP** — méta-prompt et démarrage/arrêt du serveur MCP.
4. **Admin Tunnels (DevTunnel)** — connexion GitHub, création/hébergement des
   tunnels nommés (dashboard sur 5173, serveur MCP sur 9000), liste de tous les
   tunnels configurés, suppression, affichage des URL publiques dynamiques.
5. **Admin RAG** — import de documents (.txt/.md/.pdf/.docx), vectorisation
   Qdrant avec barre de progression, liste des fichiers.
6. **Chat de test** — valide la chaîne RAG + vLLM, affiche sources, latence et
   tokens par requête.

## Prérequis

- DGX Spark (GB10), Ubuntu 24.04 aarch64
- Docker, devtunnel CLI (déjà présents)
- Python 3.12, Node.js (installé en local dans `~/.local/node`)

## Installation

```bash
# 1) Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) Frontend
export PATH="$HOME/.local/node/bin:$PATH"
cd ../frontend && npm install

# 3) Config
Éditer `.env` et ajuster l'image vLLM si nécessaire.
```

## Démarrage

```bash
./scripts/start.sh
```

Puis ouvrir **http://localhost:5173** (dev) — le backend tourne sur `:8000`,
Qdrant sur `:6333`.

> En production, `npm run build` génère `frontend/dist`, servi directement par
> le backend FastAPI sur `:8000`.

## Lancer un modèle vLLM (GB10)

Par défaut, le projet utilise `vllm/vllm-openai:latest` (multi-arch, dont
`linux/arm64`). Vous pouvez remplacer dans `.env`
(`DGX_DEMO_VLLM_DOCKER_IMAGE`) par une image NGC privée si besoin.
Depuis l'admin **Modèles vLLM** :
télécharger un modèle (ex. `Qwen/Qwen2.5-14B-Instruct`), régler les paramètres,
puis **Lancer**. Le dashboard affiche alors les tokens/s en temps réel.

## Notes

- Mémoire **unifiée** : le dashboard reporte l'usage mémoire système (NVML ne
  sépare pas la VRAM sur GB10).
- Modèles gated (Llama, Gemma) : fournir un token HuggingFace dans l'admin.
- Le dossier `data/` (Qdrant, root via Docker) est distinct de `appdata/`
  (modèles/état, écrit par le backend).
