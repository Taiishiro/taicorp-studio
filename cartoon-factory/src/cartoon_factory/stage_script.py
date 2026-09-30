"""Étape 1 — SCRIPT.

Claude Code est le rédacteur : ce module ne génère pas de texte, il fournit
  * `brief()`   : le cahier des charges + schéma JSON à donner à Claude ;
  * `scaffold()`: un episode.json vide à compléter ;
  * `report()`  : validation + estimation des durées (mots / 150 wpm).
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from cartoon_factory.config import Config
from cartoon_factory.models import CAMERAS, METHODS, Episode, Shot

_SCHEMA_EXAMPLE = {
    "id": "ciel-bleu",
    "question": "Pourquoi le ciel est bleu ?",
    "title": "Le ciel est bleu !",
    "audience": "8-12 ans",
    "language": "fr",
    "summary": "Une phrase qui résume l'explication.",
    "characters": ["pilou"],
    "shots": [
        {
            "id": "s01",
            "duration_s": 4.0,
            "voice_text": "Texte lu par la voix off pour ce plan (8 à 12 mots).",
            "visual": "Description du dessin, en français, décor minimal.",
            "characters": ["pilou"],
            "motion": "Ce qui bouge : « Pilou lève les bras », « la caméra zoome sur le soleil ».",
            "method": "kenburns | tooncrafter | wan_i2v",
            "camera": "zoom_in | zoom_out | pan_left | pan_right | static",
            "keyframes": [
                {"prompt": "Prompt anglais du 1er dessin clé (sans le style, ajouté auto)."},
                {"prompt": "2e dessin clé — obligatoire pour tooncrafter, ignoré sinon."},
            ],
        }
    ],
}


def slugify(text: str) -> str:
    """« Pourquoi le ciel est bleu ? » → « pourquoi-le-ciel-est-bleu »."""
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    return slug[:48] or "episode"


def brief(question: str, cfg: Config, characters: list[str]) -> str:
    """Consignes complètes pour que Claude écrive `episode.json`."""
    wpm = cfg.tts.words_per_minute
    chars = ", ".join(characters) if characters else "(aucune fiche : en créer une)"
    return f"""# Brief d'écriture — « {question} »

Écris un épisode de dessin animé éducatif (public 8-12 ans) qui répond à la
question ci-dessus, au format JSON ci-dessous, dans `episode.json`.

## Règles éditoriales
- Voix off en français simple, phrases courtes, ton complice, **zéro jargon**
  sans l'expliquer. Une seule idée par plan. Terminer par une phrase qui
  résume et ouvre la curiosité.
- Rythme : ~{wpm} mots/min ⇒ **8 à 12 mots par plan de 4 s**. Durée totale
  visée : 45 s à 90 s (10 à 20 plans de 3 à 5 s).
- Tout est **original** : aucun personnage, décor ou nom d'une émission existante.
- Personnages disponibles : {chars}. Utiliser les mêmes ids dans `characters`.
- Style visuel imposé par la config (trait crayon, aplats doux, décor minimal) :
  ne décrire dans `visual` que le contenu (qui, quoi, où), pas le style.

## Choix de la méthode d'animation par plan
- `kenburns` : plan statique + zoom/pan (par défaut, le moins coûteux). 1 keyframe.
- `tooncrafter` : geste ou expression simple entre **2 dessins clés** proches
  (bras qui se lève, sourire → surprise). Les 2 prompts doivent différer peu.
- `wan_i2v` : mouvement plus libre (marche, objet qui tombe), 1 keyframe +
  `motion` précis. Coûteux (~2-5 min/plan) : 2 à 4 plans max par épisode.

## Méthodes : {", ".join(METHODS)} — Caméras : {", ".join(CAMERAS)}

## Schéma JSON (exemple à suivre exactement)
```json
{json.dumps(_SCHEMA_EXAMPLE, ensure_ascii=False, indent=2)}
```

Ensuite : `cartoon-factory validate --episode <chemin>/episode.json`.
"""


def scaffold(question: str, characters: list[str], episode_id: str | None = None) -> Episode:
    """Épisode squelette : 1 plan d'exemple à remplacer."""
    return Episode(
        id=episode_id or slugify(question),
        question=question,
        title=question.rstrip(" ?!."),
        characters=list(characters),
        shots=[Shot(id="s01", voice_text="", visual="", characters=list(characters[:1]))],
    )


def report(ep: Episode, cfg: Config, known_characters: set[str]) -> str:
    """Tableau lisible : durée cible vs durée estimée par plan, puis problèmes."""
    wpm = cfg.tts.words_per_minute
    lines = [f"Épisode « {ep.id} » — {len(ep.shots)} plans, "
             f"{ep.total_duration_s():.0f} s cibles, {ep.total_words()} mots "
             f"(≈ {ep.total_words() / wpm * 60:.0f} s de voix à {wpm} wpm)", ""]
    lines.append(f"{'plan':<6}{'cible':>7}{'voix≈':>7}  {'méthode':<12}{'texte'}")
    for s in ep.shots:
        est = s.word_count() / wpm * 60
        flag = " ⚠" if est > s.duration_s * 1.6 else ""
        lines.append(f"{s.id:<6}{s.duration_s:>6.1f}s{est:>6.1f}s  {s.method:<12}"
                     f"{s.voice_text[:60]}{flag}")
    problems = ep.validate(known_characters=known_characters, words_per_minute=wpm)
    lines.append("")
    if problems:
        lines.append("Problèmes :")
        lines += [f"  - {p}" for p in problems]
    else:
        lines.append("✅ Script valide.")
    return "\n".join(lines)


def write_brief_file(question: str, cfg: Config, characters: list[str], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(brief(question, cfg, characters), encoding="utf-8")
    return dest
