---
name: episode
description: Produit un épisode complet de dessin animé éducatif 2D (30 s – 2 min) à partir d'une question, avec le pipeline local cartoon-factory (ComfyUI + TTS + ffmpeg). Écrit le script, demande validation, génère les dessins clés, la voix, l'animation et le montage, vérifie chaque plan en regardant une image extraite, relance les plans ratés. Usage : /episode <question> [--placeholder] [--tts espeak].
---

# /episode — de la question au MP4

Tu es le réalisateur. Le pipeline est dans `cartoon-factory/` ; lis son
`README.md` § 2 si tu doutes d'une commande. Toutes les commandes se lancent
depuis `cartoon-factory/` avec `.venv/bin/cartoon-factory …` (ou
`PYTHONPATH=src python3 -m cartoon_factory …` si le venv n'existe pas).

Arguments : `$ARGUMENTS` = la question, plus options facultatives :
`--placeholder` (machine sans GPU : `--backend placeholder`), `--tts espeak|xtts|kokoro|silence`.

## Règles d'or

1. **Jamais de génération avant validation du script** par l'utilisateur.
2. **Regarder les images** (outil Read sur les PNG) avant de déclarer un plan bon.
   Le rapport `check` n'attrape que les échecs grossiers.
3. **Relancer un plan, pas l'épisode** : `reject` + `--shots`. Le cache fait le reste.
4. Original uniquement : aucun personnage, décor, nom ou gimmick d'une émission existante.
5. Ne jamais lancer ComfyUI sur autre chose que `127.0.0.1`.

## Déroulé

### 0. Contexte
- `ls characters/ examples/*/characters/` → personnages disponibles (fiches JSON).
  S'il n'y en a pas, en écrire une (format : `examples/ciel-bleu/characters/pilou.json`)
  dans `characters/<id>.json` et la montrer à l'utilisateur.
- Mode réel : vérifier que ComfyUI répond (`curl -s 127.0.0.1:8188/system_stats | head -c 200`).
  S'il ne répond pas, proposer `scripts/run_comfy.sh &` ou basculer en `--placeholder`.

### 1. Script (toi)
- `cartoon-factory brief "<question>"` → lis les consignes.
- Écris `output/<slug>/episode.json` (`cartoon-factory new "<question>"` donne le
  squelette et le slug). 10-20 plans, 8-12 mots par plan de 4 s, une idée par
  plan, 2-4 plans `wan_i2v` max, `tooncrafter` pour les gestes des persos.
- `cartoon-factory validate --episode output/<slug>/episode.json` : corrige jusqu'à ✅.
- **Présente le script à l'utilisateur** : la voix off complète en un bloc, puis
  un tableau plan / durée / méthode / visuel. Demande explicitement
  « Je lance la génération ? » (AskUserQuestion si disponible : Valider /
  Modifier / Annuler). Applique les retours et re-valide.

### 2. Personnages
- `cartoon-factory characters --episode … [--backend placeholder]` → image de
  référence par perso dans `characters/<id>_ref.png`. **Regarde-la.** Si le
  design ne correspond pas à la fiche, ajuste `prompt` / `negative_prompt` /
  `seed` de la fiche et relance avec `--force`.

### 3. Génération
Lance dans cet ordre (chaque commande est relançable ; ajouter `--backend
placeholder` et/ou `--tts …` si demandé) :
```
cartoon-factory keyframes --episode …
cartoon-factory voice     --episode …
cartoon-factory animate   --episode …
cartoon-factory assemble  --episode …
cartoon-factory check     --episode …
```
Ou `cartoon-factory run --episode …` qui enchaîne tout. En mode réel, un plan
Wan prend 2-5 min : lance `animate` en arrière-plan si l'outil le permet et
informe l'utilisateur de l'avancement.

### 4. Vérification plan par plan
- Ouvre `output/<slug>/checks/report.md`.
- **Pour chaque plan**, Read `output/<slug>/checks/<id>.png` et, pour les plans
  ToonCrafter, les deux dessins clés `keyframes/<id>_k0.png` / `_k1.png`.
  Critères : le contenu de `visual` est reconnaissable ; le perso ressemble à sa
  fiche (couleurs, vêtements) ; pas de texte parasite, membres en trop, image
  noire ou vide ; cadrage lisible en 9:16 (sujet au centre).
- Plan raté → note la cause, puis :
  - dessin raté : `cartoon-factory reject <id> --episode … --reason "…"` puis
    `keyframes --shots <id>` (changer `keyframes[].seed` dans episode.json si le
    même prompt échoue deux fois, ou préciser le prompt) ;
  - animation ratée (déformation, saut) : `reject <id> --stages animate` puis
    `animate --shots <id>` ; en dernier recours passer le plan en `kenburns` ;
  - voix ratée (mot mal prononcé) : réécrire `voice_text` (chiffres en lettres,
    sigles épelés) puis `voice --shots <id>`.
  Puis `assemble` + `check` à nouveau. **Maximum 3 tentatives par plan**, ensuite
  demande à l'utilisateur.

### 5. Livraison
Résume : chemin du MP4 16:9, du 9:16, du .srt, durée totale, plans relancés et
pourquoi, ce qui reste perfectible. Propose les suites possibles (LoRA perso,
musique, autre question) sans les lancer.

## Dépannage rapide
- `ComfyUI injoignable` → `scripts/run_comfy.sh &`, attendre « To see the GUI go to ».
- `erreur d'exécution ComfyUI : … does not exist` → nom de nœud du custom node à
  corriger dans `workflows/*.api.json` (voir `workflows/README.md`).
- `CUDA out of memory` → baisser `animation.wan_i2v.frames` / `height` dans
  `config.yaml`, vérifier que ComfyUI tourne avec `--lowvram`.
- `ffmpeg introuvable` → `sudo apt install ffmpeg` ou `pip install imageio-ffmpeg`.
- Kokoro : `espeak-ng` absent → `sudo apt install espeak-ng`.
