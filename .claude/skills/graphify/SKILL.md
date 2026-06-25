---
name: graphify
description: Transforme le dépôt en knowledge graph navigable pour que les agents IA sélectionnent le contexte minimal et analysent l'architecture sans avaler tout le code. Utilisé par le Context Manager pour router les fichiers pertinents à chaque ticket, et par l'Architect Lead pour mesurer l'impact d'une décision structurante avant tout ADR.
---

# Skill : graphify — knowledge graph du dépôt

## Pourquoi dans le pipeline TaiCorp

Sans graphify, le Context Manager doit deviner quels fichiers sont liés à un ticket → soit il inclut trop (token waste), soit il oublie une dépendance (le Senior Coder bloque).

Avec graphify, chaque agent qui en a besoin **interroge** le graph au lieu de scanner le dépôt :

| Agent | Comment il l'utilise |
|-------|---------------------|
| **Context Manager** | `graphify query "fichiers liés à X"` pour bâtir un bundle minimal sourcé. |
| **Architect Lead** | `graphify path "ModuleA" "ModuleB"` pour mesurer l'impact d'un changement avant ADR. |
| **Reviewer** | `graphify explain "<symbole>"` pour comprendre un appel hors diff sans lire tout le module. |

## Quand le lancer (build initial)

Au démarrage du projet, ou après une refonte majeure :

```bash
cd <racine-projet>
graphify .                        # full pipeline, sortie dans graphify-out/
graphify . --update               # incrémental : re-extrait seulement les fichiers changés
graphify . --watch                # auto-rebuild en continu (pas de LLM nécessaire)
```

> 🪶 Une fois `graphify-out/` créé, **toute question codebase doit passer par graphify d'abord**, avant grep/glob/read.

## Commandes-clés pour les agents

```bash
# Context Manager — quels fichiers inclure pour un ticket
graphify query "fichiers et symboles liés à l'authentification OAuth" --budget 1500

# Architect Lead — impact d'un changement avant ADR
graphify path "AuthMiddleware" "UserRepository"
graphify explain "AuthMiddleware"

# Reviewer — comprendre un symbole hors diff
graphify explain "<NomSymbole>"
```

## Règles d'or

- 🗺️ **graphify avant grep.** Si `graphify-out/` existe, l'agent interroge le graph avant tout autre outil de recherche.
- 🔁 **`--update` après chaque ticket mergé** par le git-integration (ou via `--watch` en continu).
- 📦 **Le résultat de graphify est cité** dans le context bundle (Context Manager) ou dans l'ADR (Architect Lead) — pas de décision sans traçabilité.
- 🚫 **Pas d'écriture par graphify.** C'est un outil de lecture / analyse. Aucun agent ne demande à graphify de modifier le code.

## Sortie attendue dans le bundle / ADR

```markdown
## Source graphify

**Requête :** `graphify query "fichiers liés à OAuth"`
**Fichiers renvoyés :** src/auth/oauth.py, src/auth/middleware.py, tests/test_oauth.py
**Communauté détectée :** auth-cluster (4 modules, 12 symboles)
```

## Skill global complet

La référence complète du CLI (toutes les options : `--mode deep`, `--neo4j`, `--mcp`, `--obsidian`, etc.) est dans le skill global :
`~/.claude/skills/graphify/SKILL.md`

Ce SKILL.md projet liste uniquement les usages utiles aux 9 agents du pipeline TaiCorp.
