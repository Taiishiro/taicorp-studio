"""CLI `cartoon-factory` (ou `python -m cartoon_factory`).

    cartoon-factory brief "Pourquoi le ciel est bleu ?"      # consignes pour Claude
    cartoon-factory new   "Pourquoi le ciel est bleu ?"      # squelette episode.json
    cartoon-factory validate  --episode examples/ciel-bleu/episode.json
    cartoon-factory keyframes --episode … [--shots s01,s02] [--force] [--backend placeholder]
    cartoon-factory voice / animate / assemble / check  (mêmes options)
    cartoon-factory run --episode …                         # tout enchaîner
    cartoon-factory reject s03 --episode … --reason "bras déformé"
    cartoon-factory status --episode …
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from cartoon_factory import __version__
from cartoon_factory.config import Config, load_config
from cartoon_factory.context import EpisodeContext
from cartoon_factory.models import Episode, ValidationError, load_characters

log = logging.getLogger("cartoon_factory")


def _ctx(args: argparse.Namespace, cfg: Config) -> EpisodeContext:
    if not args.episode:
        sys.exit("--episode <chemin/episode.json> est requis")
    ep = Episode.load(args.episode)
    out_dir = Path(args.out) if args.out else cfg.resolve(cfg.output_dir) / ep.id
    shots = {s.strip() for s in args.shots.split(",") if s.strip()} if args.shots else set()
    characters = load_characters(cfg.resolve(cfg.characters_dir))
    # Repli pratique : fiches perso à côté de l'episode.json (cas des examples/)
    local = load_characters(Path(args.episode).parent / "characters")
    for cid, ch in local.items():
        characters.setdefault(cid, ch)
    ctx = EpisodeContext(cfg=cfg, episode=ep, out_dir=out_dir, backend=args.backend,
                         force=args.force, only_shots=shots, characters=characters)
    ctx.save_episode_copy()
    return ctx


def _validate(ctx: EpisodeContext) -> None:
    from cartoon_factory import stage_script

    print(stage_script.report(ctx.episode, ctx.cfg, set(ctx.characters)))
    ctx.episode.validate_or_raise(known_characters=set(ctx.characters),
                                  words_per_minute=ctx.cfg.tts.words_per_minute)


# ── Commandes ────────────────────────────────────────────────────────────────

def cmd_brief(args, cfg):
    from cartoon_factory import stage_script

    chars = sorted(load_characters(cfg.resolve(cfg.characters_dir)))
    text = stage_script.brief(args.question, cfg, chars)
    if args.out:
        p = stage_script.write_brief_file(args.question, cfg, chars, Path(args.out))
        print(f"brief écrit : {p}")
    else:
        print(text)


def cmd_new(args, cfg):
    from cartoon_factory import stage_script

    chars = sorted(load_characters(cfg.resolve(cfg.characters_dir)))
    ep = stage_script.scaffold(args.question, chars, args.id)
    dest = Path(args.out) if args.out else cfg.resolve(cfg.output_dir) / ep.id / "episode.json"
    if dest.exists() and not args.force:
        sys.exit(f"{dest} existe déjà (--force pour écraser)")
    ep.save(dest)
    print(f"squelette écrit : {dest}\nComplète-le puis : cartoon-factory validate --episode {dest}")


def cmd_validate(args, cfg):
    _validate(_ctx(args, cfg))


def cmd_characters(args, cfg):
    from cartoon_factory import stage_characters

    ctx = _ctx(args, cfg)
    stage_characters.ensure_sheets(ctx.episode.characters, ctx.characters)
    for cid in ctx.episode.characters:
        ch = ctx.characters[cid]
        if args.dataset:
            out = cfg.resolve(cfg.characters_dir) / "datasets" / cid
            paths = stage_characters.build_dataset(ch, cfg, out, args.dataset, ctx.backend)
            print(f"{cid} : {len(paths)} images de dataset dans {out}")
        else:
            dest = cfg.resolve(cfg.characters_dir) / f"{cid}_ref.png"
            if dest.exists() and not args.force:
                print(f"{cid} : référence déjà présente ({dest})")
                continue
            stage_characters.reference_image(ch, cfg, dest, ctx.backend)
            print(f"{cid} : image de référence → {dest}")


def cmd_keyframes(args, cfg):
    from cartoon_factory import stage_keyframes

    ctx = _ctx(args, cfg)
    paths = stage_keyframes.run(ctx)
    print(f"{len(paths)} dessin(s) clé(s) généré(s) → {ctx.keyframes_dir}")


def cmd_voice(args, cfg):
    from cartoon_factory import stage_voice

    ctx = _ctx(args, cfg)
    paths = stage_voice.run(ctx, args.tts)
    print(f"{len(paths)} voix générée(s) → {ctx.voice_dir}")


def cmd_animate(args, cfg):
    from cartoon_factory import stage_animate

    ctx = _ctx(args, cfg)
    paths = stage_animate.run(ctx)
    print(f"{len(paths)} clip(s) généré(s) → {ctx.anims_dir}")


def cmd_assemble(args, cfg):
    from cartoon_factory import stage_assemble

    ctx = _ctx(args, cfg)
    outputs = stage_assemble.run(ctx, title_card=not args.no_title)
    for k, v in outputs.items():
        print(f"{k:>9} : {v}")


def cmd_check(args, cfg):
    from cartoon_factory import stage_check

    ctx = _ctx(args, cfg)
    reports = stage_check.run(ctx)
    print((ctx.checks_dir / "report.md").read_text(encoding="utf-8"))
    bad = [r.id for r in reports if not r.ok]
    if bad:
        print(f"❌ plans à revoir : {', '.join(bad)}")
        return 1
    print(f"✅ {len(reports)} plan(s) OK — images à regarder dans {ctx.checks_dir}")
    return 0


def cmd_reject(args, cfg):
    ctx = _ctx(args, cfg)
    for sid in args.shot_ids:
        ctx.episode.shot(sid)  # vérifie l'existence
        for stage in args.stages.split(","):
            ctx.cache.reject(stage.strip(), sid, args.reason)
    print(f"plans {args.shot_ids} marqués à refaire pour : {args.stages}")


def cmd_status(args, cfg):
    ctx = _ctx(args, cfg)
    print(f"épisode {ctx.episode.id} — sortie : {ctx.out_dir}")
    print(f"{'plan':<6}{'keyframes':<11}{'voice':<8}{'animate':<9}{'assemble'}")
    for s in ctx.episode.shots:
        cells = []
        stage_paths = (("keyframes", [ctx.keyframe_path(s, i) for i in range(s.keyframe_count)]),
                       ("voice", [ctx.voice_path(s)]), ("animate", [ctx.anim_path(s)]),
                       ("assemble", [ctx.shot_video_path(s)]))
        for stage, paths in stage_paths:
            entry = ctx.cache.entries().get(f"{stage}:{s.id}", {})
            if entry.get("rejected"):
                cells.append("✗ rejeté")
            elif all(p.exists() for p in paths):
                cells.append("✓")
            else:
                cells.append("·")
        print(f"{s.id:<6}{cells[0]:<11}{cells[1]:<8}{cells[2]:<9}{cells[3]}")


def cmd_clean(args, cfg):
    ctx = _ctx(args, cfg)
    ctx.clean()
    print(f"sorties supprimées dans {ctx.out_dir} (episode.json conservé)")


def cmd_run(args, cfg):
    """Pipeline complet : validate → characters → keyframes → voice → animate → assemble → check.

    La voix passe AVANT l'animation pour que chaque clip soit rendu à la durée
    réelle de l'audio (c'est la vidéo qui s'adapte à la voix).
    """
    from cartoon_factory import (
        stage_animate,
        stage_assemble,
        stage_characters,
        stage_check,
        stage_keyframes,
        stage_voice,
    )

    ctx = _ctx(args, cfg)
    _validate(ctx)
    stage_characters.ensure_sheets(ctx.episode.characters, ctx.characters)
    steps = [("keyframes", lambda: stage_keyframes.run(ctx)),
             ("voice", lambda: stage_voice.run(ctx, args.tts)),
             ("animate", lambda: stage_animate.run(ctx)),
             ("assemble", lambda: stage_assemble.run(ctx, title_card=not args.no_title))]
    for name, fn in steps:
        log.info("━━ étape %s ━━", name)
        fn()
    reports = stage_check.run(ctx)
    print((ctx.checks_dir / "report.md").read_text(encoding="utf-8"))
    master = ctx.final_dir / f"{ctx.episode.id}_1080p.mp4"
    print(f"🎬 {master}")
    return 0 if all(r.ok for r in reports) else 1


# ── Parser ───────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cartoon-factory",
                                description="Pipeline local de dessins animés éducatifs 2D")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--config", default=None, help="chemin de config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    def add_episode_opts(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--episode", required=False, help="chemin de episode.json")
        sp.add_argument("--out", default=None, help="dossier de sortie (défaut output/<id>)")
        sp.add_argument("--shots", default="", help="ids de plans, séparés par des virgules")
        sp.add_argument("--force", action="store_true", help="ignorer le cache")
        sp.add_argument("--backend", default="comfy", choices=("comfy", "placeholder"),
                        help="comfy = ComfyUI réel ; placeholder = croquis Pillow sans GPU")

    sp = sub.add_parser("brief", help="consignes d'écriture du script pour Claude")
    sp.add_argument("question")
    sp.add_argument("--out", default=None)
    sp.set_defaults(fn=cmd_brief)

    sp = sub.add_parser("new", help="squelette episode.json")
    sp.add_argument("question")
    sp.add_argument("--id", default=None)
    sp.add_argument("--out", default=None)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=cmd_new)

    for name, fn, helptxt in (("validate", cmd_validate, "valider le script"),
                              ("keyframes", cmd_keyframes, "générer les dessins clés"),
                              ("animate", cmd_animate, "animer les plans"),
                              ("status", cmd_status, "état du cache par plan"),
                              ("clean", cmd_clean, "supprimer les sorties de l'épisode"),
                              ("check", cmd_check, "extraire une image par plan + rapport")):
        sp = sub.add_parser(name, help=helptxt)
        add_episode_opts(sp)
        sp.set_defaults(fn=fn)

    sp = sub.add_parser("characters", help="images de référence / dataset LoRA des persos")
    add_episode_opts(sp)
    sp.add_argument("--dataset", type=int, default=0, metavar="N",
                    help="générer N images + captions pour entraîner un LoRA perso")
    sp.set_defaults(fn=cmd_characters)

    sp = sub.add_parser("voice", help="synthèse vocale par plan")
    add_episode_opts(sp)
    sp.add_argument("--tts", default=None, choices=("kokoro", "xtts", "espeak", "silence"))
    sp.set_defaults(fn=cmd_voice)

    sp = sub.add_parser("assemble", help="montage final (16:9 + 9:16, .srt)")
    add_episode_opts(sp)
    sp.add_argument("--no-title", action="store_true", help="sans carte-titre")
    sp.set_defaults(fn=cmd_assemble)

    sp = sub.add_parser("reject", help="marquer des plans à refaire")
    add_episode_opts(sp)
    sp.add_argument("shot_ids", nargs="+")
    sp.add_argument("--stages", default="keyframes,animate", help="étapes à invalider")
    sp.add_argument("--reason", default="")
    sp.set_defaults(fn=cmd_reject)

    sp = sub.add_parser("run", help="tout le pipeline")
    add_episode_opts(sp)
    sp.add_argument("--tts", default=None, choices=("kokoro", "xtts", "espeak", "silence"))
    sp.add_argument("--no-title", action="store_true")
    sp.set_defaults(fn=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname).1s %(name)s: %(message)s")
    cfg = load_config(args.config)
    try:
        return int(args.fn(args, cfg) or 0)
    except ValidationError as exc:
        print(f"❌ script invalide :\n{exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, KeyError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:  # ComfyError, FFmpegError, TTSError
        print(f"❌ {type(exc).__name__} : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
