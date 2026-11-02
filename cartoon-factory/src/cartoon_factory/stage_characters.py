"""Étape 2 — PERSONNAGES.

  * `ensure_sheets()`   : vérifie que chaque perso de l'épisode a une fiche ;
  * `reference_image()` : génère l'image de référence d'une fiche (cohérence) ;
  * `build_dataset()`   : 15-30 dessins variés + captions pour entraîner un LoRA
                          perso (voir scripts/train_character_lora.sh).
"""

from __future__ import annotations

import logging
from pathlib import Path

from cartoon_factory.config import Config
from cartoon_factory.models import Character, ValidationError
from cartoon_factory.prompts import build_negative, build_prompt

log = logging.getLogger(__name__)

# Variations de poses/expressions pour le dataset LoRA (anglais : prompts SDXL).
DATASET_VARIATIONS = [
    "standing, front view, neutral expression", "standing, three-quarter view, smiling",
    "waving hand, happy", "pointing up, curious expression", "sitting on the grass",
    "walking to the right, side view", "jumping with joy", "thinking, hand on chin",
    "surprised, wide eyes, open mouth", "laughing, eyes closed", "holding a magnifying glass",
    "looking through a telescope", "reading a book", "holding an umbrella",
    "sleeping, night, moon", "running, motion", "close-up portrait, smiling",
    "close-up portrait, surprised", "back view, looking at the horizon",
    "arms crossed, confident", "shrugging, confused", "cheering, arms up",
    "sitting at a desk", "under a tree", "on a hill, wind", "holding a balloon",
    "with a flashlight in the dark", "splashing in a puddle", "looking at the sky",
    "eating an apple",
]


def ensure_sheets(character_ids: list[str], characters: dict[str, Character]) -> None:
    missing = [c for c in character_ids if c not in characters]
    if missing:
        raise ValidationError([f"fiche perso manquante : {m} (characters/{m}.json)"
                               for m in missing])


def reference_image(ch: Character, cfg: Config, dest: Path, backend: str = "comfy") -> Path:
    """Image de référence pleine page (à regarder pour valider le design)."""
    prompt = build_prompt(cfg, "full body reference sheet, front view, plain white background",
                          characters=[ch])
    negative = build_negative(cfg, characters=[ch])
    if backend == "placeholder":
        from cartoon_factory.placeholder import draw_keyframe

        return draw_keyframe(dest, width=cfg.keyframe.width, height=cfg.keyframe.height,
                             visual=ch.description, seed=ch.seed,
                             characters=[{"name": ch.name, "palette": ch.palette}],
                             label=ch.id)
    from cartoon_factory.stage_keyframes import render_with_comfy

    return render_with_comfy(cfg, prompt, negative, ch.seed, dest, characters=[ch])


def build_dataset(ch: Character, cfg: Config, dest_dir: Path, count: int = 20,
                  backend: str = "comfy") -> list[Path]:
    """Génère `count` dessins du perso + un .txt de caption par image (format kohya)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    trigger = ch.lora_trigger or f"{ch.id}_character"
    outputs: list[Path] = []
    for i in range(count):
        variation = DATASET_VARIATIONS[i % len(DATASET_VARIATIONS)]
        img = dest_dir / f"{ch.id}_{i:03d}.png"
        caption = dest_dir / f"{ch.id}_{i:03d}.txt"
        if not img.exists():
            if backend == "placeholder":
                from cartoon_factory.placeholder import draw_keyframe

                draw_keyframe(img, width=cfg.keyframe.width, height=cfg.keyframe.height,
                              visual=f"{ch.description} {variation}", seed=ch.seed + i,
                              characters=[{"name": ch.name, "palette": ch.palette}],
                              variant=i % 2)
            else:
                from cartoon_factory.stage_keyframes import render_with_comfy

                prompt = build_prompt(cfg, variation, characters=[ch])
                negative = build_negative(cfg, characters=[ch])
                render_with_comfy(cfg, prompt, negative, ch.seed + i, img, characters=[ch],
                                  use_character_lora=False)  # on entraîne : pas de LoRA perso
        # Caption : trigger + description fixe + variation (le style vient du LoRA style)
        caption.write_text(f"{trigger}, {ch.prompt}, {variation}\n", encoding="utf-8")
        outputs.append(img)
        log.info("dataset %s : %d/%d", ch.id, i + 1, count)
    return outputs
