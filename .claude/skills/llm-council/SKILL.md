---
name: llm-council
description: Pipeline en trois étapes (council members → review anonymisée → chairman) pour trancher les décisions irréversibles et les failles CRITIQUE. Inspiré de karpathy/llm-council. Service local sur localhost:8001 (FastAPI) avec UI sur :5173 (React). Déclenché par l'Architect Lead avant tout ADR irréversible, ou par le Security Reviewer dès qu'une faille CRITIQUE est détectée.
---

# Skill : llm-council — débat 3-étapes inspiré de Karpathy

> Référence : [karpathy/llm-council](https://github.com/karpathy/llm-council) — pipeline 3 étapes : multi-LLM en parallèle → review anonymisée → chairman synthétise.
>
> 🔌 **Service local** : backend FastAPI `localhost:8001` + frontend React `localhost:5173` (lancer avec `python -m backend.main` depuis la racine du repo llm-council, pas depuis `backend/`).

## Quand le convoquer (3 déclencheurs exclusifs)

| Déclencheur | Convoquant | Sortie attendue |
|-------------|-----------|-----------------|
| Décision **irréversible** (BDD, microservices, refonte) | Architect Lead | ADR validé collégialement |
| Faille **CRITIQUE** dans le diff | Security Reviewer | Décision de blocage + plan |
| Désaccord persistant entre gardiens après 2 boucles | Context Manager | Tranche du débat |

## Architecture du pipeline (Karpathy)

### Étape 1 — Council Members (en parallèle, indépendants)

Chaque modèle reçoit **la même question** sans voir les réponses des autres. Composition recommandée pour TaiCorp (modèles dispo dans `COUNCIL_MODELS` du backend) :

| Membre | Modèle suggéré | Angle |
|--------|---------------|-------|
| Membre 1 | `claude-opus-4-7` (via OpenRouter) | Vision structurelle |
| Membre 2 | `claude-sonnet-4-6` | Rigueur opérationnelle |
| Membre 3 | `claude-haiku-4-5` ou GPT/Gemini équivalent | Angle alternatif (diversité) |

> 💡 **Diversité de modèles > nombre de modèles.** 3 modèles d'éditeurs différents > 5 modèles du même éditeur.

### Étape 2 — Review anonymisée (peer ranking)

Chaque membre reçoit les réponses des autres **avec labels anonymes** (`Response A`, `Response B`, `Response C`) — il ne sait pas qui a écrit quoi. Il doit :

1. Classer les réponses par qualité (1er, 2ème, 3ème).
2. Justifier le classement en 3 lignes max.
3. Identifier le risque résiduel de la réponse classée 1ère.

Le backend stocke la mapping `label → modèle` pour dé-anonymiser côté client après coup.

### Étape 3 — Chairman synthétise

Un **modèle désigné** (`CHAIRMAN_MODEL` dans `backend/config.py`, recommandé `claude-opus-4-7`) reçoit :
- Les 3 réponses (avec leurs auteurs visibles).
- Les 3 classements anonymisés.
- La question d'origine.

Il produit la **réponse finale unique** : décision, justification, action immédiate, risque résiduel.

## Format de sortie obligatoire

Le format ci-dessous est ce que le service `llm-council` retourne (ou ce que l'agent rédige si le service n'est pas lancé) :

```markdown
# LLM Council — [Sujet en une ligne]

**Convoqué par :** Architect Lead / Security Reviewer / Context Manager
**Question :** [Question fermée — OUI/NON/ALTERNATIVE]
**Date :** YYYY-MM-DD

## Étape 1 — Council Members (réponses parallèles)

### Response A — `<modèle>`
[Réponse complète]

### Response B — `<modèle>`
[Réponse complète]

### Response C — `<modèle>`
[Réponse complète]

## Étape 2 — Peer ranking (anonymisé)

| Évaluateur | 1er | 2ème | 3ème | Justification |
|------------|-----|------|------|---------------|
| Membre 1 | C | A | B | "C identifie le risque migration que les autres oublient." |
| Membre 2 | A | C | B | "A propose la solution la plus simple à rollback." |
| Membre 3 | A | B | C | "A est le seul à citer un cas d'usage concret." |

> Mapping dé-anonymisé : A=`modèle-X`, B=`modèle-Y`, C=`modèle-Z`

## Étape 3 — Synthèse du Chairman (`<modèle-chairman>`)

**Décision finale :** [OUI / NON / ALTERNATIVE — retenue : ...]
**Justification :** [Argument synthétique en 5 lignes max]
**Action immédiate :** [Ce qui doit se passer maintenant]
**Risque résiduel :** [Le minoritaire — ou "aucun signalé"]

---
→ **Council clos.** Verdict transmis au [convoquant].
```

## Comment l'invoquer depuis le pipeline TaiCorp

### Mode service (UI Karpathy en parallèle)

```bash
# Terminal 1 — backend llm-council
cd ~/llm-council
python -m backend.main      # ⚠️ depuis la racine, PAS depuis backend/

# Terminal 2 — frontend
cd frontend && npm run dev

# Depuis l'agent (Architect Lead ou Security Reviewer) :
curl -X POST localhost:8001/council \
  -d '{"question": "Migrer la BDD de SQLite vers Postgres ?", "context": "..."}'
```

### Mode inline (si le service n'est pas lancé)

L'agent convoquant produit lui-même les 3 étapes en faisant 3 appels au SDK avec des modèles différents (via `model=` dans `ClaudeAgentOptions`), puis synthétise.

## Règles d'or

- 🏛️ **Pas de Council pour une décision réversible.** Si on peut défaire en < 1h, on tranche seul.
- 🗳️ **3 membres minimum, diversité d'éditeurs préférée.**
- 🕶️ **Anonymisation stricte à l'étape 2.** Sinon biais de prestige.
- 📜 **Tout Council = artefact markdown archivé** dans `docs/council/<date>-<sujet>.md`.
- 🪶 **Question fermée obligatoire.** Si tu ne peux pas formuler en OUI/NON/ALTERNATIVE, c'est que la spec est ambiguë → renvoi au PO.
- 🚨 **Faille CRITIQUE = Council immédiat, non négociable.**
- 🤝 **Le Chairman tranche, pas la majorité.** S'il invalide les 3 réponses, il propose une 4ème voie.
