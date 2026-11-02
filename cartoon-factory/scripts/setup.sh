#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# cartoon-factory — installation ComfyUI + custom nodes + environnement Python.
# Idempotent : relançable sans risque (git pull si déjà cloné, pip -U).
#
# Cible : WSL2 Ubuntu 22.04/24.04, RTX 4060 Ti 16 Go, driver NVIDIA Windows
# récent (CUDA 12.x visible via `nvidia-smi` dans WSL).
#
#   COMFY_DIR=~/ComfyUI ./scripts/setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMFY_DIR="${COMFY_DIR:-$HOME/ComfyUI}"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu124}"
PYTHON="${PYTHON:-python3}"

log() { printf '\033[1;34m▶ %s\033[0m\n' "$*"; }

# ── 0. Paquets système ───────────────────────────────────────────────────────
log "Paquets système (git, ffmpeg, espeak-ng, python venv)"
if command -v apt-get >/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq git git-lfs ffmpeg espeak-ng python3-venv python3-pip aria2 \
    libgl1 libglib2.0-0 >/dev/null
fi

if ! command -v nvidia-smi >/dev/null; then
  echo "⚠️  nvidia-smi introuvable : installe le driver NVIDIA côté Windows (le driver WSL est inclus)."
fi

# ── 1. ComfyUI ───────────────────────────────────────────────────────────────
if [ -d "$COMFY_DIR/.git" ]; then
  log "ComfyUI déjà présent → git pull"
  git -C "$COMFY_DIR" pull --ff-only
else
  log "Clone de ComfyUI dans $COMFY_DIR"
  git clone https://github.com/comfyanonymous/ComfyUI "$COMFY_DIR"
fi

# ── 2. venv ComfyUI + PyTorch CUDA ───────────────────────────────────────────
if [ ! -d "$COMFY_DIR/.venv" ]; then
  log "Création du venv ComfyUI"
  "$PYTHON" -m venv "$COMFY_DIR/.venv"
fi
# shellcheck disable=SC1091
source "$COMFY_DIR/.venv/bin/activate"
pip install -q -U pip wheel
log "PyTorch CUDA ($TORCH_INDEX)"
pip install -q torch torchvision torchaudio --index-url "$TORCH_INDEX"
log "Dépendances ComfyUI"
pip install -q -r "$COMFY_DIR/requirements.txt"

# ── 3. Custom nodes ──────────────────────────────────────────────────────────
declare -A NODES=(
  [ComfyUI-Manager]=https://github.com/ltdrdata/ComfyUI-Manager
  [ComfyUI-GGUF]=https://github.com/city96/ComfyUI-GGUF
  [ComfyUI-KJNodes]=https://github.com/kijai/ComfyUI-KJNodes
  [ComfyUI-VideoHelperSuite]=https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
  [ComfyUI-ToonCrafter]=https://github.com/AIGODLIKE/ComfyUI-ToonCrafter
)
mkdir -p "$COMFY_DIR/custom_nodes"
for name in "${!NODES[@]}"; do
  dest="$COMFY_DIR/custom_nodes/$name"
  if [ -d "$dest/.git" ]; then
    log "custom node $name → git pull"
    git -C "$dest" pull --ff-only || true
  else
    log "custom node $name → clone"
    git clone --depth 1 "${NODES[$name]}" "$dest"
  fi
  if [ -f "$dest/requirements.txt" ]; then
    pip install -q -r "$dest/requirements.txt" || echo "⚠️  requirements de $name en échec (souvent bénin)"
  fi
done

# Workflows Wan 2.2 low-VRAM de référence (documentation, pas des nodes)
if [ ! -d "$HERE/vendor/ComfyUI-Wan2.2-workflow" ]; then
  log "Workflows de référence Wan 2.2 (Cordux) → vendor/"
  mkdir -p "$HERE/vendor"
  git clone --depth 1 https://github.com/Cordux/ComfyUI-Wan2.2-workflow "$HERE/vendor/ComfyUI-Wan2.2-workflow" || true
fi

# ── 4. Dossiers modèles + sorties ────────────────────────────────────────────
mkdir -p "$COMFY_DIR/models/"{checkpoints,loras,unet,clip,vae,clip_vision,diffusion_models} \
         "$COMFY_DIR/models/checkpoints/tooncrafter" \
         "$COMFY_DIR/output/cartoon-factory" "$COMFY_DIR/input/cartoon-factory"
deactivate

# ── 5. venv de l'orchestrateur (léger, séparé de ComfyUI) ────────────────────
log "venv cartoon-factory ($HERE/.venv)"
if [ ! -d "$HERE/.venv" ]; then "$PYTHON" -m venv "$HERE/.venv"; fi
"$HERE/.venv/bin/pip" install -q -U pip
"$HERE/.venv/bin/pip" install -q -e "$HERE[dev,ffmpeg]"
if [ "${WITH_KOKORO:-1}" = "1" ]; then
  log "TTS Kokoro (CPU) — WITH_KOKORO=0 pour sauter"
  "$HERE/.venv/bin/pip" install -q "kokoro>=0.9" soundfile "misaki[fr]" || echo "⚠️  Kokoro non installé"
fi
if [ "${WITH_XTTS:-0}" = "1" ]; then
  log "TTS XTTS-v2 (Coqui) — lourd"
  "$HERE/.venv/bin/pip" install -q TTS || echo "⚠️  Coqui TTS non installé"
fi
if [ "${WITH_MCP:-1}" = "1" ]; then
  log "Serveur MCP ComfyUI pour Claude Code (comfy-mcp)"
  "$HERE/.venv/bin/pip" install -q comfy-mcp || echo "⚠️  comfy-mcp non installé (pip install comfy-mcp)"
fi

# Fiches perso de départ
mkdir -p "$HERE/characters"
cp -n "$HERE"/examples/ciel-bleu/characters/*.json "$HERE/characters/" 2>/dev/null || true

cat <<MSG

✅ Installation terminée.
   ComfyUI : $COMFY_DIR   (lancer : scripts/run_comfy.sh)
   Modèles : scripts/download_models.sh   (à compléter avec tes URLs)
   Test sans GPU : .venv/bin/cartoon-factory run --episode examples/ciel-bleu/episode.json \\
                     --backend placeholder --tts espeak
MSG
