# TaiCorp AI Agents — équipe d'agents de développement

Une équipe de **9 agents IA spécialisés** organisée comme un studio de dev, motorisée par le **Claude Agent SDK**. Chaque agent a un rôle, des **outils restreints** et des **règles d'or** qui l'empêchent de sortir de son couloir.

## Le pipeline

```
Utilisateur → PO → Architecte → Context Manager → Senior Coder
                                                      │
                                   ┌──────────────────┼──────────────────┐
                                   ▼                  ▼                  ▼
                               Reviewer         Test Engineer      Security Reviewer
                                   └──────────────────┼──────────────────┘
                                                      ▼
                                          3 verts ? → Git → DevOps → Déploiement
```

> 🔁 **Boucle** : un verdict bloquant (Reviewer / Test / Security) renvoie au Senior Coder *via* le Context Manager. On ne passe à l'intégration que lorsque les 3 gardiens sont au vert.

## Structure du dossier

- `.claude/agents/` — **un fichier par agent** (prompt système + outils + modèle + règles). Format de sous-agent Claude Code / Agent SDK.
- `docs/passive-services.md` — les 3 services passifs (Memory, Dependency Graph, LLM Council), qui ne sont **pas** des agents LLM.

## Les agents

| # | Agent (`name`) | Modèle | Outils | Rôle en une ligne |
|---|----------------|--------|--------|-------------------|
| 1 | `reporter-po` | sonnet | lecture seule | Besoin brut → spec + critères d'acceptation |
| 2 | `architect-lead` | opus | + Write, Bash | Spec → tickets + ADR |
| 3 | `context-manager` | sonnet | lecture + Bash | Sélection du contexte minimal (anti-tokens) |
| 4 | `senior-coder` | sonnet | code complet | Implémentation |
| 5 | `reviewer` | sonnet | lecture + Bash | Critique qualité / dette technique |
| 6 | `test-engineer` | sonnet | code complet | Tests + non-régression |
| 7 | `security-reviewer` | opus | lecture + Bash | Audit sécurité |
| 8 | `git-integration` | haiku | Bash | Commits, branches, CI |
| 9 | `devops-infra` | sonnet | code complet | Docker, déploiement |

> 🔒 Les outils restreints **font respecter les règles** : le PO ne peut littéralement pas écrire de code (pas de `Write`/`Edit`/`Bash`), le Reviewer ne peut pas corriger à la place du codeur, etc.

## Comment l'utiliser

### Dans Claude Code
Les fichiers `.claude/agents/*.md` sont détectés automatiquement quand tu ouvres ce dossier. Invoque un agent via le Task tool (« delegate to `senior-coder` »).

### Dans le Claude Agent SDK (Python)
```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    setting_sources=["project"],   # charge .claude/agents/
    cwd="/chemin/vers/TaiCorp AI AGENTS",
)
async for message in query(prompt="<la demande utilisateur>", options=options):
    print(message)
```
> TypeScript : même principe avec `settingSources: ["project"]`.

## Réglage des coûts (ton dashboard tokens)
- **Cerveaux (opus)** : Architecte + Security — décisions à fort impact.
- **Exécutants (sonnet)** : PO, Context Manager, Coder, Reviewer, Test, DevOps.
- **Mécanique (haiku)** : Git.

Si ton budget tokens chauffe → baisse un agent d'un cran. Sur les gros projets → monte Reviewer en opus.

## Fusion sur petit projet
- `reporter-po` + `architect-lead` → un seul agent « conception ».
- `reviewer` + `security-reviewer` → un seul gardien (sauf auth / API sensibles : on garde Security séparé).

## Le moteur (`engine/`)

L'orchestrateur Python qui fait **réellement** tourner les agents et alimente le jeu en direct.

| Fichier | Rôle |
|---|---|
| `agents_loader.py` | Charge les 9 agents depuis `.claude/agents/` (modèle, outils, prompt) |
| `orchestrator.py` | Enchaîne le pipeline + boucle de feedback via le **Claude Agent SDK** |
| `bus.py` | Écrit l'état live dans `engine/state/state.json` + `events.jsonl` |
| `server.py` | Sert l'état au jeu (CORS, no-cache) sur `http://localhost:8765` |

### Lancer

```bash
cd engine
pip install -r requirements.txt
cp .env.example .env          # mets ta clé ANTHROPIC_API_KEY

# Mode démo (aucun token brûlé) — pour voir state.json bouger en direct :
python orchestrator.py --demo "Ajoute un login Google"

# Mode réel (les vrais agents tournent) :
python orchestrator.py "Ajoute un login Google"
```

> ⚠️ Le mode réel utilise `permission_mode="bypassPermissions"` : les agents codeurs/git/devops auto-approuvent leurs actions. **À lancer sur une branche jetable ou un sandbox.**

### Comment le jeu se branche

Le moteur écrit `engine/state/state.json` à chaque étape :

```json
{ "ticket": 142, "stage": "senior-coder travaille", "tokens": 410000,
  "cost": 4.7, "xp": 74, "done": 12,
  "agents": { "senior-coder": { "status": "working", "tokens": 320000 }, ... } }
```

**Prochaine étape** : transformer le plateau pixel-art (la maquette du chat) en `web/index.html` qui `fetch()` ce `state.json` toutes les ~1 s → les agents bougent avec les **vraies** données (statut réel, tokens réels, étape réelle).
