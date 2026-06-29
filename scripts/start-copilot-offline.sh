#!/usr/bin/env bash
# DGX Demo — launch the GitHub Copilot CLI wired to the local Ollama backend in
# offline / airgapped mode. Inference runs 100% on-device; nothing reaches
# GitHub's servers.
#
# Usage:
#   ./scripts/start-copilot-offline.sh                       # uses the first local model
#   ./scripts/start-copilot-offline.sh --model llama3.2:3b
#   ./scripts/start-copilot-offline.sh --no-launch           # print env only
#   ./scripts/start-copilot-offline.sh --pull                # pull the model first (needs network)
#
# Prereqs: docker (the dgx-demo-ollama container), the Copilot CLI
#   (npm install -g @github/copilot), and a model pulled from the dashboard.
set -euo pipefail

cd "$(dirname "$0")/.."

PORT=11434
MODEL=""
NO_LAUNCH=0
PULL=0
BASE_URL="http://localhost:${PORT}/v1"

c_cyan()  { printf '\033[36m%s\033[0m\n' "$*"; }
c_green() { printf '\033[32m%s\033[0m\n' "$*"; }
c_red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
die() { c_red "ERROR: $*"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)     MODEL="$2"; shift 2 ;;
    --port)      PORT="$2"; BASE_URL="http://localhost:${PORT}/v1"; shift 2 ;;
    --no-launch) NO_LAUNCH=1; shift ;;
    --pull)      PULL=1; shift ;;
    -h|--help)   sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1 (try --help)" ;;
  esac
done

command -v docker >/dev/null 2>&1 || die "docker not found."

# 1. Ensure Ollama is up.
if ! curl -fsS --max-time 3 "http://localhost:${PORT}/api/version" >/dev/null 2>&1; then
  c_cyan "==> Starting the Ollama container..."
  docker compose up -d ollama
  deadline=$(( $(date +%s) + 60 ))
  until curl -fsS --max-time 3 "http://localhost:${PORT}/api/version" >/dev/null 2>&1; do
    [[ $(date +%s) -gt $deadline ]] && die "Ollama did not become ready within 60s."
    sleep 2
  done
fi
c_green "==> Ollama endpoint is up (${BASE_URL})."

# 2. Optionally pull the requested model.
if [[ $PULL -eq 1 ]]; then
  [[ -z "$MODEL" ]] && die "--pull needs --model <name>."
  c_cyan "==> Pulling ${MODEL}..."
  docker exec dgx-demo-ollama ollama pull "$MODEL"
fi

# 3. Resolve the model id (first local model if none given).
if [[ -z "$MODEL" ]]; then
  MODEL="$(curl -fsS "http://localhost:${PORT}/api/tags" \
    | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]+"' \
    | sed -E 's/.*"([^"]+)"$/\1/' | head -n1 || true)"
  [[ -z "$MODEL" ]] && die "No local model found. Pull one from the dashboard (Copilot hors-ligne)."
fi
c_green "==> Model: ${MODEL}"

# 4. Export the offline Copilot provider env.
export COPILOT_PROVIDER_TYPE="openai"
export COPILOT_PROVIDER_BASE_URL="$BASE_URL"
export COPILOT_PROVIDER_API_KEY="ollama"
export COPILOT_MODEL="$MODEL"
export COPILOT_OFFLINE="true"

echo
echo "  COPILOT_PROVIDER_TYPE     = ${COPILOT_PROVIDER_TYPE}"
echo "  COPILOT_PROVIDER_BASE_URL = ${COPILOT_PROVIDER_BASE_URL}"
echo "  COPILOT_MODEL             = ${COPILOT_MODEL}"
echo "  COPILOT_OFFLINE           = ${COPILOT_OFFLINE}"
echo

if [[ $NO_LAUNCH -eq 1 ]]; then
  c_cyan "Env set. Source this script to keep the vars, then run: copilot"
  (return 0 2>/dev/null) && return 0
  exit 0
fi

command -v copilot >/dev/null 2>&1 || die "copilot CLI not found. Install: npm install -g @github/copilot"
c_cyan "==> Launching GitHub Copilot CLI (offline)..."
exec copilot
