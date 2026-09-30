# Épisode test — « Pourquoi le ciel est bleu ? »

Public 8-12 ans, ~50 s, 10 plans. Personnage : **Pilou** (hérisson curieux,
fiche dans `characters/pilou.json`).

## Voix off complète

Ce matin, Pilou lève le nez : le ciel est tout bleu ! Mais pourquoi bleu ? Pas
vert, pas rose, pas orange ? Tout commence avec le Soleil. Sa lumière a l'air
blanche… mais en vrai, elle contient toutes les couleurs de l'arc-en-ciel !
L'air, lui, est rempli de minuscules molécules invisibles. Quand la lumière les
touche, le bleu rebondit dans tous les sens. Les autres couleurs, elles,
passent presque tout droit. Alors, où que Pilou regarde, du bleu arrive dans
ses yeux. Le soir, la lumière traverse plus d'air : le bleu s'éparpille, il
reste l'orange ! Le ciel est bleu parce que l'air adore faire rebondir le bleu.
Et toi, tu regardes en l'air ?

## Découpage

Voir `episode.json` : 6 plans Ken Burns (peu coûteux), 2 plans ToonCrafter
(gestes de Pilou, s01 et s08), 2 plans Wan 2.2 (prisme s04, diffusion s06).

## Lancer

```bash
# sans GPU (croquis Pillow + voix espeak) :
cartoon-factory run --episode examples/ciel-bleu/episode.json --backend placeholder --tts espeak
# en réel (ComfyUI lancé, Kokoro installé) :
cartoon-factory run --episode examples/ciel-bleu/episode.json
```
