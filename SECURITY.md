# Sécurité

## Le modèle, en une phrase

**TaiCorp Studio exécute du code arbitraire sur la machine qui l'héberge — c'est sa
fonction.** Le mode réel lance des agents Claude avec `permission_mode="bypassPermissions"`
et l'outil `Bash`. Ils écrivent des fichiers, lancent des commandes, commitent.

Toute la sécurité du projet repose donc sur une seule idée : **seule la personne
assise devant la machine peut déclencher un run.**

## Ce qui est garanti

| Garde-fou | Contre quoi |
|---|---|
| Bind `127.0.0.1` par défaut | Un voisin de réseau qui appelle `/run` |
| Aucun en-tête CORS | Une page tierce qui lit l'état ou le jeton |
| Mutations en `POST` seulement | Le drive-by `<img src="http://localhost:8765/run?…">` |
| Jeton `X-Studio-Token` par démarrage | Le CSRF : le jeton est illisible cross-origin, et le préflight échoue faute de CORS |
| `Origin`/`Referer` vérifiés | Une requête émise depuis une autre page |
| Chemins cachés bloqués | `/.env` (ta clé API !), `/.git/config`, `/.claude/…` |
| `flow`/`mode` sur liste blanche, `branch` sans méta-caractères | L'injection d'arguments vers `argparse` et `git` |
| Chemins d'agents confinés à `.claude/agents/` | L'écriture arbitraire de fichiers via `POST /agent` |

## Ce qui n'est PAS garanti

- **Le mode réel n'est pas un bac à sable.** Un agent peut détruire ton dépôt.
  Branche jetable ou conteneur, toujours.
- **`STUDIO_HOST` désactive le garde-fou principal.** Il existe pour le cas Docker
  (bind `0.0.0.0` *dans* un conteneur, publié sur `127.0.0.1` par l'hôte). Le mettre
  sur une interface publique revient à offrir un shell root à Internet.
- **Un prompt hostile reste un prompt hostile.** Les outils restreints par agent
  limitent les dégâts, ils ne les suppriment pas.

## Signaler une faille

N'ouvre **pas** d'issue publique pour une vulnérabilité.

Écris à **antoninjomir@gmail.com** avec :

- ce que ça permet de faire (impact concret) ;
- les étapes pour le reproduire ;
- la version / le commit concerné.

Réponse sous ~7 jours. Projet personnel, pas de programme de bug bounty — mais la
signalisation sera créditée si tu le souhaites.

## Historique

| Date | Correctif |
|---|---|
| 2026-07 | **RCE non authentifiée.** `server.py` écoutait sur toutes les interfaces (`("", 8765)`) avec `Access-Control-Allow-Origin: *` et un `/run` en `GET` : n'importe qui sur le réseau — ou n'importe quelle page web visitée, via `<img src>` — pouvait exécuter du code. Corrigé par le bind localhost, le passage en POST, le jeton anti-CSRF et la suppression du CORS. |
| 2026-07 | **Fuite de secrets.** `SimpleHTTPRequestHandler` servait la racine du projet, donc `/.env` (contenant `ANTHROPIC_API_KEY`) et `/.git/`. Corrigé : les chemins cachés sont refusés. |
| 2026-07 | **`docker-compose` publiait `8765:8765`**, rouvrant le port sur toutes les interfaces de l'hôte. Corrigé en `127.0.0.1:8765:8765`. |
