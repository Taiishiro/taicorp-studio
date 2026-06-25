# Services passifs

Ces 3 entités ne sont **pas des agents LLM** : c'est l'écosystème que les agents consultent. Pas de prompt système, pas de coût de tokens propre. (C'est pourquoi elles n'ont pas de fichier dans `.claude/agents/`.)

## A. Memory Manager (base vectorielle)
**Contient** : conventions de code, historique des erreurs résolues, ADR, architecture globale.
- **Lu par** : le **Context Manager** (récupération du contexte pertinent).
- **Écrit par** : le **LLM Council** (nouveaux ADR) et l'**Architecte**.
- **Implémentation possible** : base vectorielle (Chroma, Qdrant, sqlite-vec) + embeddings, ou simplement des fichiers Markdown indexés dans `docs/`.

## B. Dependency Graph (Graphify)
**Contient** : la cartographie exacte des liens fichier ↔ fonction ↔ module.
- **Alimenté par** : l'outil **graphify** (`graphify-out/`).
- **Utilisé par** : l'**Architecte** (impact d'une décision) et le **Context Manager** (quels fichiers inclure).
- **Mise à jour** : régénérer après chaque merge structurant.

## C. LLM Council (le Conseil des Sages)
- **Composition** : **Architect Lead + Reviewer + Security Reviewer**.
- **Déclencheur** : UNIQUEMENT les décisions irréversibles (changement de BDD, passage microservices, refonte majeure, alerte sécu critique).
- **Process** : les 3 débattent → consensus → rédaction d'un nouvel ADR (écrit dans le Memory Manager).
- **Jamais** utilisé pour le dev quotidien.
- **Implémentation possible** : ton projet `llm-council` (karpathy) existant — multi-modèles via OpenRouter + un chairman de synthèse.
