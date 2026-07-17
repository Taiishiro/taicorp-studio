# TaiCorp Studio — contexte projet

Studio de dev piloté par 9 agents (Claude Agent SDK) + un plateau pixel-art qui
montre ce qu'ils font. `engine/` = Python, `web/index.html` = tout le front.

## ⚠️ Contraintes non négociables

### /run est une exécution de code arbitraire

Le mode réel lance les agents avec `permission_mode="bypassPermissions"` et Bash.
Toute la sécurité repose sur : **seule la personne devant la machine peut lancer
un run.** Ne jamais affaiblir un de ces points :

- bind `127.0.0.1` (`STUDIO_HOST` = cas Docker isolé uniquement) ;
- **aucun en-tête CORS** — ne pas ré-ajouter `Access-Control-Allow-Origin` ;
- mutations en **POST** seulement (un GET `/run` = RCE drive-by par `<img src>`) ;
- jeton `X-Studio-Token` sur toute mutation, comparé en constant-time ;
- chemins cachés refusés (sinon `/.env` sert `ANTHROPIC_API_KEY`).

Historique des failles : voir [SECURITY.md](SECURITY.md).

### Le pipeline ne livre que sur 3 verts

`run_pipeline` : `MAX_REVIEW_ROUNDS` passes, chaque correction **re-vérifiée**,
et un verdict bloquant maintenu ⇒ `bus.error` + `return`, **jamais** de commit ni
de déploiement. C'est la promesse du README — `engine/tests/` la verrouille.

### bus._write() doit rester atomique

`os.replace()` obligatoire. Un `write_text()` direct laisse le fichier tronqué
pendant que le serveur SSE le lit → JSON invalide → l'UI clignote « OFFLINE ».

### council() doit respecter `demo`

En réel, les membres délibèrent vraiment (un appel chacun). Ne pas revenir à
`DEMO_IDEAS` en mode réel — le conseil serait un décor.

## Gotchas

- **Serveur multi-thread obligatoire** (`ThreadingTCPServer`) : le SSE est une
  connexion longue, et `TCPServer` mono-thread gèle toute l'UI.
- **Docker** : le conteneur doit écouter sur `0.0.0.0` (`STUDIO_HOST`), mais
  `docker-compose` ne publie que sur `127.0.0.1:8765`. Ne jamais écrire
  `"8765:8765"`.
- **PEP 668** : le Python système refuse `pip install`. Utiliser `.venv/`.
- **Le front est un seul fichier** (`web/index.html`, ~560 lignes) : CSS, canvas
  et logique inclus. Assumé — pas de build step.
- **SSE avec repli** : si `/events` tombe, le front repasse en polling sur
  `state.json`. Garder les deux chemins fonctionnels.
- **Le décor est procédural par défaut** ; `web/assets/office.json` + tileset le
  remplacent s'ils sont présents, avec repli auto si absent/cassé.

## Vérifier

```bash
.venv/bin/python -m pytest engine/tests -q   # 6 tests, aucun token consommé
.venv/bin/ruff check engine/                 # la CI lint aussi
```

Les tests stubbent l'exécution des agents : ils tournent sans clé API.

## À faire

- **CI non poussée** : `.github/workflows/ci.yml` existe en local mais le jeton
  `gh` n'a pas le scope `workflow`. Après `gh auth refresh -s workflow`, la
  committer et la pousser (jobs : lint → test → docker-build).
- `bus.py` initialise `ticket: 141`, `xp: 74`, `done: 12` — des compteurs de
  démo en dur, à remettre à zéro si le projet sort du cadre vitrine.
