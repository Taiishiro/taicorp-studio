"""Modèles de données : épisode, plan, personnage — et leur validation.

Le JSON d'épisode est écrit par Claude (étape SCRIPT) puis consommé par toutes
les autres étapes. Ce module est la seule source de vérité sur sa forme.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

METHODS = ("kenburns", "tooncrafter", "wan_i2v")
CAMERAS = ("static", "zoom_in", "zoom_out", "pan_left", "pan_right")
MIN_SHOT_S = 2.0
MAX_SHOT_S = 8.0
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ValidationError(ValueError):
    """Le JSON d'épisode ou une fiche perso est invalide (liste de problèmes)."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(f"- {p}" for p in problems))


@dataclass
class Keyframe:
    """Un dessin clé : prompt spécifique au plan (le style est ajouté par la config)."""

    prompt: str
    seed: int | None = None  # None = seed dérivée du plan (reproductible)


@dataclass
class Shot:
    """Un plan de 3-5 s : texte de voix off + description visuelle + animation."""

    id: str
    voice_text: str
    visual: str
    duration_s: float = 4.0  # durée cible ; la durée réelle vient de l'audio
    characters: list[str] = field(default_factory=list)
    motion: str = ""  # mouvement souhaité, en français, pour le prompt vidéo
    method: str = "kenburns"  # kenburns | tooncrafter | wan_i2v
    camera: str = "zoom_in"  # pour kenburns
    keyframes: list[Keyframe] = field(default_factory=list)
    notes: str = ""

    @property
    def keyframe_count(self) -> int:
        """ToonCrafter interpole entre 2 dessins ; les autres méthodes en veulent 1."""
        return 2 if self.method == "tooncrafter" else 1

    def word_count(self) -> int:
        return len(self.voice_text.split())


@dataclass
class Episode:
    id: str
    question: str
    title: str = ""
    audience: str = "8-12 ans"
    language: str = "fr"
    characters: list[str] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    summary: str = ""

    # ── Sérialisation ────────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Episode:
        shots = []
        for s in data.get("shots", []):
            kfs = [Keyframe(**k) if isinstance(k, dict) else Keyframe(prompt=str(k))
                   for k in s.get("keyframes", [])]
            shots.append(Shot(**{**s, "keyframes": kfs}))
        return cls(**{**data, "shots": shots})

    @classmethod
    def load(cls, path: str | Path) -> Episode:
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    # ── Métriques ────────────────────────────────────────────────────────────
    def total_duration_s(self) -> float:
        return sum(s.duration_s for s in self.shots)

    def total_words(self) -> int:
        return sum(s.word_count() for s in self.shots)

    def shot(self, shot_id: str) -> Shot:
        for s in self.shots:
            if s.id == shot_id:
                return s
        raise KeyError(f"plan inconnu : {shot_id}")

    # ── Validation ───────────────────────────────────────────────────────────
    def validate(self, known_characters: set[str] | None = None,
                 words_per_minute: int = 150) -> list[str]:
        """Retourne la liste des problèmes (vide = OK). Ne lève pas."""
        problems: list[str] = []
        if not SLUG_RE.match(self.id):
            problems.append(f"id d'épisode invalide « {self.id} » (minuscules, chiffres, - _)")
        if not self.question.strip():
            problems.append("question vide")
        if not self.shots:
            problems.append("aucun plan")
        seen: set[str] = set()
        for i, s in enumerate(self.shots):
            where = f"plan {i + 1} ({s.id})"
            if not SLUG_RE.match(s.id):
                problems.append(f"{where} : id invalide")
            if s.id in seen:
                problems.append(f"{where} : id en doublon")
            seen.add(s.id)
            if s.method not in METHODS:
                problems.append(f"{where} : method « {s.method} » ∉ {METHODS}")
            if s.camera not in CAMERAS:
                problems.append(f"{where} : camera « {s.camera} » ∉ {CAMERAS}")
            if not (MIN_SHOT_S <= s.duration_s <= MAX_SHOT_S):
                problems.append(
                    f"{where} : durée {s.duration_s}s hors [{MIN_SHOT_S}, {MAX_SHOT_S}]")
            if not s.visual.strip():
                problems.append(f"{where} : description visuelle vide")
            if s.keyframes and len(s.keyframes) < s.keyframe_count:
                problems.append(f"{where} : {s.method} demande {s.keyframe_count} keyframe(s)")
            # Rythme : ~150 mots/min → tolérance ±60 %
            if s.voice_text.strip():
                expected = s.word_count() / words_per_minute * 60
                if expected > s.duration_s * 1.6:
                    problems.append(
                        f"{where} : {s.word_count()} mots ≈ {expected:.1f}s de voix "
                        f"pour un plan de {s.duration_s}s (trop dense)")
            for c in s.characters:
                if c not in self.characters:
                    problems.append(f"{where} : personnage « {c} » absent de episode.characters")
                if known_characters is not None and c not in known_characters:
                    problems.append(f"{where} : pas de fiche perso pour « {c} »")
        total = self.total_duration_s()
        if self.shots and not (20 <= total <= 150):
            problems.append(f"durée totale {total:.0f}s hors de la fenêtre 30 s – 2 min")
        return problems

    def validate_or_raise(self, **kw: Any) -> None:
        problems = self.validate(**kw)
        if problems:
            raise ValidationError(problems)


@dataclass
class Character:
    """Fiche perso : description visuelle FIXE pour la cohérence entre plans."""

    id: str
    name: str
    description: str  # en français, pour Claude et le lecteur
    prompt: str  # en anglais, injecté tel quel dans chaque dessin clé
    negative_prompt: str = ""
    seed: int = 1234
    palette: dict[str, str] = field(default_factory=dict)  # couleurs hex (placeholder + doc)
    lora: dict[str, Any] = field(default_factory=dict)  # {"file": "", "weight": 0.9, "trigger": ""}
    reference_image: str = ""  # chemin d'une image de référence (IP-Adapter, doc)

    @classmethod
    def load(cls, path: str | Path) -> Character:
        with open(path, encoding="utf-8") as fh:
            return cls(**json.load(fh))

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    @property
    def lora_file(self) -> str:
        return str(self.lora.get("file", "") or "")

    @property
    def lora_weight(self) -> float:
        return float(self.lora.get("weight", 0.9))

    @property
    def lora_trigger(self) -> str:
        return str(self.lora.get("trigger", "") or "")


def load_characters(directory: str | Path) -> dict[str, Character]:
    """Charge toutes les fiches `*.json` d'un dossier (dict id → fiche)."""
    directory = Path(directory)
    out: dict[str, Character] = {}
    if not directory.is_dir():
        return out
    for p in sorted(directory.glob("*.json")):
        ch = Character.load(p)
        out[ch.id] = ch
    return out
