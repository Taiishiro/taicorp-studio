# Workflows ComfyUI (format API)

Trois graphes au **format API** (ComfyUI → menu ⚙ → *Enable dev mode options*
→ bouton *Save (API Format)*). L'orchestrateur (`src/cartoon_factory/comfy.py`)
charge le JSON, remplace les **placeholders `__NOM__`** puis l'envoie sur
`POST /prompt`.

| Fichier | Rôle | Custom nodes requis |
|---|---|---|
| `keyframe_sdxl.api.json` | dessin clé SDXL + LoRA style + LoRA perso | aucun (cœur ComfyUI) |
| `keyframe_flux.api.json` | variante Flux.1-dev GGUF (meilleur suivi de prompt, plus lent) | ComfyUI-GGUF |
| `tooncrafter.api.json` | 2 dessins clés → interpolation cartoon | ComfyUI-ToonCrafter, VideoHelperSuite |
| `wan_i2v.api.json` | 1 dessin → clip Wan 2.2 I2V 14B GGUF (16 Go) | ComfyUI-GGUF, KJNodes, VideoHelperSuite |

## Placeholders

Un placeholder est une chaîne **entière** `"__NOM__"` (remplacée par la valeur
typée : int, float, str) ou **incluse** dans un texte (`"cartoon-factory/__PREFIX__"`).
`fill_workflow()` refuse d'envoyer un graphe où il en reste un.

Communs : `__PROMPT__`, `__NEGATIVE__`, `__SEED__`, `__STEPS__`, `__CFG__`,
`__WIDTH__`, `__HEIGHT__`, `__PREFIX__`.
Keyframe : `__SAMPLER__`, `__SCHEDULER__`, `__STYLE_LORA__`, `__STYLE_LORA_WEIGHT__`,
`__CHAR_LORA__`, `__CHAR_LORA_WEIGHT__`, `__SDXL_CHECKPOINT__` (ou `__FLUX_*__`).
ToonCrafter : `__IMAGE_START__`, `__IMAGE_END__`, `__FRAMES__`, `__FPS__`, `__ETA__`,
`__TOONCRAFTER__`.
Wan : `__IMAGE_START__`, `__FRAMES__`, `__FPS__`, `__SHIFT__`, `__WAN_HIGH_GGUF__`,
`__WAN_LOW_GGUF__`, `__WAN_CLIP__`, `__WAN_VAE__`, `__WAN_CLIP_VISION__`.

Les noms de modèles (`__SDXL_CHECKPOINT__`, `__WAN_*__`, …) viennent de
`config.yaml → comfy.models` (clé en majuscules).

## LoRA optionnels

Un nœud `LoraLoader` dont `lora_name` reste vide est **retiré automatiquement**
(`bypass_empty_loras`) et ses consommateurs rebranchés en amont. On peut donc
laisser `style.lora.file: ""` dans la config sans toucher au graphe.

## ⚠️ Vérifier les nœuds des custom nodes

Les graphes ToonCrafter et Wan ont été écrits « à la main » d'après la doc des
dépôts ; les **noms de classes et d'entrées des custom nodes changent d'une
version à l'autre**. Procédure sûre, une fois ComfyUI installé :

1. Ouvrir le workflow d'exemple fourni par le custom node (dossier
   `custom_nodes/<node>/examples/` ou le README du dépôt), le faire tourner
   une fois dans l'UI avec deux de tes dessins.
2. L'exporter au format API et le copier ici sous le même nom.
3. Remplacer les valeurs variables par les placeholders du tableau ci-dessus
   (prompt, images, seed, frames, prefix). Garder les valeurs fixes en dur.
4. `cartoon-factory animate --episode … --shots s01` pour tester.

Toute erreur de nœud remonte telle quelle dans la console (`ComfyError :
erreur d'exécution ComfyUI : …`).
