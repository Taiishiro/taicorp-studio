# État du projet cartoon-factory

> Fichier d'état à relire **avant d'agir** après une reprise ou une compaction.
> Règle : une tâche passe en `fait` uniquement avec sa preuve (commit, test, fichier).
> Ce qui n'est pas vérifiable depuis la session courante reste en `à Antonin`.

**Statut global : EN PAUSE** (demande d'Antonin, relayée le 02/11/2026) jusqu'à la
fin de la série E4 d'Axiome. Ne rien lancer qui demande le GPU ou WSL.

Branche : `claude/cartoon-factory-pipeline-fjpt1s` — PR brouillon
[Taiishiro/taicorp-studio#1](https://github.com/Taiishiro/taicorp-studio/pull/1).

## Tâches

### à faire
- [ ] Vérifier les noms de nœuds de `workflows/tooncrafter.api.json` et
      `workflows/wan_i2v.api.json` contre les custom nodes installés
      (procédure : `workflows/README.md`). **GPU/WSL requis → attendre la fin de la pause.**
- [ ] Choisir un LoRA de style crayon et renseigner `style.lora` dans `config.yaml`.
- [ ] Premier épisode réel avec ComfyUI (`cartoon-factory run --episode …`). **GPU requis.**
- [ ] Relire le diff des correctifs locaux d'Antonin une fois poussés (voir « à Antonin »).

### en cours
- (aucune tâche en cours dans la session cloud — tout ce qu'elle a produit est committé)

### à Antonin
- [ ] Pousser sur la même branche les correctifs faits en local depuis le 30/09
      (la branche distante n'a qu'un commit : `b1fae75`). Sans ce push, la PR et ce
      fichier ne reflètent pas l'état réel du PC.
- [ ] Confirmer les choix notés dans le second brain mais absents de la branche :
      univers Plumeval, pilote « Manger à sa faim », Flux comme seul modèle image,
      XTTS en venv séparé, `characters/univers/lieux.json`, `scripts/lora_phase2.sh`,
      `scripts/lora_control.py`. S'ils sont réels, les committer ; sinon corriger la carte.
- [ ] Décider : fusionner la PR en l'état, ou attendre la fin de la pause.

### fait
- [x] Pipeline complet (script → persos → dessins clés → voix → animation → montage →
      vérification), CLI, cache par plan, backends ComfyUI + placeholder, 4 backends TTS,
      4 workflows API, scripts d'installation, skill `/episode`, README, exemple
      « ciel-bleu » — **preuve : commit `b1fae75`, poussé, PR #1 ouverte (30/09/2026).**
- [x] Lint propre et 13 tests verts sans GPU — **preuve : `ruff check src tests` OK,
      `pytest -q` → 13 passed (30/09/2026), CI étendue dans `.github/workflows/ci.yml`.**
- [x] Rendu de démonstration de bout en bout en mode placeholder + espeak (10 plans,
      1080p + 9:16 + .srt) — **preuve : `examples/ciel-bleu/preview/` committé.**
- [x] Relecture de la carte du second brain (02/11/2026) : écarts signalés à Antonin
      dans la conversation cloud (SDXL par défaut et non Flux ; Kokoro par défaut,
      pas de venv XTTS séparé ; aucun correctif non committé côté cloud).

## Décisions tenues (ne pas rediscuter sans Antonin)
- La voix est synthétisée **avant** l'animation ; la vidéo se cale sur la durée réelle de l'audio.
- Sous-titres : `.srt` à côté + piste `mov_text` dans le MP4, pas d'incrustation par défaut.
- ComfyUI écoute uniquement sur `127.0.0.1` (un workflow exécute du code arbitraire).
- Un épisode à la fois, jamais de saison en lot (règle d'Antonin).
- Un seul univers graphique : mêmes lieux, même trait, même échelle (règle d'Antonin).

## Comment reprendre
1. Lire ce fichier, puis `git status` et `git log --oneline -5` pour voir ce qui a bougé.
2. Sans GPU : `cd cartoon-factory && .venv/bin/pytest -q` et, pour un rendu témoin,
   `cartoon-factory run --episode examples/ciel-bleu/episode.json --backend placeholder --tts espeak`.
3. Avec GPU (après la pause) : `scripts/run_comfy.sh &` puis les étapes du README § 2.
4. Mettre à jour la section « Tâches » **avant** de clore la session.
