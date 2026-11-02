"""Étape 4 — ANIMATION : un clip vidéo par plan.

  * kenburns    : image fixe + zoom/pan ffmpeg (durée = durée de la voix) ;
  * tooncrafter : 2 dessins clés → interpolation (ComfyUI) ;
  * wan_i2v     : 1 dessin clé → clip Wan 2.2 (ComfyUI, réglages 16 Go).

En backend `placeholder`, ToonCrafter est simulé par un fondu enchaîné entre
les 2 dessins et Wan par un Ken Burns plus marqué : le reste du pipeline
(cache, retiming, montage) est exercé à l'identique.

Le clip final `anims/<plan>.mp4` est toujours à la résolution/fps de sortie ;
`fit_to_duration()` (utilisé au montage) le cale sur la voix.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from cartoon_factory.cache import fingerprint
from cartoon_factory.comfy import ComfyClient, fill_workflow, load_workflow
from cartoon_factory.config import Config
from cartoon_factory.context import EpisodeContext
from cartoon_factory.media import media_duration, run_ffmpeg, video_encode_args
from cartoon_factory.models import Shot

log = logging.getLogger(__name__)
STAGE = "animate"


# ── Ken Burns (ffmpeg zoompan) ───────────────────────────────────────────────

def kenburns_filter(camera: str, duration_s: float, fps: int, width: int, height: int,
                    zoom_max: float = 1.10, pan_fraction: float = 0.08) -> str:
    """Filtre zoompan pour un mouvement de caméra donné.

    L'image est d'abord suréchantillonnée (largeur 4×) pour éviter le tremblement
    caractéristique de zoompan sur les petites images.
    """
    frames = max(2, int(round(duration_s * fps)))
    d = frames - 1  # `on` va de 0 à frames-1
    zoom_max = max(1.001, zoom_max)
    zp = 1 + pan_fraction * 2  # zoom constant nécessaire pour avoir de la marge de pan
    center = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if camera == "zoom_in":
        z = f"z='1+({zoom_max}-1)*on/{d}':{center}"
    elif camera == "zoom_out":
        z = f"z='{zoom_max}-({zoom_max}-1)*on/{d}':{center}"
    elif camera == "pan_left":
        z = f"z='{zp}':x='(iw-iw/zoom)*(1-on/{d})':y='ih/2-(ih/zoom/2)'"
    elif camera == "pan_right":
        z = f"z='{zp}':x='(iw-iw/zoom)*on/{d}':y='ih/2-(ih/zoom/2)'"
    else:  # static : micro-zoom pour éviter l'image totalement figée
        z = f"z='1.02':{center}"
    return (f"scale={width * 4}:-2,zoompan={z}:d={frames}:s={width}x{height}:fps={fps},"
            f"format=yuv420p")


def render_kenburns(image: Path, dest: Path, camera: str, duration_s: float, cfg: Config,
                    zoom_max: float | None = None) -> Path:
    kb = cfg.animation.kenburns
    vf = kenburns_filter(camera, duration_s, cfg.video.fps, cfg.video.width, cfg.video.height,
                         zoom_max=zoom_max or float(kb.get("zoom_max", 1.10)),
                         pan_fraction=float(kb.get("pan_fraction", 0.08)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-loop", "1", "-framerate", str(cfg.video.fps), "-i", str(image),
                "-vf", vf, "-t", f"{duration_s:.3f}", "-r", str(cfg.video.fps),
                *video_encode_args(cfg.video.crf, cfg.video.preset), "-an", str(dest)])
    return dest


def render_crossfade(img_a: Path, img_b: Path, dest: Path, duration_s: float, cfg: Config) -> Path:
    """Placeholder ToonCrafter : fondu A→B sur toute la durée."""
    fps, W, H = cfg.video.fps, cfg.video.width, cfg.video.height
    half = max(0.5, duration_s / 2)
    fade = max(0.3, duration_s - 1.0)
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-loop", "1", "-framerate", str(fps), "-t", f"{half + fade:.3f}", "-i", str(img_a),
        "-loop", "1", "-framerate", str(fps), "-t", f"{half + fade:.3f}", "-i", str(img_b),
        "-filter_complex",
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:-1:-1:color=white,"
        f"setsar=1[a];[1:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:-1:-1:color=white,setsar=1[b];"
        f"[a][b]xfade=transition=fade:duration={fade:.3f}:offset={half - fade / 2:.3f},"
        f"format=yuv420p[v]",
        "-map", "[v]", "-t", f"{duration_s:.3f}", "-r", str(fps),
        *video_encode_args(cfg.video.crf, cfg.video.preset), "-an", str(dest)])
    return dest


# ── Post-traitement commun ───────────────────────────────────────────────────

def upscale_to_output(src: Path, dest: Path, cfg: Config) -> Path:
    """Met un clip ComfyUI (480p/320p) au format de sortie : scale + pad + fps."""
    W, H, fps = cfg.video.width, cfg.video.height, cfg.video.fps
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
          f"pad={W}:{H}:-1:-1:color=white,fps={fps},format=yuv420p")
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-i", str(src), "-vf", vf, *video_encode_args(cfg.video.crf, cfg.video.preset),
                "-an", str(dest)])
    return dest


def fit_to_duration(src: Path, dest: Path, target_s: float, cfg: Config,
                    max_stretch: float = 1.6) -> Path:
    """Cale un clip sur la durée de la voix : ralenti/accéléré jusqu'à ×1.6,
    puis gel de la dernière image si la voix est encore plus longue.
    C'est la vidéo qui s'adapte à l'audio, jamais l'inverse."""
    src_s = media_duration(src)
    ratio = target_s / max(src_s, 0.01)
    stretch = min(max(ratio, 1 / max_stretch), max_stretch)
    vf = f"setpts={stretch:.5f}*PTS,fps={cfg.video.fps}"
    stretched_s = src_s * stretch
    if target_s > stretched_s + 0.02:
        vf += f",tpad=stop_mode=clone:stop_duration={target_s - stretched_s:.3f}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-i", str(src), "-vf", vf, "-t", f"{target_s:.3f}",
                *video_encode_args(cfg.video.crf, cfg.video.preset), "-an", str(dest)])
    return dest


# ── ComfyUI : ToonCrafter et Wan ─────────────────────────────────────────────

def _comfy_video(ctx: EpisodeContext, client: ComfyClient, shot: Shot, method: str,
                 seed: int, raw_dest: Path) -> Path:
    cfg = ctx.cfg
    params = getattr(cfg.animation, method)
    template = load_workflow(cfg.workflow_path(method))
    values = {
        "IMAGE_START": client.upload_image(ctx.keyframe_path(shot, 0)),
        "PROMPT": (shot.motion or shot.visual), "NEGATIVE": cfg.style.negative_prompt,
        "SEED": seed, "PREFIX": f"cartoon-factory/{shot.id}",
        **{k.upper(): v for k, v in params.items()},
        "HALF_STEPS": int(params.get("steps", 20)) // 2,  # bascule high→low noise (Wan 2.2)
        **{k.upper(): v for k, v in cfg.comfy.models.items()},
    }
    if method == "tooncrafter":
        values["IMAGE_END"] = client.upload_image(ctx.keyframe_path(shot, 1))
    workflow = fill_workflow(template, values)
    outputs = client.run(workflow, raw_dest.parent, raw_dest.stem)
    videos = [o for o in outputs if o.suffix.lower() in (".mp4", ".webm", ".mov", ".gif")]
    if not videos:
        raise RuntimeError(f"[{shot.id}] {method} n'a produit aucune vidéo : {outputs}")
    if videos[0] != raw_dest:
        shutil.move(str(videos[0]), str(raw_dest))
    return raw_dest


# ── Étape ────────────────────────────────────────────────────────────────────

def run(ctx: EpisodeContext) -> list[Path]:
    cfg = ctx.cfg
    produced: list[Path] = []
    client = None
    if ctx.backend == "comfy":
        client = ComfyClient(cfg.comfy.url, cfg.comfy.timeout_s, cfg.comfy.poll_interval_s)
    index_of = {s.id: i for i, s in enumerate(ctx.episode.shots)}

    for shot in ctx.selected_shots():
        method = shot.method or cfg.animation.default_method
        keyframes = [ctx.keyframe_path(shot, i) for i in range(shot.keyframe_count)]
        missing = [k for k in keyframes if not k.exists()]
        if missing:
            raise FileNotFoundError(f"[{shot.id}] dessins clés manquants : {missing} "
                                    "(lance d'abord `keyframes`)")
        duration = ctx.voice_duration(shot)
        dest = ctx.anim_path(shot)
        seed = cfg.keyframe.seed_base + index_of[shot.id] * 100 + 50
        kf_meta = ctx.cache.get_meta("keyframes", shot.id)
        params = getattr(cfg.animation, method, {})
        # Pour kenburns la durée fait partie de l'empreinte (le clip est rendu à la
        # bonne longueur) ; pour ComfyUI, non : c'est le montage qui recale.
        fp = fingerprint(STAGE, ctx.backend, method, shot.camera, shot.motion, params,
                         kf_meta.get("seeds"), kf_meta.get("prompts"),
                         cfg.video.__dict__, round(duration, 2) if method == "kenburns" else None)
        if not ctx.force and ctx.cache.is_fresh(STAGE, shot.id, fp, [dest]):
            log.info("[%s] animation en cache", shot.id)
            continue

        log.info("[%s] animation %s (%s), %.1fs", shot.id, method, ctx.backend, duration)
        if method == "kenburns":
            render_kenburns(keyframes[0], dest, shot.camera, duration, cfg)
        elif ctx.backend == "placeholder":
            if method == "tooncrafter":
                render_crossfade(keyframes[0], keyframes[1], dest, duration, cfg)
            else:  # wan_i2v simulé : mouvement de caméra plus ample
                render_kenburns(keyframes[0], dest, shot.camera or "zoom_in", duration, cfg,
                                zoom_max=1.25)
        else:
            raw = ctx.anims_dir / f"{shot.id}_raw.mp4"
            _comfy_video(ctx, client, shot, method, seed, raw)  # type: ignore[arg-type]
            upscale_to_output(raw, dest, cfg)
        produced.append(dest)
        ctx.cache.mark_done(STAGE, shot.id, fp, [dest],
                            meta={"method": method, "seed": seed, "duration_s": duration})

    if client and cfg.comfy.free_vram_between_stages:
        client.free_vram()
    return produced
