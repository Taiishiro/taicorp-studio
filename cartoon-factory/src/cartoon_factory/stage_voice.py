"""Étape 5 — VOIX : un wav normalisé par plan, durée réelle mémorisée."""

from __future__ import annotations

import logging
from pathlib import Path

from cartoon_factory.cache import fingerprint
from cartoon_factory.context import EpisodeContext
from cartoon_factory.media import media_duration, normalize_wav, write_silence
from cartoon_factory.tts import get_backend

log = logging.getLogger(__name__)
STAGE = "voice"


def run(ctx: EpisodeContext, backend_name: str | None = None) -> list[Path]:
    cfg = ctx.cfg
    name = backend_name or cfg.tts.backend
    backend = get_backend(name, cfg.tts)
    produced: list[Path] = []
    try:
        for shot in ctx.selected_shots():
            dest = ctx.voice_path(shot)
            fp = fingerprint(STAGE, shot.voice_text, backend.params(), cfg.tts.pause_after_s,
                             cfg.tts.sample_rate)
            if not ctx.force and ctx.cache.is_fresh(STAGE, shot.id, fp, [dest]):
                log.info("[%s] voix en cache", shot.id)
                continue
            log.info("[%s] voix (%s) : « %s »", shot.id, name, shot.voice_text[:50])
            if not shot.voice_text.strip():
                # Plan muet : silence de la durée cible du script.
                write_silence(dest, shot.duration_s, cfg.tts.sample_rate)
            else:
                raw = dest.with_name(f"{shot.id}_raw.wav")
                backend.synthesize(shot.voice_text, raw)
                normalize_wav(raw, dest, cfg.tts.sample_rate, pad_end_s=cfg.tts.pause_after_s)
                raw.unlink(missing_ok=True)
            dur = media_duration(dest)
            produced.append(dest)
            ctx.cache.mark_done(STAGE, shot.id, fp, [dest], meta={"duration_s": dur})
            # La durée réelle remplace la durée cible dans la suite du pipeline.
            if abs(dur - shot.duration_s) > 1.5:
                log.warning("[%s] voix de %.1fs pour un plan prévu à %.1fs", shot.id, dur,
                            shot.duration_s)
    finally:
        backend.release()
    return produced
