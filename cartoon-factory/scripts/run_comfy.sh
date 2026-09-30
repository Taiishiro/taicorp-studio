#!/usr/bin/env bash
# Lance ComfyUI avec les flags adaptés à une RTX 4060 Ti 16 Go.
#   --lowvram        : décharge agressivement (Wan 14B + T5 ne tiennent pas ensemble)
#   --preview-method : aperçus latents économiques
#   --listen 127.0.0.1 : jamais exposé sur le réseau (exécution de workflows = code)
set -euo pipefail
COMFY_DIR="${COMFY_DIR:-$HOME/ComfyUI}"
PORT="${COMFY_PORT:-8188}"
EXTRA="${COMFY_FLAGS:---lowvram --preview-method auto --disable-smart-memory}"
# PYTORCH_CUDA_ALLOC_CONF limite la fragmentation VRAM sur les longs clips.
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
cd "$COMFY_DIR"
# shellcheck disable=SC2086
exec .venv/bin/python main.py --listen 127.0.0.1 --port "$PORT" $EXTRA "$@"
