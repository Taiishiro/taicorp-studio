"""Vérification par plan : extraire une image, mesurer, écrire un rapport.

Claude regarde ensuite les PNG de `checks/` (outil Read) et décide quels plans
relancer (`cartoon-factory reject s03 --reason "…"` puis `animate --shots s03`).
Les heuristiques ici attrapent les échecs grossiers : image noire/blanche,
clip trop court, fichiers manquants, voix trop longue pour le plan.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image, ImageStat

from cartoon_factory.context import EpisodeContext
from cartoon_factory.media import extract_frame, media_duration

log = logging.getLogger(__name__)


@dataclass
class ShotReport:
    id: str
    ok: bool = True
    frame: str = ""
    video_s: float = 0.0
    voice_s: float = 0.0
    brightness: float = 0.0
    contrast: float = 0.0
    issues: list[str] = field(default_factory=list)


def analyse_frame(png: Path) -> tuple[float, float]:
    """(luminance moyenne 0-255, écart-type) sur l'image en niveaux de gris."""
    with Image.open(png) as im:
        st = ImageStat.Stat(im.convert("L"))
    return float(st.mean[0]), float(st.stddev[0])


def check_shot(ctx: EpisodeContext, shot) -> ShotReport:
    rep = ShotReport(id=shot.id)
    anim, voice = ctx.anim_path(shot), ctx.voice_path(shot)
    for i in range(shot.keyframe_count):
        if not ctx.keyframe_path(shot, i).exists():
            rep.issues.append(f"dessin clé k{i} manquant")
    if not anim.exists():
        rep.issues.append("animation manquante")
    if not voice.exists():
        rep.issues.append("voix manquante")
    if rep.issues:
        rep.ok = False
        return rep
    rep.video_s = media_duration(anim)
    rep.voice_s = media_duration(voice)
    frame = extract_frame(anim, ctx.checks_dir / f"{shot.id}.png")
    rep.frame = str(frame)
    rep.brightness, rep.contrast = analyse_frame(frame)
    if rep.brightness < 25:
        rep.issues.append("image quasi noire")
    if rep.brightness > 245 or rep.contrast < 6:
        rep.issues.append("image vide / sans contraste")
    if rep.video_s < 1.0:
        rep.issues.append(f"clip trop court ({rep.video_s:.1f}s)")
    if rep.voice_s > shot.duration_s * 2:
        rep.issues.append(f"voix {rep.voice_s:.1f}s ≫ plan prévu {shot.duration_s}s")
    rep.ok = not rep.issues
    return rep


def run(ctx: EpisodeContext) -> list[ShotReport]:
    ctx.checks_dir.mkdir(parents=True, exist_ok=True)
    reports = [check_shot(ctx, s) for s in ctx.selected_shots()]
    (ctx.checks_dir / "report.json").write_text(
        json.dumps([asdict(r) for r in reports], ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["| plan | ok | vidéo | voix | lum. | contraste | problèmes |",
          "|---|---|---|---|---|---|---|"]
    for r in reports:
        md.append(f"| {r.id} | {'✅' if r.ok else '❌'} | {r.video_s:.1f}s | {r.voice_s:.1f}s | "
                  f"{r.brightness:.0f} | {r.contrast:.0f} | {'; '.join(r.issues)} |")
    (ctx.checks_dir / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return reports
