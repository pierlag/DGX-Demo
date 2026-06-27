#!/usr/bin/env bash
# DGX Demo — démarrage de tous les services (Qdrant, backend, frontend).
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
export PATH="$HOME/.local/node/bin:$PATH"

echo "==> 1/3 Services Docker (Qdrant + Ollama + Observabilité)"
# Qdrant (RAG), Ollama (backend Copilot hors-ligne) et la stack d'observabilité
# (exporter + Prometheus + Loki + Promtail + Grafana).
docker compose up -d qdrant ollama ollama-exporter prometheus loki promtail grafana

echo "    Grafana    : http://localhost:3000  (admin/admin)"
echo "    Prometheus : http://localhost:9090"
echo "    Ollama API : http://localhost:11434/v1"

echo "==> 2/3 Backend FastAPI (port 8000)"
cd "$ROOT/backend"
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACK_PID=$!

echo "==> 3/3 Frontend Vite (port 5173)"
cd "$ROOT/frontend"
npm run dev -- --host 0.0.0.0 &
FRONT_PID=$!

echo ""
echo "  Dashboard : http://localhost:5173"
echo "  API       : http://localhost:8000/api/health"
echo "  Qdrant UI : http://localhost:6333/dashboard"
echo "  Grafana   : http://localhost:3000"
echo ""
echo "Ctrl+C pour tout arrêter."

trap "kill $BACK_PID $FRONT_PID 2>/dev/null; docker compose stop qdrant ollama ollama-exporter prometheus loki promtail grafana" INT TERM
wait
