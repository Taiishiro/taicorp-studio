---
name: ponytails
description: Mode "lazy senior dev" — applique systématiquement l'échelle YAGNI avant d'écrire la moindre ligne. Réduit le code écrit de ~54% selon le benchmark du repo. Utilisé par le Senior Coder avant chaque implémentation, et par l'Architect Lead avant chaque ADR pour éviter les abstractions inutiles.
---

# Skill : ponytails — lazy senior dev / échelle YAGNI

> Référence : [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) — benchmark : –54% de code, –20% de coût, sécurité préservée.

## L'échelle ponytail (à monter dans l'ordre, sans sauter de marche)

Avant d'écrire une ligne de code, le coder se pose les questions **dans cet ordre** et s'arrête au premier OUI :

| # | Question | Si OUI |
|---|---------|--------|
| 1 | Cette feature/code doit-il vraiment exister ? | **Skip**. Signaler au PO. |
| 2 | Existe-t-il déjà dans le codebase ? | **Réutiliser**, pas réécrire. |
| 3 | La stdlib le fait-elle ? | Utiliser la stdlib. |
| 4 | Une feature native de la plateforme le fait-elle ? | Utiliser la plateforme. |
| 5 | Une dépendance déjà installée le fait-elle ? | Utiliser cette dépendance. |
| 6 | Une seule ligne suffit-elle ? | Écrire la ligne. |
| 7 | Sinon : minimum viable | Écrire le code, **pas un de plus**. |

## Ce que ponytails interdit

- ❌ **Nouvelle dépendance** sans avoir vérifié les marches 1-5.
- ❌ **Abstraction "au cas où"** — pas de factory, pas d'interface, pas de plugin system spéculatif.
- ❌ **Wrapper / helper** pour deux usages — il faut au moins **trois usages identiques** avant d'extraire.
- ❌ **Refactor sans demande** — l'agent ne re-style pas le code adjacent au passage.
- ❌ **Validation / handler d'erreur** pour des cas qui ne peuvent pas arriver dans le ticket courant.
- ❌ **Commentaire qui décrit le QUOI** (le nom du symbole le dit déjà).

## Quand l'utiliser dans le pipeline

| Agent | Application de ponytails |
|-------|-------------------------|
| **Senior Coder** | Avant chaque ticket — monte les 7 marches avant d'écrire. |
| **Architect Lead** | Avant chaque ADR — la décision la plus paresseuse est souvent la meilleure. |
| **Reviewer** | Comme grille de critique : "Marche 3 (stdlib) sautée ici" est un BLOQUANT. |

## Niveaux d'intensité

| Niveau | Comportement |
|--------|-------------|
| `lite` | Guide gentil, accepte un peu de structure préventive. |
| `full` (défaut) | Échelle stricte, refuse la sur-ingénierie évidente. |
| `ultra` | Minimisation agressive — supprime même les commentaires "utiles". |
| `off` | Désactivé (à éviter sauf projet legacy déjà sur-ingénié). |

## Exemple avant/après ponytails

**Avant** (Senior Coder non-ponytail)
```python
class UserAuthenticationService:
    def __init__(self, config: AuthConfig):
        self.config = config
        self._validator = TokenValidator(config)

    def authenticate(self, token: str) -> AuthResult:
        try:
            return self._validator.validate(token)
        except ValidationError as e:
            logger.error(f"Auth failed: {e}")
            return AuthResult.failure(str(e))
```

**Après** (Senior Coder ponytail-full)
```python
def authenticate(token):
    return jwt.decode(token, SECRET, algorithms=["HS256"])
```

Marche 3 (stdlib + dep déjà installée `PyJWT`) → suffisante. Les erreurs `jwt.InvalidTokenError` remontent naturellement.

## Règles d'or

- 🪜 **Tu ne sautes pas de marche.** Marche 5 jamais avant d'avoir éliminé 1-4.
- 🚫 **Pas de "ça pourra servir plus tard".** Plus tard = jamais ou refacto plus simple.
- 🔁 **3 usages = abstraction. 2 usages = duplication acceptée.**
- ⛔ **Pas de wrapper autour de la stdlib.** Si tu wrappes, tu justifies par écrit dans le diff.
- 🪶 **La meilleure ligne de code est celle qu'on n'écrit pas.**
- 🤝 **Compatible avec [`caveman`](../caveman/SKILL.md)** — ponytails réduit la *quantité de code*, caveman réduit la *quantité de mots autour*.
