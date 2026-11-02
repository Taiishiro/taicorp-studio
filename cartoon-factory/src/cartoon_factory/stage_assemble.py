"""Étape 6 — MONTAGE : plans + voix (+ musique, sous-titres) → MP4 1080p et 9:16."""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

from cartoon_factory.cache import fingerprint
from cartoon_factory.context import EpisodeContext
from cartoon_factory.media import media_duration, run_ffmpeg, video_encode_args, write_silence
from cartoon_factory.models import Shot
from cartoon_factory.stage_animate import fit_to_duration, render_kenburns

log = logging.getLogger(__name__)
STAGE = "assemble"
TITLE_CARD_S = 2.5


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(entries: list[tuple[float, float, str]], width: int = 42) -> str:
    """entries = [(début, fin, texte)] → contenu .srt (2 lignes max par sous-titre)."""
    out = []
    for i, (start, end, text) in enumerate(entries, 1):
        if not text.strip():
            continue
        lines = textwrap.wrap(text.strip(), width=width)
        if len(lines) > 2:  # rééquilibre en 2 lignes
            lines = textwrap.wrap(text.strip(), width=max(width, len(text) // 2 + 2))[:2]
        out.append(f"{i}\n{_srt_time(start)} --> {_srt_time(end)}\n" + "\n".join(lines) + "\n")
    return "\n".join(out)


def _mux_shot(ctx: EpisodeContext, shot: Shot) -> tuple[Path, float]:
    """Vidéo du plan calée sur sa voix + audio muxé → final/shots/<plan>.mp4."""
    cfg = ctx.cfg
    anim, voice, dest = ctx.anim_path(shot), ctx.voice_path(shot), ctx.shot_video_path(shot)
    for p in (anim, voice):
        if not p.exists():
            raise FileNotFoundError(f"[{shot.id}] manquant : {p} (lance `animate` / `voice`)")
    target = media_duration(voice)
    fp = fingerprint(STAGE, anim.stat().st_mtime_ns, voice.stat().st_mtime_ns, cfg.video.__dict__)
    if ctx.force or not ctx.cache.is_fresh(STAGE, shot.id, fp, [dest]):
        fitted = dest.with_name(f"{shot.id}_fit.mp4")
        fit_to_duration(anim, fitted, target, cfg)
        run_ffmpeg(["-i", str(fitted), "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(dest)])
        fitted.unlink(missing_ok=True)
        ctx.cache.mark_done(STAGE, shot.id, fp, [dest], meta={"duration_s": target})
    return dest, target


def _title_card(ctx: EpisodeContext) -> tuple[Path, float]:
    """Carte-titre (question) avec un silence : même en réel, c'est du Pillow."""
    from cartoon_factory.placeholder import draw_title_card

    cfg = ctx.cfg
    png = ctx.final_dir / "shots" / "title.png"
    mp4 = ctx.final_dir / "shots" / "title.mp4"
    wav = ctx.final_dir / "shots" / "title.wav"
    if not mp4.exists():
        draw_title_card(png, width=cfg.video.width, height=cfg.video.height,
                        title=ctx.episode.title or ctx.episode.question,
                        subtitle=(ctx.episode.question
                                  if ctx.episode.title and ctx.episode.title != ctx.episode.question
                                  else ""))
        silent = mp4.with_name("title_v.mp4")
        render_kenburns(png, silent, "zoom_in", TITLE_CARD_S, cfg, zoom_max=1.04)
        write_silence(wav, TITLE_CARD_S, cfg.tts.sample_rate)
        run_ffmpeg(["-i", str(silent), "-i", str(wav), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(mp4)])
        silent.unlink(missing_ok=True)
    return mp4, TITLE_CARD_S


def run(ctx: EpisodeContext, title_card: bool = True) -> dict[str, Path]:
    cfg, ep = ctx.cfg, ctx.episode
    ctx.final_dir.mkdir(parents=True, exist_ok=True)
    parts: list[tuple[Path, float]] = []
    if title_card:
        parts.append(_title_card(ctx))
    srt_entries: list[tuple[float, float, str]] = []
    t = sum(d for _, d in parts)
    for shot in ep.shots:  # le montage prend toujours tous les plans, dans l'ordre
        path, dur = _mux_shot(ctx, shot)
        parts.append((path, dur))
        srt_entries.append((t + 0.05, t + dur - 0.05, shot.voice_text))
        t += dur

    outputs: dict[str, Path] = {}
    # Sous-titres
    srt = ctx.final_dir / f"{ep.id}.srt"
    srt.write_text(build_srt(srt_entries), encoding="utf-8")
    outputs["srt"] = srt

    # Concat (demuxer : mêmes codecs/résolution/fps partout → pas de ré-encodage vidéo)
    listing = ctx.final_dir / "concat.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p, _ in parts), encoding="utf-8")
    concat = ctx.final_dir / f"{ep.id}_concat.mp4"
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(concat)])

    # Master 16:9 : musique optionnelle + sous-titres (piste ou incrustés)
    master = ctx.final_dir / f"{ep.id}_1080p.mp4"
    args = ["-i", str(concat)]
    filters: list[str] = []
    maps = ["-map", "0:v:0"]
    music = cfg.resolve(cfg.music.file) if cfg.music.file else None
    if music and music.exists():
        args += ["-stream_loop", "-1", "-i", str(music)]
        fade_out = max(0.0, t - cfg.music.fade_s)
        filters.append(
            f"[1:a]volume={cfg.music.volume_db}dB,afade=t=in:d={cfg.music.fade_s},"
            f"afade=t=out:st={fade_out:.3f}:d={cfg.music.fade_s}[m];"
            f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        maps += ["-map", "[a]"]
    else:
        maps += ["-map", "0:a:0"]
    vcodec = ["-c:v", "copy"]
    if cfg.subtitles.enabled and cfg.subtitles.burn_in:
        srt_esc = str(srt.resolve()).replace(":", "\\:").replace("'", "\\'")
        filters.append(f"[0:v]subtitles='{srt_esc}':force_style='FontSize=20,Outline=1'[v]")
        maps[1] = "[v]"
        vcodec = video_encode_args(cfg.video.crf, cfg.video.preset)
    sub_args: list[str] = []
    if cfg.subtitles.enabled and not cfg.subtitles.burn_in:
        args += ["-i", str(srt)]
        idx = 2 if (music and music.exists()) else 1
        sub_args = ["-map", f"{idx}:s:0", "-c:s", "mov_text", "-metadata:s:s:0",
                    f"language={ep.language or 'fra'}"]
    fc = ["-filter_complex", ";".join(filters)] if filters else []
    run_ffmpeg([*args, *fc, *maps, *sub_args, *vcodec, "-c:a", "aac", "-b:a", "192k",
                "-t", f"{t:.3f}", str(master)])
    outputs["master"] = master

    # Variante verticale 9:16 : recadrage central puis mise à l'échelle 1080x1920
    if cfg.video.vertical_variant:
        vertical = ctx.final_dir / f"{ep.id}_9x16.mp4"
        vf = "crop=ih*9/16:ih,scale=1080:1920:flags=lanczos,format=yuv420p"
        run_ffmpeg(["-i", str(master), "-vf", vf, "-map", "0:v:0", "-map", "0:a:0",
                    *video_encode_args(cfg.video.crf, cfg.video.preset), "-c:a", "copy",
                    str(vertical)])
        outputs["vertical"] = vertical
    concat.unlink(missing_ok=True)
    log.info("montage terminé : %s (%.1fs)", master, t)
    return outputs
