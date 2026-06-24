#!/usr/bin/env bash
# Install the optional Studio 3D dependencies into the backend venv.
#
#  - diffusers + transformers + accelerate : text -> image (SD-Turbo)
#  - TRELLIS.2 (trellis2 + o_voxel + native CUDA extensions) : image -> 3D
#
# We deliberately do NOT use the repo's own setup.sh: it relies on conda, the
# *system* pip (which is "externally-managed" here) and `sudo apt`. Instead we
# install everything straight into backend/.venv and build the native
# extensions with --no-build-isolation against the already-installed torch.
#
# TRELLIS.2 is officially tested on x86_64 A100/H100 with CUDA 12.4 / torch 2.6.
# On the DGX Spark (GB10 / Blackwell, aarch64, CUDA 13) some native extensions
# may fail to compile; each build step is isolated so a failure does not abort
# the rest, and the backend degrades gracefully if a piece is missing.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/backend/.venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

if [[ ! -x "$PIP" ]]; then
  echo "Backend venv introuvable ($VENV). Lancez d'abord scripts/start.sh." >&2
  exit 1
fi

step() { echo; echo "==> $*"; }
run()  { echo "    \$ $*"; "$@"; }
try()  { echo "    \$ $*"; if "$@"; then echo "    [ok]"; else echo "    [ÉCHEC] (on continue)"; fi; }

# Best-effort CUDA arch hint for the native builds (Blackwell GB10 = sm_121).
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-12.0;12.1}"
export MAX_JOBS="${MAX_JOBS:-$(nproc)}"

# --------------------------------------------------------------------------- #
step "1/4 · Texte -> Image (diffusers)"
try "$PIP" install --upgrade diffusers transformers accelerate safetensors

# --------------------------------------------------------------------------- #
step "2/4 · Clonage du dépôt TRELLIS.2"
TRELLIS_DIR="$ROOT/appdata/TRELLIS.2"
if [[ ! -d "$TRELLIS_DIR/.git" ]]; then
  run git clone --recursive https://github.com/microsoft/TRELLIS.2 "$TRELLIS_DIR"
else
  echo "    déjà présent: $TRELLIS_DIR"
  ( cd "$TRELLIS_DIR" && git submodule update --init --recursive ) || true
fi

# --------------------------------------------------------------------------- #
step "3/4 · Dépendances Python de base (dans le venv)"
try "$PIP" install \
  imageio imageio-ffmpeg tqdm easydict opencv-python-headless ninja \
  trimesh tensorboard pandas lpips zstandard kornia timm pybind11
try "$PIP" install \
  "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8"

# --------------------------------------------------------------------------- #
step "4/4 · Extensions natives CUDA (compilation — peut être longue)"
EXT="$ROOT/appdata/trellis_extensions"
mkdir -p "$EXT"

# o-voxel ships inside the repo (needed for GLB export).
if [[ -d "$TRELLIS_DIR/o-voxel" ]]; then
  try "$PIP" install "$TRELLIS_DIR/o-voxel" --no-build-isolation
fi

clone_build() {  # <name> <git-url> [git-ref]
  local name="$1" url="$2" ref="${3:-}"
  local dir="$EXT/$name"
  if [[ ! -d "$dir/.git" ]]; then
    if [[ -n "$ref" ]]; then
      try git clone --recursive -b "$ref" "$url" "$dir"
    else
      try git clone --recursive "$url" "$dir"
    fi
  fi
  [[ -d "$dir" ]] && try "$PIP" install "$dir" --no-build-isolation
}

clone_build nvdiffrast https://github.com/NVlabs/nvdiffrast.git v0.4.0
clone_build nvdiffrec  https://github.com/JeffreyXiang/nvdiffrec.git renderutils
clone_build CuMesh     https://github.com/JeffreyXiang/CuMesh.git
clone_build FlexGEMM   https://github.com/JeffreyXiang/FlexGEMM.git
# flash-attn is optional; the model can fall back to a slower attention.
try "$PIP" install flash-attn==2.7.3 --no-build-isolation

# --------------------------------------------------------------------------- #
step "Enregistrement du paquet trellis2 (importable depuis le venv)"
# trellis2 lives at the repo root and is NOT pip-installable (no setup.py);
# expose it on the venv path via a .pth file so `import trellis2` works.
SITE="$("$PY" -c 'import site; print(site.getsitepackages()[0])')"
echo "$TRELLIS_DIR" > "$SITE/trellis2_repo.pth"
echo "    -> $SITE/trellis2_repo.pth"

# --------------------------------------------------------------------------- #
step "Vérification"
"$PY" - <<'PYEOF'
import importlib.util as u
for mod in ("diffusers", "torch", "trellis2", "o_voxel"):
    print(f"  {mod:12s}: {'OK' if u.find_spec(mod) else 'MANQUANT'}")
PYEOF

echo
echo "Terminé. Redémarrez le backend (scripts/start.sh) puis rechargez les modèles"
echo "depuis l'onglet Studio 3D. Les modules 'MANQUANT' ci-dessus n'ont pas pu être"
echo "compilés sur cette machine (voir le README TRELLIS.2)."
