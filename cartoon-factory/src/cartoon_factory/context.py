"""Contexte d'exécution d'un épisode : config, épisode, chemins, cache, options.

Toutes les étapes reçoivent ce même objet, ce qui les rend relançables
individuellement (`cartoon-factory keyframes --episode …`) avec le même état.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from cartoon_factory.cache import StageCache
from cartoon_factory.config import Config
from cartoon_factory.models import Character, Episode, Shot, load_characters

log = logging.getLogger(__name__)

BACKENDS = ("comfy", "placeholder")


@dataclass
class EpisodeContext:
    cfg: Config
    episode: Episode
    out_dir: Path
    backend: str = "comfy"  # comfy | placeholder
    force: bool = False
    only_shots: set[str] = field(default_factory=set)
    characters: dict[str, Character] = field(default_factory=dict)
    cache: StageCache = field(init=False)

    def __post_init__(self) -> None:
        if self.backend not in BACKENDS:
            raise ValueError(f"backend « {self.backend} » ∉ {BACKENDS}")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.cache = StageCache(self.out_dir / "cache.json")
        if not self.characters:
            self.characters = load_characters(self.cfg.resolve(self.cfg.characters_dir))

    # ── Dossiers de sortie ───────────────────────────────────────────────────
    @property
    def keyframes_dir(self) -> Path:
        return self.out_dir / "keyframes"

    @property
    def anims_dir(self) -> Path:
        return self.out_dir / "anims"

    @property
    def voice_dir(self) -> Path:
        return self.out_dir / "voice"

    @property
    def final_dir(self) -> Path:
        return self.out_dir / "final"

    @property
    def checks_dir(self) -> Path:
        return self.out_dir / "checks"

    # ── Chemins par plan ─────────────────────────────────────────────────────
    def keyframe_path(self, shot: Shot, index: int = 0) -> Path:
        return self.keyframes_dir / f"{shot.id}_k{index}.png"

    def anim_path(self, shot: Shot) -> Path:
        return self.anims_dir / f"{shot.id}.mp4"

    def voice_path(self, shot: Shot) -> Path:
        return self.voice_dir / f"{shot.id}.wav"

    def shot_video_path(self, shot: Shot) -> Path:
        return self.final_dir / "shots" / f"{shot.id}.mp4"

    # ── Sélection ────────────────────────────────────────────────────────────
    def selected_shots(self) -> list[Shot]:
        if not self.only_shots:
            return list(self.episode.shots)
        unknown = self.only_shots - {s.id for s in self.episode.shots}
        if unknown:
            raise KeyError(f"plans inconnus : {sorted(unknown)}")
        return [s for s in self.episode.shots if s.id in self.only_shots]

    def shot_characters(self, shot: Shot) -> list[Character]:
        out = []
        for cid in shot.characters:
            if cid in self.characters:
                out.append(self.characters[cid])
            else:
                log.warning("plan %s : fiche perso « %s » introuvable", shot.id, cid)
        return out

    def voice_duration(self, shot: Shot, fallback: float | None = None) -> float:
        """Durée réelle de la voix si elle existe, sinon la durée cible du script."""
        from cartoon_factory.media import media_duration

        p = self.voice_path(shot)
        if p.exists():
            return media_duration(p)
        return shot.duration_s if fallback is None else fallback

    def save_episode_copy(self) -> Path:
        """Fige le script utilisé pour ce rendu dans le dossier de sortie."""
        dest = self.out_dir / "episode.json"
        self.episode.save(dest)
        return dest

    def clean(self) -> None:
        """Supprime toutes les sorties de l'épisode (garde le script)."""
        for d in (self.keyframes_dir, self.anims_dir, self.voice_dir, self.final_dir,
                  self.checks_dir):
            shutil.rmtree(d, ignore_errors=True)
        self.cache.invalidate()
