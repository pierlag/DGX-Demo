#!/usr/bin/env bash
# vibeMCP — nettoyage des processus/services bloqués.
# - Stoppe backend (uvicorn)
# - Stoppe frontend (vite / npm run dev)
# - Stoppe les tunnels DevTunnel (devtunnel host)
# - Stoppe Qdrant via docker compose
# - Vérifie que les ports 8000/5173 sont libérés

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "==> Nettoyage vibeMCP"

# 1) Stopper les processus Python/Node liés au dev
# (ignore les erreurs si aucun processus ne correspond)
pkill -9 -f "uvicorn app.main" 2>/dev/null || true
pkill -9 -f "npm run dev" 2>/dev/null || true
pkill -9 -f "node .*vite" 2>/dev/null || true
pkill -9 -f "vite" 2>/dev/null || true

# Stopper d'éventuels téléchargements de modèles HuggingFace.
# Les téléchargements tournent dans des threads du process uvicorn (déjà tué
# ci-dessus), mais hf_transfer peut laisser des process résiduels ainsi que des
# verrous (*.lock) et fichiers partiels (*.incomplete) qui bloquent une reprise.
pkill -9 -f "huggingface_hub" 2>/dev/null || true
pkill -9 -f "hf_transfer" 2>/dev/null || true

# Nettoyer les verrous de téléchargement laissés dans le cache des modèles.
MODELS_DIR="$ROOT/appdata/models"
if [ -d "$MODELS_DIR" ]; then
  find "$MODELS_DIR" -type f \( -name "*.lock" -o -name "*.incomplete" \) \
    -delete 2>/dev/null || true
fi

# Stopper les tunnels DevTunnel (devtunnel host)
pkill -9 -f "devtunnel host" 2>/dev/null || true

# Supprimer tous les tunnels DevTunnel configurés
if command -v devtunnel >/dev/null 2>&1; then
  devtunnel delete-all -f >/dev/null 2>&1 || devtunnel delete-all >/dev/null 2>&1 || true
fi

# 2) Libérer explicitement les ports si encore occupés
if lsof -i :8000 -sTCP:LISTEN >/dev/null 2>&1; then
  kill -9 "$(lsof -t -i :8000 | head -1)" 2>/dev/null || true
fi

if lsof -i :5173 -sTCP:LISTEN >/dev/null 2>&1; then
  kill -9 "$(lsof -t -i :5173 | head -1)" 2>/dev/null || true
fi

# 3) Stopper Qdrant (docker compose)
if command -v docker >/dev/null 2>&1; then
  (
    cd "$ROOT"
    docker compose stop qdrant >/dev/null 2>&1 || true
  )
fi

sleep 1

echo "==> Vérification"
if lsof -i :8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "✗ Port 8000 encore occupé"
else
  echo "✓ Port 8000 libéré"
fi

if lsof -i :5173 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "✗ Port 5173 encore occupé"
else
  echo "✓ Port 5173 libéré"
fi

if command -v docker >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' | grep -q '^vibemcp-qdrant$'; then
    echo "✗ Qdrant encore actif"
  else
    echo "✓ Qdrant arrêté"
  fi
fi

if pgrep -f "devtunnel host" >/dev/null 2>&1; then
  echo "✗ devtunnel host encore actif"
else
  echo "✓ Tunnels DevTunnel arrêtés"
fi

if pgrep -f "huggingface_hub\|hf_transfer" >/dev/null 2>&1; then
  echo "✗ Téléchargement de modèle encore actif"
else
  echo "✓ Téléchargements de modèles arrêtés"
fi

echo "Nettoyage terminé."
