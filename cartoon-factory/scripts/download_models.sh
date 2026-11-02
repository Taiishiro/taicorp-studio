#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Téléchargement des modèles dans $COMFY_DIR/models/… (idempotent : saute les
# fichiers déjà présents). Les URLs sont des VARIABLES à vérifier/compléter :
# certains dépôts Hugging Face demandent d'accepter une licence (Flux.1-dev)
# → exporter HF_TOKEN=hf_xxx. Les LoRA de style sont à choisir toi-même sur
# Civitai / Hugging Face (voir README § LoRA).
#
#   COMFY_DIR=~/ComfyUI ./scripts/download_models.sh [sdxl|flux|tooncrafter|wan|all]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
COMFY_DIR="${COMFY_DIR:-$HOME/ComfyUI}"
M="$COMFY_DIR/models"
WHAT="${1:-all}"

# ── URLs (à vérifier — les noms de fichiers doivent correspondre à config.yaml) ──
# SDXL base (6,9 Go) — dessins clés, le choix le plus sûr pour 16 Go
SDXL_CHECKPOINT_URL="${SDXL_CHECKPOINT_URL:-https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors}"
# Flux.1-dev GGUF Q5_K_S (~8,3 Go) + encodeurs — meilleur suivi de prompt, plus lent
FLUX_UNET_URL="${FLUX_UNET_URL:-https://huggingface.co/city96/FLUX.1-dev-gguf/resolve/main/flux1-dev-Q5_K_S.gguf}"
FLUX_CLIP_L_URL="${FLUX_CLIP_L_URL:-https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors}"
FLUX_T5_URL="${FLUX_T5_URL:-https://huggingface.co/city96/t5-v1_1-xxl-encoder-gguf/resolve/main/t5-v1_1-xxl-encoder-Q5_K_M.gguf}"
FLUX_VAE_URL="${FLUX_VAE_URL:-https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors}"
# ToonCrafter (~10 Go fp16 ; le node AIGODLIKE peut le convertir en fp8 au chargement)
TOONCRAFTER_URL="${TOONCRAFTER_URL:-https://huggingface.co/Doubiiu/ToonCrafter/resolve/main/model.ckpt}"
TOONCRAFTER_FILE="${TOONCRAFTER_FILE:-ToonCrafter_512_interp-fp16.safetensors}"
# Wan 2.2 I2V A14B, 2 experts GGUF Q4_K_M (~9 Go chacun, chargés l'un après l'autre)
WAN_HIGH_URL="${WAN_HIGH_URL:-https://huggingface.co/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/HighNoise/Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf}"
WAN_LOW_URL="${WAN_LOW_URL:-https://huggingface.co/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/LowNoise/Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf}"
WAN_CLIP_URL="${WAN_CLIP_URL:-https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors}"
WAN_VAE_URL="${WAN_VAE_URL:-https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors}"
WAN_CLIP_VISION_URL="${WAN_CLIP_VISION_URL:-https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors}"
# LoRA de style crayon : À COMPLÉTER (Civitai : "crayon", "children's book", "pencil sketch")
STYLE_LORA_URL="${STYLE_LORA_URL:-}"
STYLE_LORA_FILE="${STYLE_LORA_FILE:-crayon_style.safetensors}"

dl() {  # dl <url> <dest>
  local url="$1" dest="$2"
  if [ -z "$url" ]; then echo "⏭  $(basename "$dest") : URL vide, à compléter"; return; fi
  if [ -s "$dest" ]; then echo "✓  $(basename "$dest") déjà présent"; return; fi
  mkdir -p "$(dirname "$dest")"
  echo "⬇  $(basename "$dest")"
  local hdr=()
  [ -n "${HF_TOKEN:-}" ] && hdr=(--header "Authorization: Bearer $HF_TOKEN")
  if command -v aria2c >/dev/null; then
    aria2c -x 8 -s 8 -c "${hdr[@]}" -d "$(dirname "$dest")" -o "$(basename "$dest")" "$url"
  else
    curl -L --fail --retry 3 -C - "${hdr[@]}" -o "$dest" "$url"
  fi
}

case "$WHAT" in sdxl|all)
  dl "$SDXL_CHECKPOINT_URL" "$M/checkpoints/sd_xl_base_1.0.safetensors" ;;
esac
case "$WHAT" in flux|all)
  dl "$FLUX_UNET_URL"   "$M/unet/flux1-dev-Q5_K_S.gguf"
  dl "$FLUX_CLIP_L_URL" "$M/clip/clip_l.safetensors"
  dl "$FLUX_T5_URL"     "$M/clip/t5-v1_1-xxl-encoder-Q5_K_M.gguf"
  dl "$FLUX_VAE_URL"    "$M/vae/ae.safetensors" ;;
esac
case "$WHAT" in tooncrafter|all)
  dl "$TOONCRAFTER_URL" "$M/checkpoints/tooncrafter/$TOONCRAFTER_FILE" ;;
esac
case "$WHAT" in wan|all)
  dl "$WAN_HIGH_URL"        "$M/unet/wan2.2_i2v_high_noise_14B_Q4_K_M.gguf"
  dl "$WAN_LOW_URL"         "$M/unet/wan2.2_i2v_low_noise_14B_Q4_K_M.gguf"
  dl "$WAN_CLIP_URL"        "$M/clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
  dl "$WAN_VAE_URL"         "$M/vae/wan_2.1_vae.safetensors"
  dl "$WAN_CLIP_VISION_URL" "$M/clip_vision/clip_vision_h.safetensors" ;;
esac
case "$WHAT" in lora|all)
  dl "$STYLE_LORA_URL" "$M/loras/$STYLE_LORA_FILE" ;;
esac
echo "Terminé. Espace utilisé : $(du -sh "$M" 2>/dev/null | cut -f1)"
