"""Étape 3 — DESSINS CLÉS (1 ou 2 images par plan via ComfyUI, ou placeholder)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from cartoon_factory.cache import fingerprint
from cartoon_factory.comfy import ComfyClient, bypass_empty_loras, fill_workflow, load_workflow
from cartoon_factory.config import Config
from cartoon_factory.context import EpisodeContext
from cartoon_factory.models import Character, Shot
from cartoon_factory.prompts import build_negative, build_prompt

log = logging.getLogger(__name__)
STAGE = "keyframes"


def shot_seed(cfg: Config, shot_index: int, kf_index: int, explicit: int | None) -> int:
    """Seed reproductible : base + 100·plan + keyframe, sauf seed explicite."""
    if explicit is not None:
        return explicit
    return cfg.keyframe.seed_base + shot_index * 100 + kf_index


def keyframe_prompts(shot: Shot) -> list[str]:
    """Prompts des dessins clés : ceux du script, sinon la description visuelle."""
    prompts = [k.prompt for k in shot.keyframes if k.prompt.strip()]
    if not prompts:
        prompts = [shot.visual]
    if shot.keyframe_count == 2 and len(prompts) == 1:
        prompts.append(prompts[0] + ", " + (shot.motion or "slightly different pose"))
    return prompts[:shot.keyframe_count]


def render_with_comfy(cfg: Config, prompt: str, negative: str, seed: int, dest: Path,
                      characters: list[Character] | None = None,
                      use_character_lora: bool = True, client: ComfyClient | None = None) -> Path:
    """Remplit le workflow keyframe, l'exécute et range l'image dans `dest`."""
    client = client or ComfyClient(cfg.comfy.url, cfg.comfy.timeout_s, cfg.comfy.poll_interval_s)
    template = load_workflow(cfg.workflow_path("keyframe"))
    char_lora = ""
    char_weight = 0.9
    if use_character_lora:
        for ch in characters or []:
            if ch.lora_file:
                char_lora, char_weight = ch.lora_file, ch.lora_weight
                break  # le workflow ne prévoit qu'un LoRA perso : le premier gagne
    values = {
        "PROMPT": prompt, "NEGATIVE": negative, "SEED": int(seed),
        "STEPS": cfg.keyframe.steps, "CFG": cfg.keyframe.cfg,
        "WIDTH": cfg.keyframe.width, "HEIGHT": cfg.keyframe.height,
        "SAMPLER": cfg.keyframe.sampler, "SCHEDULER": cfg.keyframe.scheduler,
        "STYLE_LORA": cfg.style.lora.file, "STYLE_LORA_WEIGHT": cfg.style.lora.weight,
        "CHAR_LORA": char_lora, "CHAR_LORA_WEIGHT": char_weight,
        "PREFIX": f"cartoon-factory/{dest.stem}",
        **{k.upper(): v for k, v in cfg.comfy.models.items()},
    }
    workflow = bypass_empty_loras(fill_workflow(template, values))
    outputs = client.run(workflow, dest.parent, dest.stem)
    if outputs[0] != dest:
        shutil.move(str(outputs[0]), str(dest))
    return dest


def run(ctx: EpisodeContext) -> list[Path]:
    """Génère les dessins clés manquants/périmés des plans sélectionnés."""
    cfg = ctx.cfg
    produced: list[Path] = []
    client = None
    if ctx.backend == "comfy":
        client = ComfyClient(cfg.comfy.url, cfg.comfy.timeout_s, cfg.comfy.poll_interval_s)
    index_of = {s.id: i for i, s in enumerate(ctx.episode.shots)}

    for shot in ctx.selected_shots():
        chars = ctx.shot_characters(shot)
        prompts = keyframe_prompts(shot)
        outputs = [ctx.keyframe_path(shot, i) for i in range(len(prompts))]
        seeds = [shot_seed(cfg, index_of[shot.id], i,
                           shot.keyframes[i].seed if i < len(shot.keyframes) else None)
                 for i in range(len(prompts))]
        full_prompts = [build_prompt(cfg, p, chars) for p in prompts]
        negative = build_negative(cfg, chars)
        fp = fingerprint(STAGE, ctx.backend, full_prompts, negative, seeds,
                         cfg.keyframe.__dict__, cfg.style.lora.__dict__,
                         [(c.id, c.lora) for c in chars])
        if not ctx.force and ctx.cache.is_fresh(STAGE, shot.id, fp, outputs):
            log.info("[%s] dessins clés en cache", shot.id)
            continue

        for i, (prompt, dest, seed) in enumerate(zip(full_prompts, outputs, seeds, strict=True)):
            log.info("[%s] dessin clé %d/%d (%s)", shot.id, i + 1, len(outputs), ctx.backend)
            if ctx.backend == "placeholder":
                from cartoon_factory.placeholder import draw_keyframe

                draw_keyframe(dest, width=cfg.keyframe.width, height=cfg.keyframe.height,
                              visual=shot.visual + " " + prompts[i], seed=seed,
                              characters=[{"name": c.name, "palette": c.palette} for c in chars],
                              variant=i, label=f"{shot.id} k{i}")
            else:
                render_with_comfy(cfg, prompt, negative, seed, dest, chars, client=client)
            produced.append(dest)
        ctx.cache.mark_done(STAGE, shot.id, fp, outputs,
                            meta={"prompts": full_prompts, "seeds": seeds})

    if client and cfg.comfy.free_vram_between_stages:
        client.free_vram()
    return produced
