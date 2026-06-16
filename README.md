# vibeMCP — Serveur MCP RAG + Dashboard pour DGX Spark (GB10)

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
(`VIBEMCP_VLLM_DOCKER_IMAGE`) par une image NGC privée si besoin.
Depuis l'admin **Modèles vLLM** :
télécharger un modèle (ex. `Qwen/Qwen2.5-14B-Instruct`), régler les paramètres,
puis **Lancer**. Le dashboard affiche alors les tokens/s en temps réel.

## Notes

- Mémoire **unifiée** : le dashboard reporte l'usage mémoire système (NVML ne
  sépare pas la VRAM sur GB10).
- Modèles gated (Llama, Gemma) : fournir un token HuggingFace dans l'admin.
- Le dossier `data/` (Qdrant, root via Docker) est distinct de `appdata/`
  (modèles/état, écrit par le backend).
