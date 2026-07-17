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
| `router.py` | Langage naturel → agent ; appel d'outil → action lisible à l'écran |
| `bus.py` | Écrit l'état live (`state.json` atomique + `events.jsonl` append-only) |
| `server.py` | Sert l'UI, pousse l'état en **SSE**, lance les flows — `127.0.0.1:8765` |
| `tests/` | Les garanties du pipeline et du Council, sans clé API ni tokens |

### Lancer

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r engine/requirements.txt
cp engine/.env.example .env        # mets ta clé ANTHROPIC_API_KEY

python engine/server.py            # → http://localhost:8765/web/index.html
```

Le studio s'ouvre sur le plateau : tu tapes une demande, tu choisis le flow, et tu
regardes les 9 agents travailler. **Décoche « réel » pour rester en démo** : le
pipeline se joue en entier, sans appeler l'API ni brûler un seul token.

En ligne de commande, sans interface :

```bash
python engine/orchestrator.py --demo "Ajoute un login Google"   # simulation
python engine/orchestrator.py "Ajoute un login Google"          # vrais agents
python engine/orchestrator.py --flow route "mets ça sur mon github"
python engine/orchestrator.py --flow meta  "j'ai besoin d'un agent qui traduit la doc"
```

### Tests

```bash
pip install pytest && python -m pytest engine/tests -q
```

Ils verrouillent ce que ce README promet : qu'un verdict bloquant **n'est jamais**
livré, que toute correction repasse devant les gardiens, que le Council délibère
réellement en mode réel, et que `state.json` n'est jamais lisible à moitié écrit.
L'exécution des agents est stubbée → aucun token consommé.

## 🔒 Sécurité — à lire avant de lancer

**`/run` exécute du code arbitraire, par conception.** Le mode réel lance les agents
avec `permission_mode="bypassPermissions"` et l'outil `Bash` sur ce dossier : ils
auto-approuvent leurs actions. C'est le but du projet, et c'est aussi son danger.

Le serveur est donc verrouillé, et ces choix ne sont pas négociables :

| Garde-fou | Pourquoi |
|---|---|
| Bind sur `127.0.0.1` | Le réseau local n'atteint pas le studio |
| Aucun en-tête CORS | Une page tierce ne peut pas lire nos réponses |
| Mutations en `POST` uniquement | Tue le drive-by `<img src="/run?…">` |
| Jeton `X-Studio-Token` | Illisible cross-origin ; le préflight échoue sans CORS |
| `Origin`/`Referer` vérifiés | Rejette les requêtes d'une autre page |
| Chemins cachés bloqués | `/.env`, `/.git/…` ne sont jamais servis |

Ce qu'il ne faut **jamais** faire :

- exposer le port `8765` sur une interface publique (`STUDIO_HOST` existe pour le
  cas Docker, où le conteneur isole — pas pour ouvrir sur Internet) ;
- publier `8765:8765` dans un `docker-compose` (utilise `127.0.0.1:8765:8765`) ;
- lancer le mode réel sur une branche à laquelle tu tiens. **Branche jetable ou
  conteneur**, toujours.

Une faille ? Voir [SECURITY.md](SECURITY.md).

### Comment le plateau se branche

Le bus écrit `engine/state/state.json` à chaque étape :

```json
{ "ticket": 142, "stage": "senior-coder travaille", "tokens": 410000,
  "cost": 4.7, "xp": 74, "done": 12,
  "agents": { "senior-coder": { "status": "working", "tokens": 320000 }, ... } }
```

`server.py` surveille ce fichier et **pousse** chaque changement au navigateur par
SSE (`/events`, ~150 ms). Le front n'interroge plus le serveur chaque seconde : il
écoute. Si le flux tombe, il repasse tout seul en polling sur `state.json`.

En mode réel, chaque `ToolUseBlock` du SDK est traduit en action lisible
(`Edit{file_path:"engine/server.py"}` → **« modifie server.py · handle_run() »**),
donc ce que tu vois à l'écran est littéralement ce que l'agent est en train de faire.

### Le décor

Le plateau est procédural par défaut — aucun asset requis, ça tourne tel quel.
Pour un vrai rendu pixel-art avec ton propre tileset, voir
[`web/assets/README.txt`](web/assets/README.txt) : la carte se peint dans Tiled et
se dépose ici. Absent ou cassé → repli automatique sur le bureau procédural.
