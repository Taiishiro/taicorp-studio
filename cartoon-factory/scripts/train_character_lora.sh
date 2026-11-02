#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# (Optionnel) Entraînement d'un LoRA personnage SDXL avec kohya sd-scripts,
# à partir du dataset généré par :
#   cartoon-factory characters --episode … --dataset 24
#   → characters/datasets/<perso>/<perso>_000.png + .txt (captions)
#
# Réglages pour 16 Go : réseau dim 16, batch 1, gradient checkpointing, fp16,
# 1 200 pas (~25-40 min sur 4060 Ti). Résultat : ComfyUI/models/loras/<perso>.safetensors
#
#   ./scripts/train_character_lora.sh pilou [steps]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHAR="${1:?usage: $0 <id-perso> [steps]}"
STEPS="${2:-1200}"
COMFY_DIR="${COMFY_DIR:-$HOME/ComfyUI}"
KOHYA_DIR="${KOHYA_DIR:-$HOME/sd-scripts}"
BASE_CKPT="${BASE_CKPT:-$COMFY_DIR/models/checkpoints/sd_xl_base_1.0.safetensors}"
DATASET="$HERE/characters/datasets/$CHAR"
WORK="$HERE/characters/datasets/_train_$CHAR"

[ -d "$DATASET" ] || { echo "dataset absent : $DATASET (génère-le d'abord)"; exit 1; }

# kohya sd-scripts (branche sdxl) — installé une fois
if [ ! -d "$KOHYA_DIR" ]; then
  git clone https://github.com/kohya-ss/sd-scripts "$KOHYA_DIR"
  python3 -m venv "$KOHYA_DIR/.venv"
  "$KOHYA_DIR/.venv/bin/pip" install -q -U pip
  "$KOHYA_DIR/.venv/bin/pip" install -q torch torchvision --index-url https://download.pytorch.org/whl/cu124
  "$KOHYA_DIR/.venv/bin/pip" install -q -r "$KOHYA_DIR/requirements.txt" xformers bitsandbytes
fi

# kohya attend  <work>/<repeats>_<trigger>/ ; 10 répétitions × ~24 images
TRIGGER="$(python3 -c "import json;print(json.load(open('$HERE/characters/$CHAR.json')).get('lora',{}).get('trigger') or '${CHAR}_character')")"
rm -rf "$WORK"; mkdir -p "$WORK/img/10_$TRIGGER" "$WORK/out"
cp "$DATASET"/*.png "$DATASET"/*.txt "$WORK/img/10_$TRIGGER/"

cd "$KOHYA_DIR"
.venv/bin/accelerate launch --num_cpu_threads_per_process 4 sdxl_train_network.py \
  --pretrained_model_name_or_path="$BASE_CKPT" \
  --train_data_dir="$WORK/img" --output_dir="$WORK/out" --output_name="$CHAR" \
  --resolution=1024,1024 --enable_bucket --min_bucket_reso=512 --max_bucket_reso=1024 \
  --network_module=networks.lora --network_dim=16 --network_alpha=8 \
  --learning_rate=1e-4 --unet_lr=1e-4 --text_encoder_lr=5e-5 --lr_scheduler=cosine \
  --optimizer_type=AdamW8bit --train_batch_size=1 --max_train_steps="$STEPS" \
  --mixed_precision=fp16 --save_precision=fp16 --gradient_checkpointing --xformers \
  --cache_latents --cache_latents_to_disk --caption_extension=.txt --shuffle_caption \
  --keep_tokens=1 --noise_offset=0.03 --min_snr_gamma=5 --save_model_as=safetensors \
  --no_half_vae --lowram

cp "$WORK/out/$CHAR.safetensors" "$COMFY_DIR/models/loras/$CHAR.safetensors"
echo "✅ LoRA → $COMFY_DIR/models/loras/$CHAR.safetensors"
echo "   Dans characters/$CHAR.json : \"lora\": {\"file\": \"$CHAR.safetensors\", \"weight\": 0.9, \"trigger\": \"$TRIGGER\"}"
