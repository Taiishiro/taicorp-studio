"""Pipeline complet en backend placeholder + voix silence : cache, durées, sorties."""

import json

from cartoon_factory import (
    stage_animate,
    stage_assemble,
    stage_check,
    stage_keyframes,
    stage_voice,
)
from cartoon_factory.cache import StageCache, fingerprint
from cartoon_factory.context import EpisodeContext
from cartoon_factory.media import media_duration
from cartoon_factory.stage_animate import kenburns_filter
from cartoon_factory.stage_assemble import build_srt
from tests.conftest import needs_ffmpeg


def test_cache_fresh_and_reject(tmp_path):
    c = StageCache(tmp_path / "cache.json")
    out = tmp_path / "a.png"
    fp = fingerprint("x", 1)
    assert not c.is_fresh("st", "s01", fp, [out])
    out.write_bytes(b"x")
    c.mark_done("st", "s01", fp, [out])
    assert c.is_fresh("st", "s01", fp, [out])
    assert not c.is_fresh("st", "s01", fingerprint("x", 2), [out])  # entrée modifiée
    c.reject("st", "s01", "moche")
    assert not c.is_fresh("st", "s01", fp, [out])
    assert json.loads((tmp_path / "cache.json").read_text())["st:s01"]["rejected"] is True


def test_kenburns_filter_shapes():
    f = kenburns_filter("zoom_in", 4.0, 24, 1920, 1080, zoom_max=1.1)
    assert "zoompan=z='1+(1.1-1)*on/95'" in f and "d=96" in f and "s=1920x1080" in f
    assert "(iw-iw/zoom)*(1-on/" in kenburns_filter("pan_left", 2, 10, 320, 180)
    assert "z='1.02'" in kenburns_filter("static", 2, 10, 320, 180)


def test_build_srt():
    long_text = "Bonjour les amis, aujourd'hui on parle du ciel bleu et du soleil."
    srt = build_srt([(0.0, 3.5, long_text), (3.5, 6.0, "")])
    assert srt.startswith("1\n00:00:00,000 --> 00:00:03,500\n")
    assert srt.count("\n\n") <= 1 and "2\n" not in srt  # l'entrée vide est ignorée
    assert max(len(line) for line in srt.splitlines()) <= 45


@needs_ffmpeg
def test_end_to_end_placeholder(small_cfg, example_episode, example_characters):
    ep = example_episode
    ep.shots = ep.shots[:3]  # s01 tooncrafter, s02 kenburns, s03 kenburns
    ctx = EpisodeContext(cfg=small_cfg, episode=ep, out_dir=small_cfg.resolve("output") / ep.id,
                         backend="placeholder", characters=example_characters)

    assert len(stage_keyframes.run(ctx)) == 4  # 2 + 1 + 1
    assert len(stage_voice.run(ctx)) == 3
    assert len(stage_animate.run(ctx)) == 3
    # La vidéo suit la voix : durées égales à la frame près.
    for shot in ep.shots:
        v, a = media_duration(ctx.anim_path(shot)), media_duration(ctx.voice_path(shot))
        assert abs(v - a) < 0.2, (shot.id, v, a)

    outputs = stage_assemble.run(ctx)
    assert outputs["master"].exists() and outputs["vertical"].exists()
    assert outputs["srt"].read_text(encoding="utf-8").count("-->") == 3
    total = sum(media_duration(ctx.voice_path(s)) for s in ep.shots) + 2.5  # + carte-titre
    assert abs(media_duration(outputs["master"]) - total) < 0.5

    reports = stage_check.run(ctx)
    assert all(r.ok for r in reports), [r.issues for r in reports]
    assert (ctx.checks_dir / "s01.png").exists()

    # Second passage : tout est en cache, rien n'est régénéré.
    assert stage_keyframes.run(ctx) == [] and stage_voice.run(ctx) == []
    assert stage_animate.run(ctx) == []
    # Un plan rejeté est refait, les autres non.
    ctx.cache.reject("animate", "s02", "test")
    assert [p.name for p in stage_animate.run(ctx)] == ["s02.mp4"]
    # --shots restreint la sélection ; --force ignore le cache.
    ctx.only_shots, ctx.force = {"s03"}, True
    assert [p.name for p in stage_keyframes.run(ctx)] == ["s03_k0.png"]
